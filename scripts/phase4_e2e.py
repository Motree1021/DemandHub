# -*- coding: utf-8 -*-
"""P4 验收自测：角色族权限全链路 + PC 管理端（开发计划 v2.0 任务 4.1~4.12）

覆盖验收标准：
- 管理端接口：用户（分页/详情/补全/激活/停用/合并/映射/设登录账号/重置密码）、组织（CRUD+路径重算+删除引用校验）、
  渠道（列表脱敏/启停/配置/连接测试）；全部仅 ADMIN 可达。
- SRS 第4节权限矩阵：三类经理互不可见对方队列、不能跨类型受理；处理人仅见本类型池、不能跨类型领取；
  EXECUTIVE 只读（队列可见不可操作）；提报不受授权影响。
- 4.12：需求列表 channel 筛选 + 看板 channelDistribution 统计。
- 授权 API：新增/分页/回收（is_deleted=id 防 UK 撞键）。

运行前提：中间件栈 + gateway:8080 + system:8081 + demand:8082 已启动（联调走网关）。
"""
import json
import time
import urllib.request
import urllib.error
import urllib.parse

import pymysql

BASE = "http://localhost:8080/api"
MYSQL = {"host": "localhost", "port": 3307, "user": "root", "password": "demandhub123", "database": "demandhub"}

PASS, FAIL = [], []


def report(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}")


def req(method, path, token=None, body=None, base=BASE):
    url = base + urllib.parse.quote(path, safe="/?=&%")
    data = json.dumps(body).encode("utf-8") if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        payload = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(payload)
        except Exception:
            return e.code, {"raw": payload}


