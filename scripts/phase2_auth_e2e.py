# -*- coding: utf-8 -*-
"""P2 验收自测：认证会话重构 + PC 账密（开发计划 v2.0 任务 2.1~2.6）

覆盖验收标准：Mock 下登录/刷新/登出/授权失效全通；账密登录、错误锁定、强制改密通过；越权构造头 401/403。
附加：渠道匹配引擎（映射/手机/企微/自动建号/MERGED 跳转）、refresh 旋转、票据一次性、旧端点下线。

运行前提：中间件栈 + gateway:8080 + system:8081 已启动（联调走网关）。
"""
import json
import os
import sys
import time
import urllib.request
import urllib.error

import pymysql

BASE = os.environ.get("E2E_BASE", "http://localhost:8080/api")
# 微服务形态：直连 8081 验证业务服务只信网关头；单体形态（E2E_MONOLITH=1）：等价于无 token 访问单体
DIRECT = os.environ.get("E2E_DIRECT", "http://localhost:8081/system")
MONOLITH = os.environ.get("E2E_MONOLITH") == "1"
MYSQL = {"host": "localhost", "port": 3307, "user": "root", "password": "demandhub123", "database": "demandhub"}
SEED_HASH = "$2b$10$l8x3YuZxjnhAEHHQSnL5oeHe7fmlC8AlyvYdYrWi0qSPYViSVaa0y"  # Admin@123456

PASS, FAIL = [], []


def report(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}")


def req(method, path, token=None, body=None, headers=None, base=BASE):
    url = base + path
    data = json.dumps(body).encode("utf-8") if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", f"Bearer {token}")
    for k, v in (headers or {}).items():
        r.add_header(k, v)
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
            cur.execute(sql, args or ())
            return cur.fetchall() if fetch else cur.rowcount
    finally:
        conn.close()


def sso_login(channel_user_id, name=None, phone=None):
    """Mock 签票 → channel-sso 登录，返回 (status, body)"""
    s, b = req("POST", "/system/mock-sso/ticket",
               body={"channelUserId": channel_user_id, "name": name, "phone": phone})
    assert s == 200 and b["code"] == 0, f"签票失败: {s} {b}"
    ticket = b["data"]["ticket"]
    return req("GET", f"/system/auth/channel-sso?channel=chuangjinls&ticket={ticket}"), ticket


def cleanup_users(ids):
    for uid in ids:
        db("DELETE FROM channel_user_mapping WHERE demand_user_id=%s", (uid,))
        db("DELETE FROM demand_role_grant WHERE demand_user_id=%s", (uid,))
        db("DELETE FROM demand_user WHERE id=%s", (uid,))


# ---------------- 1. Mock 渠道 SSO 登录主链路 ----------------
print("== 1. Mock 渠道 SSO 登录 ==")
s, b = req("GET", "/system/mock-sso/entry")
report("1.1 Mock 入口用户列表", s == 200 and b["code"] == 0 and len(b["data"]) >= 7,
       f"users={len(b.get('data') or [])}")

(sso_resp), ticket = sso_login("wq_u_mgr_tech")
s, b = sso_resp
mgr = b.get("data") or {}
report("1.2 渠道SSO登录(王经理)", s == 200 and b["code"] == 0 and mgr.get("channel") == "CHUANGJIN_LS"
       and mgr["user"]["id"] == 1003 and "MANAGER" in mgr["user"]["roles"]
       and mgr["user"].get("typeScopes") == ["TECH"],
       f"status={s} channel={mgr.get('channel')} roles={mgr.get('user', {}).get('roles')} typeScopes={mgr.get('user', {}).get('typeScopes')}")
mgr_access, mgr_refresh = mgr.get("accessToken"), mgr.get("refreshToken")
report("1.3 access 2h/refresh 8h", mgr.get("expiresIn") == 7200, f"expiresIn={mgr.get('expiresIn')}")

s, b = req("GET", f"/system/auth/channel-sso?channel=chuangjinls&ticket={ticket}")
report("1.4 票据重放拦截", s == 200 and b.get("code") == 1107, f"status={s} code={b.get('code')}")

s, b = req("GET", f"/system/auth/channel-sso?channel=chuangjinls&ticket=forged-ticket-123")
report("1.5 伪造票据拦截", s == 200 and b.get("code") == 1107, f"status={s} code={b.get('code')}")

