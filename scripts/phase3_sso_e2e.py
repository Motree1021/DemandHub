# -*- coding: utf-8 -*-
"""P3 验收自测：创金零售 SSO 渠道适配器 + Mock 联调（开发计划 v2.0 任务 3.1~3.6）

覆盖验收标准：
- dev 下 Mock 五场景全通过（正常/票据过期/重放/字段缺失无手机/离职），ChuangjinLsSsoClient 走真实 HTTP 链路；
- AC-08 安全：签名错误/时间戳过期/nonce 重复被 mock verify 拒（40003），伪造 ticket/明文 userid 无法登录；
- AC-07 文案：过期/重放→"登录已失效，请从创金零售重新进入"；verify 停机→"登录服务暂时不可用，请稍后重试"；离职→"账号不可用，请联系管理员"；
- 3.5 部门未映射挂 900 不阻塞登录 + 校准清单落库累加；
- 3.2 熔断降级：verify 不可达连续失败熔断，快速失败不放行任何未核验身份，恢复后自愈。

运行前提：中间件栈 + gateway:8080 + system:8081 已启动；dev 库已执行 deploy/mysql/init/07-channel-sso-p3.sql。
"""
import hashlib
import hmac
import json
import sys
import time
import urllib.request
import urllib.error

import pymysql

BASE = "http://localhost:8080/api"
DIRECT = "http://localhost:8081/system"
VERIFY_PATH = "/openapi/demandhub/sso/verify"
MOCK_VERIFY_URL = DIRECT + "/mock-sso" + VERIFY_PATH
MYSQL = {"host": "localhost", "port": 3307, "user": "root", "password": "demandhub123", "database": "demandhub"}

PASS, FAIL = [], []
RUN = str(int(time.time()))[-8:]  # 本轮唯一后缀，保证用例幂等可重跑


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


def channel_config():
    rows = db("SELECT config_json FROM demand_channel WHERE channel_code='CHUANGJIN_LS'", fetch=True)
    return json.loads(rows[0][0])


def issue_ticket(channel_user_id, scenario=None, name=None, phone=None, dept_id=None, dept_name=None):
    body = {"channelUserId": channel_user_id}
    if scenario:
        body["scenario"] = scenario
    if name:
        body["name"] = name
    if phone:
        body["phone"] = phone
    if dept_id:
        body["deptId"] = dept_id
    if dept_name:
        body["deptName"] = dept_name
    s, b = req("POST", "/system/mock-sso/ticket", body=body)
    assert s == 200 and b["code"] == 0, f"签票失败: {s} {b}"
    return b["data"]["ticket"]


def channel_sso(ticket, channel="chuangjinls", state=None):
    q = f"?channel={channel}&ticket={ticket}" + (f"&state={state}" if state else "")
    return req("GET", "/system/auth/channel-sso" + q)


def sso_login(channel_user_id, state=None, **kw):
    ticket = issue_ticket(channel_user_id, **kw)
    return channel_sso(ticket, state=state), ticket


def mock_verify(ticket, app_key, app_secret, sign_override=None, ts_override=None,
                nonce=None, raw_body=None, base_url=MOCK_VERIFY_URL):
    """按 §3.3 契约直接调用 mock verify（server-to-server 语义，直连 8081）"""
    body = raw_body if raw_body is not None else json.dumps({"ticket": ticket}, separators=(",", ":"))
    ts = ts_override if ts_override is not None else str(int(time.time() * 1000))
    nonce = nonce or hashlib.md5(f"{time.time()}{ticket}".encode()).hexdigest()
    sts = "\n".join(["POST", VERIFY_PATH, app_key, ts, nonce, body])
    sign = sign_override or hmac.new(app_secret.encode(), sts.encode(), hashlib.sha256).hexdigest()
    r = urllib.request.Request(base_url, data=body.encode("utf-8"), method="POST")
    r.add_header("Content-Type", "application/json")
    r.add_header("X-App-Key", app_key)
    r.add_header("X-Timestamp", ts)
    r.add_header("X-Nonce", nonce)
    r.add_header("X-Sign", sign)
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8"))
        except Exception:
            return e.code, {}