def db(sql, args=None, fetch=False):
    conn = pymysql.connect(**MYSQL, charset="utf8mb4", autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(sql, args) if args is not None else cur.execute(sql)
            return cur.fetchall() if fetch else cur.rowcount
    finally:
        conn.close()


def sso_login(channel_user_id, name=None, phone=None):
    """Mock 签票 → channel-sso 登录，返回 (status, body)"""
    s, b = req("POST", "/system/mock-sso/ticket",
               body={"channelUserId": channel_user_id, "name": name, "phone": phone})
    assert s == 200 and b["code"] == 0, f"签票失败: {s} {b}"
    ticket = b["data"]["ticket"]
    return req("GET", f"/system/auth/channel-sso?channel=chuangjinls&ticket={ticket}")


def login_sso_token(channel_user_id, name=None, phone=None):
    s, b = sso_login(channel_user_id, name, phone)
    assert s == 200 and b["code"] == 0, f"SSO 登录失败: {s} {b}"
    d = b["data"]
    return d["accessToken"], d["user"]["id"]


def cleanup_p4():
    """清理全部 P4 测试数据（幂等，开头结尾各跑一次）"""
    ids = [r[0] for r in db("SELECT id FROM demand WHERE title LIKE 'P4E2E%'", fetch=True)]
    for did in ids:
        db("DELETE FROM demand_transition_log WHERE demand_id=%s", (did,))
        db("DELETE FROM demand WHERE id=%s", (did,))
    user_ids = [r[0] for r in db(
        "SELECT id FROM demand_user WHERE name LIKE 'P4%' OR login_name LIKE 'p4e2e%'", fetch=True)]
    for uid in user_ids:
        db("DELETE FROM channel_user_mapping WHERE demand_user_id=%s", (uid,))
        db("DELETE FROM demand_role_grant WHERE demand_user_id=%s", (uid,))
        db("DELETE FROM demand_user WHERE id=%s", (uid,))
    db("DELETE FROM demand_org WHERE name LIKE 'P4%'")


# 预清理（防上次中断残留）
cleanup_p4()

# ---------------- 0. 登录态准备 ----------------
print("== 0. 登录态准备 ==")
s, b = req("POST", "/system/auth/login", body={"loginName": "admin", "password": "Admin@123456"})
admin = (b.get("data") or {}).get("accessToken")
report("0.1 admin 账密登录", s == 200 and b["code"] == 0 and admin, f"status={s} code={b.get('code')}")

mgr_tech, mgr_tech_id = login_sso_token("wq_u_mgr_tech")      # 1003 MANAGER 110 TECH
exec_tok, exec_id = login_sso_token("wq_u_exec_001")          # 1002 EXECUTIVE
handler_matl, handler_matl_id = login_sso_token("wq_u_handler_a1")  # 1004 HANDLER 121 MATL
handler_tech, handler_tech_id = login_sso_token("wq_u_reporter_2")  # 1007 HANDLER 111 TECH
reporter, reporter_id = login_sso_token("wq_u_reporter_1")    # 1006 无角色
print(f"  seed ids: mgr_tech={mgr_tech_id} exec={exec_id} handler_matl={handler_matl_id} "
      f"handler_tech={handler_tech_id} reporter={reporter_id}")

# 新建两名测试经理（D4 自动建号 → 授权 → 重新登录取新 claims）
_, mgr_matl_id = login_sso_token("p4_mgr_matl", "P4物料经理", "13800009901")
_, mgr_train_id = login_sso_token("p4_mgr_train", "P4培训经理", "13800009902")
print(f"  new mgr ids: matl={mgr_matl_id} train={mgr_train_id}")

# ---------------- 1. 管理端鉴权（仅 ADMIN） ----------------
print("== 1. 管理端鉴权 ==")
s, b = req("GET", "/system/user/page?current=1&size=3", token=admin)
report("1.1 ADMIN 可访用户分页", s == 200 and b["code"] == 0, f"total={(b.get('data') or {}).get('total')}")

s, b = req("GET", "/system/user/page", token=mgr_tech)
report("1.2 MANAGER 访用户管理被拒", s == 200 and b.get("code") == 403, f"code={b.get('code')}")

s, b = req("GET", "/system/channel/list", token=reporter)
report("1.3 无角色访渠道管理被拒", s == 200 and b.get("code") == 403, f"code={b.get('code')}")

s, b = req("GET", "/system/user/page")
report("1.4 无 token 网关 401", s == 401, f"http={s}")

s, b = req("POST", "/system/org", token=mgr_tech, body={"name": "X", "level": "GROUP", "parentId": 110, "orgKind": "BOTH"})
report("1.5 MANAGER 建组织被拒", s == 200 and b.get("code") == 403, f"code={b.get('code')}")

# ---------------- 2. 用户管理 ----------------
print("== 2. 用户管理 ==")
s, b = req("GET", "/system/user/page?keyword=王经理", token=admin)
recs = (b.get("data") or {}).get("records") or []
report("2.1 用户分页关键字过滤", s == 200 and b["code"] == 0 and any(r["name"] == "王经理" for r in recs),
       f"hits={len(recs)}")

s, b = req("GET", "/system/user/page?status=PENDING&size=50", token=admin)
recs = (b.get("data") or {}).get("records") or []
report("2.2 用户分页状态过滤", s == 200 and all(r["status"] == "PENDING" for r in recs), f"pending={len(recs)}")

s, b = req("GET", f"/system/user/{mgr_tech_id}", token=admin)
u = b.get("data") or {}
report("2.3 用户详情脱敏+部门路径",
       s == 200 and u.get("passwordHash") is None and "财管科技产品部" in (u.get("deptPath") or "")
       and "*" in (u.get("phone") or ""),
       f"deptPath={u.get('deptPath')} phone={u.get('phone')}")

# PENDING 补全：DB 直插模拟渠道字段缺失建号
db("INSERT INTO demand_user(name, phone, is_employee, primary_org_id, status) VALUES('P4待补全', NULL, 0, 900, 'PENDING')")
pending_id = db("SELECT id FROM demand_user WHERE name='P4待补全'", fetch=True)[0][0]
s, b = req("POST", f"/system/user/{pending_id}/complete", token=admin,
           body={"name": "P4补全用户", "phone": "13800009903", "email": "p4@demandhub.local",
                 "employeeNo": "P4001", "primaryOrgId": 141})
st = db("SELECT status FROM demand_user WHERE id=%s", (pending_id,), fetch=True)[0][0]
report("2.4 PENDING 补全激活", s == 200 and b["code"] == 0 and st == "ACTIVE", f"status={st}")

s, b = req("PUT", f"/system/user/{pending_id}/login-account", token=admin, body={"loginName": "admin"})
report("2.5a 登录账号冲突被拒", s == 200 and b.get("code") == 400, f"code={b.get('code')}")
s, b = req("PUT", f"/system/user/{pending_id}/login-account", token=admin, body={"loginName": "p4e2e_user"})
report("2.5b 设登录账号", s == 200 and b["code"] == 0, f"code={b.get('code')}")

s, b = req("PUT", f"/system/user/{pending_id}/reset-password", token=admin, body={"newPassword": "weak"})
report("2.6a 弱密码被拒", s == 200 and b.get("code") == 1111, f"code={b.get('code')}")
s, b = req("PUT", f"/system/user/{pending_id}/reset-password", token=admin, body={"newPassword": "P4e2e2026abc"})
pu = db("SELECT password_updated_at FROM demand_user WHERE id=%s", (pending_id,), fetch=True)[0][0]
report("2.6b 重置密码强制改密", s == 200 and b["code"] == 0 and pu is None, f"password_updated_at={pu}")

s, b = req("POST", "/system/auth/login", body={"loginName": "p4e2e_user", "password": "P4e2e2026abc"})
ld = b.get("data") or {}
report("2.7 重置后登录须改密", s == 200 and b["code"] == 0 and ld.get("mustChangePassword") is True,
       f"mustChangePassword={ld.get('mustChangePassword')}")
p4_tok = ld.get("accessToken")

s, b = req("POST", f"/system/user/{pending_id}/disable", token=admin)
time.sleep(0.3)
s2, b2 = req("GET", "/system/auth/me", token=p4_tok)
st = db("SELECT status FROM demand_user WHERE id=%s", (pending_id,), fetch=True)[0][0]
report("2.8 停用踢下线", s == 200 and b["code"] == 0 and st == "DISABLED" and s2 == 401,
       f"status={st} me_http={s2}")
s, b = req("POST", f"/system/user/{pending_id}/activate", token=admin)
st = db("SELECT status FROM demand_user WHERE id=%s", (pending_id,), fetch=True)[0][0]
report("2.8b 激活恢复", s == 200 and b["code"] == 0 and st == "ACTIVE", f"status={st}")

s, b = req("POST", "/system/user/1001/disable", token=admin)
report("2.9 拒停当前登录账号", s == 200 and b.get("code") != 0, f"code={b.get('code')} msg={b.get('message')}")

s, b = req("GET", f"/system/user/{mgr_tech_id}/mappings", token=admin)
maps = b.get("data") or []
report("2.10 渠道映射列表", s == 200 and any(m["channelCode"] == "CHUANGJIN_LS" for m in maps), f"mappings={len(maps)}")

# 合并：源用户先提一个需求（制造引用），合并后源 MERGED、需求归目标
_, merge_src = login_sso_token("p4_merge_src", "P4合并源", "13800009904")
_, merge_dst = login_sso_token("p4_merge_dst", "P4合并目标", "13800009905")
src_tok, _ = login_sso_token("p4_merge_src")
s, b = req("POST", "/demand/demand/submit", token=src_tok,
           body={"title": "P4E2E-合并引用需求", "content": "merge ref", "demandTypeCode": "TECH"})
merge_demand = (b.get("data") or {}).get("id")
s, b = req("GET", f"/system/user/merge/preview?sourceUserId={merge_src}", token=admin)
preview = b.get("data") or {}
report("2.11a 合并预览有引用", s == 200 and b["code"] == 0 and sum(preview.values()) >= 1, f"preview={preview}")
s, b = req("POST", "/system/user/merge", token=admin, body={"sourceUserId": merge_src, "targetUserId": merge_dst})
st = db("SELECT status FROM demand_user WHERE id=%s", (merge_src,), fetch=True)[0][0]
owner = db("SELECT submitter_id FROM demand WHERE id=%s", (merge_demand,), fetch=True)[0][0]
report("2.11b 合并执行", s == 200 and b["code"] == 0 and st == "MERGED" and owner == merge_dst,
       f"src_status={st} demand_owner={owner}")

# ---------------- 3. 组织管理 ----------------
print("== 3. 组织管理 ==")
s, b = req("GET", "/system/org/tree", token=admin)
tree = b.get("data") or []
root = tree[0] if tree else {}
report("3.1 组织树含校准字段", s == 200 and root.get("orgId") == 100 and "externalDeptId" in root and "status" in root,
       f"root={root.get('name')}")

s, b = req("POST", "/system/org", token=admin,
           body={"name": "P4测试组A", "level": "GROUP", "parentId": 110, "orgKind": "BOTH"})
org_a = b.get("data")
path_a = db("SELECT path FROM demand_org WHERE id=%s", (org_a,), fetch=True)[0][0]
report("3.2 新建组织路径物化", s == 200 and b["code"] == 0 and path_a == f"/100/110/{org_a}/", f"path={path_a}")

s, b = req("POST", "/system/org", token=admin,
           body={"name": "P4测试组B", "level": "GROUP", "parentId": org_a, "orgKind": "ASSIGNER"})
org_b = b.get("data")
s, b = req("PUT", f"/system/org/{org_a}", token=admin,
           body={"name": "P4测试组A", "level": "GROUP", "parentId": 120, "orgKind": "BOTH"})
path_a2, path_b2 = db("SELECT path FROM demand_org WHERE id=%s", (org_a,), fetch=True)[0][0], \
                   db("SELECT path FROM demand_org WHERE id=%s", (org_b,), fetch=True)[0][0]
report("3.3 父级变更子树路径重算",
       s == 200 and b["code"] == 0 and path_a2 == f"/100/120/{org_a}/" and path_b2 == f"/100/120/{org_a}/{org_b}/",
       f"a={path_a2} b={path_b2}")

s, b = req("DELETE", f"/system/org/{org_a}", token=admin)
report("3.4a 有子组织拒删", s == 200 and b.get("code") != 0, f"code={b.get('code')}")
s, b = req("DELETE", "/system/org/110", token=admin)
report("3.4b 有用户/授权拒删", s == 200 and b.get("code") != 0, f"code={b.get('code')}")
s, b = req("DELETE", "/system/org/100", token=admin)
report("3.4c 根组织拒删", s == 200 and b.get("code") != 0, f"code={b.get('code')}")
s, b = req("DELETE", "/system/org/900", token=admin)
report("3.4d 外部虚拟组织拒删", s == 200 and b.get("code") != 0, f"code={b.get('code')}")

s, b = req("DELETE", f"/system/org/{org_b}", token=admin)
s2, b2 = req("DELETE", f"/system/org/{org_a}", token=admin)
gone = db("SELECT COUNT(*) FROM demand_org WHERE id IN (%s,%s)", (org_a, org_b), fetch=True)[0][0] == 0
report("3.5 空叶组织可删", s == 200 and b["code"] == 0 and s2 == 200 and b2["code"] == 0 and gone, f"gone={gone}")

# ---------------- 4. 渠道管理 ----------------
print("== 4. 渠道管理 ==")
s, b = req("GET", "/system/channel/list", token=admin)
chs = b.get("data") or []
cj = next((c for c in chs if c["channelCode"] == "CHUANGJIN_LS"), {})
report("4.1 渠道列表密钥脱敏", s == 200 and len(chs) == 8 and cj.get("appSecret") == "***" and cj.get("ssoConfigured"),
       f"channels={len(chs)} secret={cj.get('appSecret')}")

s, b = req("PUT", "/system/channel/3/status", token=admin, body={"status": "ACTIVE"})
s2, b2 = req("PUT", "/system/channel/3/status", token=admin, body={"status": "DISABLED"})
st = db("SELECT status FROM demand_channel WHERE id=3", fetch=True)[0][0]
report("4.2 渠道启停", s == 200 and b["code"] == 0 and s2 == 200 and st == "DISABLED", f"restored={st}")

s, b = req("PUT", "/system/channel/2/config", token=admin, body={"timeoutMs": 5000})
s2, b2 = req("GET", "/system/channel/list", token=admin)
cj2 = next((c for c in (b2.get("data") or []) if c["channelCode"] == "CHUANGJIN_LS"), {})
report("4.3 配置更新密钥不动", s == 200 and b["code"] == 0 and cj2.get("timeoutMs") == 5000 and cj2.get("appSecret") == "***",
       f"timeoutMs={cj2.get('timeoutMs')}")
req("PUT", "/system/channel/2/config", token=admin, body={"timeoutMs": 3000})

s, b = req("POST", "/system/channel/2/test", token=admin)
msg = str(b.get("data") or b.get("message") or "")
report("4.4 渠道连接测试", s == 200 and b["code"] == 0 and "连接正常" in msg, f"msg={msg[:40]}")

s, b = req("GET", "/system/channel/dept-unmapped/page?current=1&size=5", token=admin)
report("4.5 部门未映射分页", s == 200 and b["code"] == 0 and "total" in (b.get("data") or {}),
       f"total={(b.get('data') or {}).get('total')}")

# ---------------- 5. 角色授权 API ----------------
print("== 5. 角色授权 API ==")
s, b = req("POST", "/system/grant", token=admin,
           body={"demandUserId": mgr_matl_id, "roleCode": "MANAGER", "orgId": 120, "demandTypeScope": "MATL"})
grant_matl = b.get("data")
report("5.1 新增授权(MATL经理)", s == 200 and b["code"] == 0 and grant_matl, f"id={grant_matl}")
s, b = req("POST", "/system/grant", token=admin,
           body={"demandUserId": mgr_train_id, "roleCode": "MANAGER", "orgId": 130, "demandTypeScope": "TRAIN"})
grant_train = b.get("data")
report("5.1b 新增授权(TRAIN经理)", s == 200 and b["code"] == 0 and grant_train, f"id={grant_train}")

s, b = req("GET", f"/system/grant/page?demandUserId={mgr_matl_id}", token=admin)
recs = (b.get("data") or {}).get("records") or []
report("5.2 授权分页按用户过滤", s == 200 and any(r["id"] == grant_matl for r in recs), f"hits={len(recs)}")

# 回收/重建各一次验证 is_deleted=id 防撞键；矩阵测试用最终这条授权
s, b = req("DELETE", f"/system/grant/{grant_matl}", token=admin)
flag = db("SELECT is_deleted FROM demand_role_grant WHERE id=%s", (grant_matl,), fetch=True)[0][0]
report("5.3 回收置 is_deleted=id", s == 200 and b["code"] == 0 and flag == grant_matl, f"is_deleted={flag}")
s, b = req("POST", "/system/grant", token=admin,
           body={"demandUserId": mgr_matl_id, "roleCode": "MANAGER", "orgId": 120, "demandTypeScope": "MATL"})
grant_matl = b.get("data")
report("5.4 回收后同键可重建", s == 200 and b["code"] == 0 and grant_matl, f"new_id={grant_matl}")

# 授权后重新登录取新角色 claims
mgr_matl, _ = login_sso_token("p4_mgr_matl")
mgr_train, _ = login_sso_token("p4_mgr_train")

# ---------------- 6. SRS 权限矩阵 ----------------
print("== 6. SRS 权限矩阵 ==")
def submit(tok, title, type_code, channel=None):
    body = {"title": title, "content": "P4 矩阵验收", "demandTypeCode": type_code}
    if channel:
        body["channel"] = channel
    s, b = req("POST", "/demand/demand/submit", token=tok, body=body)
    assert s == 200 and b["code"] == 0, f"提报失败 {title}: {s} {b}"
    return b["data"]["id"]

t1 = submit(reporter, "P4E2E-T1科技", "TECH")                 # WEB, assignee=111
m1 = submit(reporter, "P4E2E-M1物料", "MATL")                 # WEB, assignee=121
r1 = submit(reporter, "P4E2E-R1培训", "TRAIN")                # WEB, assignee=131
c1 = submit(reporter, "P4E2E-C1渠道科技", "TECH", "CHUANGJIN_LS")  # 渠道来源, assignee=111
print(f"  demands: T1={t1} M1={m1} R1={r1} C1={c1}")

def queue_ids(tok, type_code=None):
    # submittedOrder=desc：新纪录在前，避免 ASC 下压测存量把新数据挤到末页（maxLimit=500）
    q = f"/demand/triage/queue?size=500&submittedOrder=desc"
    if type_code:
        q += f"&demandTypeCode={type_code}"
    s, b = req("GET", q, token=tok)
    assert s == 200 and b["code"] == 0, f"queue 失败: {s} {b}"
    return {r["id"] for r in (b["data"]["records"] or [])}

def pool_ids(tok):
    # pool 固定 urgency 排序 + submitted_at ASC，无排序参数；MP maxLimit=500，翻页合并
    ids, current = set(), 1
    while True:
        s, b = req("GET", f"/demand/triage/pool?size=500&current={current}", token=tok)
        assert s == 200 and b["code"] == 0, f"pool 失败: {s} {b}"
        data = b["data"]
        ids.update(r["id"] for r in (data["records"] or []))
        if current >= (data.get("pages") or 1):
            return ids
        current += 1

q_tech = queue_ids(mgr_tech)
report("6.1 TECH经理队列只含本类型", t1 in q_tech and c1 in q_tech and m1 not in q_tech and r1 not in q_tech,
       f"T1={t1 in q_tech} C1={c1 in q_tech} M1={m1 in q_tech} R1={r1 in q_tech}")
q_matl = queue_ids(mgr_matl)
report("6.2 MATL经理队列只含本类型", m1 in q_matl and t1 not in q_matl and r1 not in q_matl,
       f"M1={m1 in q_matl} T1={t1 in q_matl} R1={r1 in q_matl}")
q_train = queue_ids(mgr_train)
report("6.3 TRAIN经理队列只含本类型", r1 in q_train and t1 not in q_train and m1 not in q_train,
       f"R1={r1 in q_train} T1={t1 in q_train} M1={m1 in q_train}")
# 经理互不可见对方队列（类型维度强过滤：队列按类型过滤后为空）
q_matl_tech = queue_ids(mgr_matl, "TECH")
report("6.3b MATL经理按TECH过滤为空", t1 not in q_matl_tech and len(q_matl_tech) == 0, f"size={len(q_matl_tech)}")

s, b = req("POST", f"/demand/triage/{t1}/accept", token=mgr_matl, body={})
# 跨类型需求对 MATL 经理不可见（DataScope）→ selectById=null → 1002；显式越权 → 403，均为有效拒绝
report("6.4 MATL经理受理TECH被拒", s == 200 and b.get("code") in (403, 1002), f"code={b.get('code')}")
s, b = req("POST", f"/demand/triage/{m1}/accept", token=mgr_tech, body={})
report("6.5 TECH经理受理MATL被拒", s == 200 and b.get("code") in (403, 1002), f"code={b.get('code')}")
s, b = req("POST", f"/demand/triage/{t1}/accept", token=exec_tok, body={})
report("6.6 EXECUTIVE不可操作受理", s == 200 and b.get("code") == 403, f"code={b.get('code')}")

s, b = req("POST", f"/demand/triage/{t1}/accept", token=mgr_tech, body={})
st1 = db("SELECT status FROM demand WHERE id=%s", (t1,), fetch=True)[0][0]
report("6.7 TECH经理受理本类型", s == 200 and b["code"] == 0 and st1 == "TRIAGE", f"status={st1}")
s, b = req("POST", f"/demand/triage/{m1}/accept", token=mgr_matl, body={})
stm = db("SELECT status FROM demand WHERE id=%s", (m1,), fetch=True)[0][0]
report("6.8 MATL经理受理本类型", s == 200 and b["code"] == 0 and stm == "TRIAGE", f"status={stm}")

p_matl = pool_ids(handler_matl)
p_tech = pool_ids(handler_tech)
report("6.9 处理人池仅本类型", m1 in p_matl and t1 not in p_matl and t1 in p_tech and m1 not in p_tech,
       f"M1∈matl={m1 in p_matl} T1∈matl={t1 in p_matl} T1∈tech={t1 in p_tech} M1∈tech={m1 in p_tech}")

s, b = req("POST", f"/demand/triage/{t1}/claim", token=handler_matl)
report("6.10 处理人跨类型领取被拒", s == 200 and b.get("code") in (403, 1002), f"code={b.get('code')}")

s, b = req("POST", f"/demand/triage/{t1}/claim", token=handler_tech)
st1 = db("SELECT status FROM demand WHERE id=%s", (t1,), fetch=True)[0][0]
report("6.11a 本类型处理人领取", s == 200 and b["code"] == 0 and st1 == "ANALYZING", f"status={st1}")
s, b = req("POST", f"/demand/triage/{m1}/claim", token=handler_matl)
stm = db("SELECT status FROM demand WHERE id=%s", (m1,), fetch=True)[0][0]
report("6.11b 本类型处理人领取2", s == 200 and b["code"] == 0 and stm == "ANALYZING", f"status={stm}")

s, b = req("GET", "/demand/triage/queue", token=reporter)
c_queue = b.get("code")
s2, b2 = req("GET", "/demand/triage/pool", token=reporter)
report("6.12 无角色用户队列/池均403", s == 200 and c_queue == 403 and s2 == 200 and b2.get("code") == 403,
       f"queue={c_queue} pool={b2.get('code')}")

q_exec = queue_ids(exec_tok)
report("6.13 EXECUTIVE队列读视图bypass", r1 in q_exec and c1 in q_exec,
       f"R1={r1 in q_exec} C1={c1 in q_exec}（T1/M1 已被受理转出 SUBMITTED）")

s, b = req("POST", "/demand/demand/submit", token=reporter,
           body={"title": "P4E2E-提报不受授权影响", "content": "x", "demandTypeCode": "TRAIN"})
no_grant_submit = b.get("data") or {}
report("6.14 提报不受授权影响", s == 200 and b["code"] == 0 and no_grant_submit.get("id"), f"id={no_grant_submit.get('id')}")

# ---------------- 7. channel 筛选与看板统计（4.12） ----------------
print("== 7. channel 筛选与看板统计 ==")
s, b = req("GET", "/demand/demand/page?channel=CHUANGJIN_LS&size=100", token=exec_tok)
recs = (b.get("data") or {}).get("records") or []
report("7.1 列表按渠道筛选(创金零售)", s == 200 and len(recs) > 0 and all(r.get("channel") == "CHUANGJIN_LS" for r in recs)
       and any(r["id"] == c1 for r in recs), f"rows={len(recs)} C1={any(r['id'] == c1 for r in recs)}")

s, b = req("GET", "/demand/demand/page?channel=WEB&size=100", token=exec_tok)
recs = (b.get("data") or {}).get("records") or []
report("7.2 列表按渠道筛选(WEB)", s == 200 and len(recs) > 0 and all(r.get("channel") == "WEB" for r in recs),
       f"rows={len(recs)}")

s, b = req("GET", "/demand/dashboard/manager?range=quarter", token=exec_tok)
dist = (b.get("data") or {}).get("channelDistribution") or []
cj_dist = next((d for d in dist if d.get("channel") == "CHUANGJIN_LS"), None)
report("7.3 看板渠道来源分布", s == 200 and b["code"] == 0 and len(dist) > 0 and cj_dist and cj_dist.get("channelName") == "创金零售",
       f"dist={[(d.get('channel'), d.get('cnt')) for d in dist]}")

# ---------------- 8. 清理 ----------------
print("== 8. 清理 ==")
cleanup_p4()
left = db("SELECT COUNT(*) FROM demand WHERE title LIKE 'P4E2E%'", fetch=True)[0][0]
left_u = db("SELECT COUNT(*) FROM demand_user WHERE name LIKE 'P4%' OR login_name LIKE 'p4e2e%'", fetch=True)[0][0]
report("8.1 测试数据自清理", left == 0 and left_u == 0, f"demand={left} user={left_u}")

# ---------------- 汇总 ----------------
print(f"\n===== 结果: {len(PASS)} PASS / {len(FAIL)} FAIL =====")
if FAIL:
    print("失败项:")
    for f in FAIL:
        print(f"  - {f}")
    raise SystemExit(1)