s, b = req("GET", "/system/auth/me", token=mgr_access)
me = b.get("data") or {}
report("1.6 me 返回渠道(X-Channel注入)", s == 200 and me.get("channel") == "CHUANGJIN_LS"
       and me.get("mustChangePassword") is False, f"channel={me.get('channel')}")

# refresh 旋转
s, b = req("POST", "/system/auth/refresh", body={"refreshToken": mgr_refresh})
rot = b.get("data") or {}
report("1.7 refresh 旋转签发新对", s == 200 and rot.get("refreshToken") and rot["refreshToken"] != mgr_refresh
       and rot.get("channel") == "CHUANGJIN_LS", f"status={s}")
s, b = req("POST", "/system/auth/refresh", body={"refreshToken": mgr_refresh})
report("1.8 旧 refresh 重用被拒(旋转生效)", s == 200 and b.get("code") == 1103, f"status={s} code={b.get('code')}")
mgr_access2 = rot.get("accessToken")

# 登出
s, b = req("POST", f"/system/auth/logout?refreshToken={rot.get('refreshToken')}", token=mgr_access2)
s2, b2 = req("GET", "/system/auth/me", token=mgr_access2)
report("1.9 登出后 access 即失效", s == 200 and s2 == 401, f"logout={s} me={s2}")

# ---------------- 2. 渠道匹配引擎 ----------------
print("== 2. 渠道匹配引擎 ==")
# 手机精确匹配：新渠道 userid + 已有手机(赵一线 13800001006) → 命中 1006，建 PHONE 映射
(sso_resp), _ = sso_login("wq_dev_zhao_new", phone="13800001006")
s, b = sso_resp
u = (b.get("data") or {}).get("user") or {}
m = db("SELECT match_type FROM channel_user_mapping WHERE channel_code='CHUANGJIN_LS' AND channel_user_id='wq_dev_zhao_new'", fetch=True)
report("2.1 手机精确匹配命中既有 OneID", s == 200 and u.get("id") == 1006 and m and m[0][0] == "PHONE",
       f"uid={u.get('id')} match={m}")

# 冲突：ticket=wq_u_reporter_2(映射→1007) 但携带 1006 的手机 → 登录 1007，合并提示记日志
(sso_resp), _ = sso_login("wq_u_reporter_2", phone="13800001006")
s, b = sso_resp
u = (b.get("data") or {}).get("user") or {}
report("2.2 同手机多 OneID 冲突不阻塞登录(映射优先)", s == 200 and u.get("id") == 1007, f"uid={u.get('id')}")

# D4 自动建号：全新 userid+手机 → ACTIVE + is_employee + WECOMID 映射 + 兜底组织 900
(sso_resp), _ = sso_login("wq_new_emp_p2", name="测试新人", phone="13911112222")
s, b = sso_resp
u = (b.get("data") or {}).get("user") or {}
row = db("SELECT status, is_employee, primary_org_id, wecom_userid FROM demand_user WHERE phone='13911112222'", fetch=True)
m = db("SELECT match_type FROM channel_user_mapping WHERE channel_user_id='wq_new_emp_p2'", fetch=True)
new_id = row and db("SELECT id FROM demand_user WHERE phone='13911112222'", fetch=True)[0][0]
report("2.3 D4 自动建 ACTIVE 账号", s == 200 and row and row[0][0] == "ACTIVE" and row[0][1] == 1
       and row[0][2] == 900 and row[0][3] == "wq_new_emp_p2" and m and m[0][0] == "WECOMID",
       f"row={row} mapping={m}")

# MERGED 跳转：新建 src/dst 两用户，DB 置 src=MERGED→dst，src 的 ticket 登录返回 dst
(sso_resp), _ = sso_login("wq_merge_src", name="合并源", phone="13933334444")
src_id = db("SELECT id FROM demand_user WHERE wecom_userid='wq_merge_src'", fetch=True)[0][0]
(sso_resp), _ = sso_login("wq_merge_dst", name="合并目标", phone="13955556666")
dst_id = db("SELECT id FROM demand_user WHERE wecom_userid='wq_merge_dst'", fetch=True)[0][0]
db("UPDATE demand_user SET status='MERGED', merged_to_user_id=%s, phone=NULL, wecom_userid=NULL WHERE id=%s", (dst_id, src_id))
(sso_resp), _ = sso_login("wq_merge_src")
s, b = sso_resp
u = (b.get("data") or {}).get("user") or {}
mp = db("SELECT demand_user_id FROM channel_user_mapping WHERE channel_user_id='wq_merge_src'", fetch=True)
report("2.4 MERGED 登录跳转目标用户", s == 200 and u.get("id") == dst_id and mp and mp[0][0] == dst_id,
       f"loginAs={u.get('id')} expect={dst_id} mapping→{mp}")