def cleanup_user(channel_user_id):
    rows = db("SELECT demand_user_id FROM channel_user_mapping WHERE channel_user_id=%s",
              (channel_user_id,), fetch=True)
    for (uid,) in rows:
        db("DELETE FROM channel_user_mapping WHERE demand_user_id=%s", (uid,))
        db("DELETE FROM demand_role_grant WHERE demand_user_id=%s", (uid,))
        db("DELETE FROM demand_user WHERE id=%s", (uid,))


CFG = channel_config()
APP_KEY = CFG["app_key"]
# app_secret 落库为 ENC: 密文（AES-GCM，dev 主密钥）；e2e 作为"创金零售侧"持有明文密钥参与签名（dev 专用假值）
DEV_APP_SECRET_PLAINTEXT = "dev-chuangjinls-secret-9f3c7a21b5e8d0f4"
APP_SECRET = DEV_APP_SECRET_PLAINTEXT if CFG["app_secret"].startswith("ENC:") else CFG["app_secret"]
print(f"config: base_url={CFG['sso_verify_base_url']} app_key={APP_KEY} timeout_ms={CFG.get('timeout_ms')}"
      f" secret_stored={'ENC' if CFG['app_secret'].startswith('ENC:') else 'plain'}")

# ---------------- 0. 熔断自愈等待（上一轮熔断测试残留时等待恢复） ----------------
s, b = sso_login("wq_u_mgr_tech")[0]
if b.get("code") == 1102:
    print(".. 检测到熔断残留，等待 31s 恢复")
    time.sleep(31)
    s, b = sso_login("wq_u_mgr_tech")[0]
assert b.get("code") == 0, f"预热登录失败: {b}"

# ---------------- 1. Mock 五场景（真实 HTTP 链路） ----------------
print("== 1. Mock 五场景 ==")
(s, b), ticket = sso_login("wq_u_mgr_tech", state="st-" + RUN)
mgr = b.get("data") or {}
report("1.1 正常场景(HTTP链路回源)", s == 200 and b["code"] == 0 and mgr.get("channel") == "CHUANGJIN_LS"
       and mgr["user"]["id"] == 1003, f"status={s} code={b.get('code')} userId={mgr.get('user', {}).get('id')}")

s, b = channel_sso(ticket)
report("1.2 重放场景→1107+AC07文案", b.get("code") == 1107 and b.get("message") == "登录已失效，请从创金零售重新进入",
       f"code={b.get('code')} msg={b.get('message')}")

s, b = channel_sso("forged-ticket-" + RUN)
report("1.3 伪造ticket无法登录", b.get("code") == 1107, f"code={b.get('code')}")

(s, b), _ = sso_login("wq_u_mgr_tech", scenario="expired")
report("1.4 票据过期场景→1107+AC07文案", b.get("code") == 1107 and b.get("message") == "登录已失效，请从创金零售重新进入",
       f"code={b.get('code')} msg={b.get('message')}")

NP_UID = "wq_p3_nophone_" + RUN
(s, b), _ = sso_login(NP_UID, scenario="no_phone", name="无手机员工")
np_user = (b.get("data") or {}).get("user") or {}
np_db = db("SELECT id, phone, status, is_employee, primary_org_id FROM demand_user WHERE id=%s",
           (np_user.get("id") or 0,), fetch=True)
report("1.5 字段缺失(无手机)不阻塞登录+自动建号ACTIVE",
       b.get("code") == 0 and np_db and np_db[0][1] is None and np_db[0][2] == "ACTIVE" and np_db[0][3] == 1,
       f"code={b.get('code')} db={np_db}")

(s, b), _ = sso_login("wq_p3_resigned_" + RUN, scenario="resigned", name="离职员工")
report("1.6 离职场景→1113+AC07文案", b.get("code") == 1113 and b.get("message") == "账号不可用，请联系管理员",
       f"code={b.get('code')} msg={b.get('message')}")

# ---------------- 2. AC-08：mock verify 契约签名校验（server-to-server 直连） ----------------
print("== 2. verify 契约安全（AC-08） ==")
t = issue_ticket("wq_u_mgr_tech")
s, b = mock_verify(t, APP_KEY, APP_SECRET)
report("2.1 合法签名verify→errcode=0", s == 200 and b.get("errcode") == 0
       and (b.get("user") or {}).get("user_id") == "wq_u_mgr_tech", f"errcode={b.get('errcode')}")

s, b = mock_verify(t, APP_KEY, APP_SECRET, sign_override="0" * 64)
report("2.2 签名错误→40003", b.get("errcode") == 40003, f"errcode={b.get('errcode')}")

s, b = mock_verify(t, APP_KEY, APP_SECRET, ts_override=str(int(time.time() * 1000) + 10 * 60 * 1000))
report("2.3 时间戳偏差>5分钟→40003", b.get("errcode") == 40003, f"errcode={b.get('errcode')}")

fixed_nonce = "nonce-replay-" + RUN
s1, b1 = mock_verify(t, APP_KEY, APP_SECRET, nonce=fixed_nonce)
s2, b2 = mock_verify(t, APP_KEY, APP_SECRET, nonce=fixed_nonce)
report("2.4 nonce重复→40003", b1.get("errcode") in (0, 40001, 40002) and b2.get("errcode") == 40003,
       f"first={b1.get('errcode')} second={b2.get('errcode')}")

s, b = mock_verify(None, APP_KEY, APP_SECRET, raw_body="{}")
report("2.5 缺ticket参数→40005", b.get("errcode") == 40005, f"errcode={b.get('errcode')}")

t2 = issue_ticket("wq_u_mgr_tech")
s1, b1 = mock_verify(t2, APP_KEY, APP_SECRET)
s2, b2 = mock_verify(t2, APP_KEY, APP_SECRET)
report("2.6 票据一次性:消费后重放→40002", b1.get("errcode") == 0 and b2.get("errcode") == 40002,
       f"first={b1.get('errcode')} second={b2.get('errcode')}")

s, b = mock_verify("never-issued-" + RUN, APP_KEY, APP_SECRET)
report("2.7 未签发ticket→40001", b.get("errcode") == 40001, f"errcode={b.get('errcode')}")

s, b = mock_verify(t, "wrong-app-key", APP_SECRET)
report("2.8 app_key错误→40003", b.get("errcode") == 40003, f"errcode={b.get('errcode')}")

# ---------------- 3. 部门映射与校准清单（3.5） ----------------
print("== 3. 部门映射与校准清单 ==")
DEPT = "NODEPT" + RUN
UM_UID = "wq_p3_unmapped_" + RUN
UM_UID2 = "wq_p3_unmapped2_" + RUN
(s, b), _ = sso_login(UM_UID, name="未映射部门员工", dept_id=DEPT, dept_name="不存在部门")
um_user = (b.get("data") or {}).get("user") or {}
um_org = db("SELECT primary_org_id FROM demand_user WHERE id=%s", (um_user.get("id") or 0,), fetch=True)
cal = db("SELECT hit_count, dept_name FROM channel_dept_unmapped WHERE channel_code='CHUANGJIN_LS' AND dept_id=%s",
         (DEPT,), fetch=True)
report("3.1 未映射部门挂EXTERNAL(900)不阻塞登录", b.get("code") == 0 and um_org and um_org[0][0] == 900,
       f"code={b.get('code')} org={um_org}")
report("3.2 未映射记录回流校准清单", bool(cal) and cal[0][0] == 1, f"calibrate={cal}")