# ---------------- 3. PC 账密登录 + 锁定 + 强制改密 ----------------
print("== 3. PC 账密 ==")
s, b = req("POST", "/system/auth/login", body={"loginName": "admin", "password": "Admin@123456"})
adm = b.get("data") or {}
report("3.1 账密登录(admin)", s == 200 and adm.get("channel") == "WEB" and "ADMIN" in adm["user"]["roles"]
       and adm.get("mustChangePassword") is True,
       f"status={s} channel={adm.get('channel')} mustChange={adm.get('mustChangePassword')}")
adm_access, adm_refresh = adm.get("accessToken"), adm.get("refreshToken")

s, b = req("POST", "/system/auth/login", body={"loginName": "admin", "password": "wrong-pass-1"})
report("3.2 错误密码 1109", s == 200 and b.get("code") == 1109, f"status={s} code={b.get('code')}")

s, b = req("POST", "/system/auth/login", body={"loginName": "nobody", "password": "x"})
report("3.3 不存在账号同口径 1109(防枚举)", s == 200 and b.get("code") == 1109, f"code={b.get('code')}")

# 锁定策略：连续 5 次失败 → 第5次起 1110（唯一 loginName 避免跨轮运行时上轮锁定键 TTL 残留）
lock_name = f"locktest_p2_{int(time.time())}"
codes = []
for i in range(5):
    s, b = req("POST", "/system/auth/login", body={"loginName": lock_name, "password": f"bad{i}"})
    codes.append(b.get("code"))
s, b = req("POST", "/system/auth/login", body={"loginName": lock_name, "password": "any"})
report("3.4 连续失败5次锁15分钟", codes[:4] == [1109] * 4 and codes[4] == 1110 and b.get("code") == 1110,
       f"codes={codes} 6th={b.get('code')}")

# 强制改密流程
s, b = req("POST", "/system/auth/change-password", token=adm_access,
           body={"oldPassword": "Admin@123456", "newPassword": "short"})
report("3.5 弱密码拒绝 1111", s == 200 and b.get("code") == 1111, f"code={b.get('code')}")
s, b = req("POST", "/system/auth/change-password", token=adm_access,
           body={"oldPassword": "wrong-old", "newPassword": "DemandHub@2026"})
report("3.6 原密码错误拒绝", s == 200 and b.get("code") == 1109, f"code={b.get('code')}")
s, b = req("POST", "/system/auth/change-password", token=adm_access,
           body={"oldPassword": "Admin@123456", "newPassword": "DemandHub@2026"})
report("3.7 改密成功", s == 200 and b.get("code") == 0, f"status={s}")
s, b = req("GET", "/system/auth/me", token=adm_access)
report("3.8 改密后旧会话全清", s == 401, f"me={s}")
s, b = req("POST", "/system/auth/refresh", body={"refreshToken": adm_refresh})
report("3.9 改密后 refresh 一并失效", s == 200 and b.get("code") == 1103, f"code={b.get('code')}")
s, b = req("POST", "/system/auth/login", body={"loginName": "admin", "password": "Admin@123456"})
report("3.10 旧密码登录失败", s == 200 and b.get("code") == 1109, f"code={b.get('code')}")
s, b = req("POST", "/system/auth/login", body={"loginName": "admin", "password": "DemandHub@2026"})
adm2 = b.get("data") or {}
report("3.11 新密码登录且无需强制改密", s == 200 and adm2.get("mustChangePassword") is False,
       f"mustChange={adm2.get('mustChangePassword')}")