sso_login(UM_UID2, name="未映射部门员工2", dept_id=DEPT, dept_name="不存在部门")
cal2 = db("SELECT hit_count FROM channel_dept_unmapped WHERE channel_code='CHUANGJIN_LS' AND dept_id=%s",
          (DEPT,), fetch=True)
report("3.3 重复命中hit_count累加", bool(cal2) and cal2[0][0] >= 2, f"hit_count={cal2}")

# 已映射部门（赵一线 1006 所在 141 营业部一组 external_dept_id 查库验证不入校准清单）
mapped = db("SELECT external_dept_id FROM demand_org WHERE id=141", fetch=True)
if mapped and mapped[0][0]:
    (s, b), _ = sso_login("wq_u_reporter_1")
    cal3 = db("SELECT COUNT(*) FROM channel_dept_unmapped WHERE dept_id=%s", (mapped[0][0],), fetch=True)
    report("3.4 已映射部门不入校准清单", b.get("code") == 0 and cal3 and cal3[0][0] == 0,
           f"dept_id={mapped[0][0]} count={cal3}")

# ---------------- 4. 熔断降级（3.2：verify 不可达不放行任何未核验身份） ----------------
print("== 4. 熔断降级 ==")
ORIGINAL_CFG = db("SELECT config_json FROM demand_channel WHERE id=2", fetch=True)[0][0]
bad_cfg = json.dumps({**CFG, "sso_verify_base_url": "http://localhost:9999/system/mock-sso"},
                     ensure_ascii=False)
try:
    db("UPDATE demand_channel SET config_json=%s WHERE id=2", (bad_cfg,))
    codes = [channel_sso(issue_ticket("wq_u_mgr_tech"))[1].get("code") for _ in range(3)]
    report("4.1 verify不可达→1102快速失败", codes == [1102, 1102, 1102], f"codes={codes}")
    s, b = channel_sso(issue_ticket("wq_u_mgr_tech"))
    report("4.2 熔断开启不放行未核验身份+AC07维护文案",
           b.get("code") == 1102 and b.get("message") == "登录服务暂时不可用，请稍后重试",
           f"code={b.get('code')} msg={b.get('message')}")
finally:
    db("UPDATE demand_channel SET config_json=%s WHERE id=2", (ORIGINAL_CFG,))

print(".. 等待 31s 熔断窗口过后验证自愈")
time.sleep(31)
s, b = sso_login("wq_u_mgr_tech")[0]
report("4.3 恢复后熔断自愈登录正常", b.get("code") == 0, f"code={b.get('code')}")

# ---------------- 5. 明文身份不可伪造（AC-08） ----------------
print("== 5. 明文身份伪造拦截 ==")
s, b = channel_sso("wq_u_mgr_tech")
report("5.1 明文userid当ticket无法登录", b.get("code") == 1107, f"code={b.get('code')}")
s, b = channel_sso("wq_u_mgr_tech", channel="WEB")
report("5.2 WEB渠道不支持票据登录", b.get("code") == 400, f"code={b.get('code')}")

# ---------------- 清理 ----------------
print("== 清理 ==")
for uid in (NP_UID, UM_UID, UM_UID2):
    cleanup_user(uid)
db("DELETE FROM channel_dept_unmapped WHERE dept_id=%s", (DEPT,))
left = db("SELECT COUNT(*) FROM channel_dept_unmapped WHERE dept_id=%s", (DEPT,), fetch=True)[0][0]
left_u = db("SELECT COUNT(*) FROM demand_user WHERE wecom_userid IN (%s,%s,%s)", (NP_UID, UM_UID, UM_UID2),
            fetch=True)[0][0]
report("C.1 测试数据自清理", left == 0 and left_u == 0, f"calibrate={left} users={left_u}")

print(f"\n==== 结果: PASS={len(PASS)} FAIL={len(FAIL)} ====")
if FAIL:
    print("失败用例:")
    for name in FAIL:
        print(" -", name)
sys.exit(1 if FAIL else 0)