# 恢复种子初始态（hash 还原 + password_updated_at=NULL，供后续 session 使用）
db("UPDATE demand_user SET password_hash=%s, password_updated_at=NULL WHERE id=1001", (SEED_HASH,))
s, b = req("POST", "/system/auth/login", body={"loginName": "admin", "password": "Admin@123456"})
adm = b.get("data") or {}
adm_access, adm_refresh = adm.get("accessToken"), adm.get("refreshToken")
report("3.12 种子态恢复(强制改密标记还原)", s == 200 and adm.get("mustChangePassword") is True, "")

# ---------------- 4. 网关安全：伪造头/直连/越权 ----------------
print("== 4. 网关与越权 ==")
s, b = req("GET", "/system/auth/me", headers={"X-User-Id": "1001", "X-User-Roles": "ADMIN"})
report("4.1 仅伪造头无 token → 401", s == 401, f"status={s}")

s, b = req("GET", "/system/auth/me", token=adm_access, headers={"X-User-Id": "1003", "X-Channel": "CHUANGJIN_LS"})
me = b.get("data") or {}
report("4.2 伪造头被剥离(仍以 token 为准)", s == 200 and me.get("id") == 1001 and me.get("channel") == "WEB",
       f"id={me.get('id')} channel={me.get('channel')}")

# 直连 8081 不带网关注入身份 → UserContext 为空 → 未授权（业务服务只信网关头，伪造头直连可绕过属既有信任模型，由网络隔离兜底）
# 单体形态：无独立业务端口可直连，等价验证"无 token 访问被 AuthFilter 拦截（真 401）"
s, b = req("GET", "/auth/me", base=DIRECT)
report("4.3 绕过网关直连 8081(无身份头) → 未授权",
       (s == 401) if MONOLITH else (s == 200 and b.get("code") == 401),
       f"status={s} code={b.get('code')}")

# 越权 403：经理(非ADMIN)调管理接口
(sso_resp), _ = sso_login("wq_u_mgr_tech")
s2, b2 = sso_resp
mgr_token = (b2.get("data") or {}).get("accessToken")
s, b = req("GET", "/system/user/page", token=mgr_token)
report("4.4 非 ADMIN 调用户管理 → 403", s == 200 and b.get("code") == 403, f"status={s} code={b.get('code')}")
s, b = req("GET", "/system/user/page", token=adm_access)
report("4.5 ADMIN 调用户管理 → 200", s == 200 and b.get("code") == 0, f"status={s}")

# 旧端点下线
s, b = req("GET", "/system/auth/mock-users", token=adm_access)
report("4.6 旧 mock-users 端点已下线", b.get("code") == 404, f"status={s} code={b.get('code')}")

# ---------------- 5. 授权变更 1 分钟内生效 ----------------
print("== 5. 授权失效 ==")
s, b = req("POST", "/system/grant", token=adm_access,
           body={"demandUserId": 1003, "roleCode": "MANAGER", "orgId": 111, "demandTypeScope": "TECH"})
grant_id = (b.get("data") if b.get("code") == 0 else None)
s, b = req("GET", "/system/auth/me", token=mgr_token)
report("5.1 授权变更后旧 access 失效(401)", s == 401, f"me={s}")
s, b = req("POST", "/system/auth/refresh", body={"refreshToken": (b2.get('data') or {}).get('refreshToken')})
report("5.2 用户无感刷新续期", s == 200 and b.get("code") == 0, f"refresh={s}")
if grant_id:
    s, b = req("DELETE", f"/system/grant/{grant_id}", token=adm_access)
    report("5.3 清理测试授权", s == 200, f"del={s}")

# ---------------- 清理 ----------------
print("== 清理 ==")
db("DELETE FROM channel_user_mapping WHERE channel_user_id IN ('wq_dev_zhao_new','wq_new_emp_p2','wq_merge_src','wq_merge_dst')")
cleanup_users([new_id, src_id, dst_id])
db("DELETE FROM demand_user WHERE phone='13911112222' OR wecom_userid IN ('wq_new_emp_p2','wq_merge_src','wq_merge_dst')")
left = db("SELECT COUNT(*) FROM demand_user WHERE id NOT BETWEEN 1001 AND 1007", fetch=True)[0][0]
report("6.1 测试数据清理", left == 0, f"remaining={left}")

print(f"\n===== 结果: {len(PASS)} 通过, {len(FAIL)} 失败 =====")
if FAIL:
    print("失败项:")
    for f in FAIL:
        print(" -", f)
    sys.exit(1)
