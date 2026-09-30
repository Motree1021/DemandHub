# -*- coding: utf-8 -*-
"""P6 验收自测：测试环境（test profile）部署 + 性能与安全复核（开发计划 v2.0 任务 6.1/6.5）。

打 demandhub-test 栈（deploy/docker-compose.test.yml）：CHANNEL_SSO_MOCK=false，
verify 回源走 CHANNEL_LS_* 环境变量 → contract-mock 容器（契约级 Mock，严格验签，§3.3 同一契约）。
这是与 dev 内置 Mock 的本质差异：签名严格性由独立服务强制校验，覆盖生产真实链路。

覆盖：
- 6.1 test profile 全链路：env 覆盖生效（config_json 仍指向 dev Mock 但被绕过）；
  契约 Mock 签票 → channel-sso 免登 → 自动建号 → 提报落 CHUANGJIN_LS → PC 来源筛选可见；nginx 同域可达。
- AC-08：契约层签名错/时间戳偏差>5min/nonce 重放均被 40003 拒；重放 ticket 上游 40002 → 1107 AC07 文案。
- AC-07：过期/离职/缺必填(40005)/伪造 ticket/无 ticket 各有明确错误码与文案，不放行。
- 防伪复核（开发计划行 201）：URL 拼 userid/name 不读取；from 篡改不改身份；请求体 channel=WEB 落库仍会话渠道；
  无 token 直调提交 401；伪造 X-User-Id 头被网关剥离。
- 6.5：verify 超时(3s)快速失败 → 连续 3 次熔断 → 熔断期 fail-fast 不放行不耗票 → 31s 自愈；
  PC 账密 5 次失败锁定(1110)；无角色会话访问管理接口 403。

运行前提：docker compose -f deploy/docker-compose.test.yml up -d --build 全部 healthy。
环境变量可覆盖：P6_BASE / P6_NGINX / P6_MOCK / P6_MYSQL_PORT / CHANNEL_LS_APP_SECRET（契约直调验签用）。
"""
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import urllib.error

import pymysql

BASE = os.environ.get("P6_BASE", "http://localhost:8180/api")
NGINX = os.environ.get("P6_NGINX", "http://localhost:8088")
MOCK = os.environ.get("P6_MOCK", "http://localhost:8099")
VERIFY_URL = MOCK + "/openapi/demandhub/sso/verify"
APP_KEY = os.environ.get("CHANNEL_LS_APP_KEY", "demandhub-test")
APP_SECRET = os.environ.get("CHANNEL_LS_APP_SECRET", "chuangjinls-test-secret-please-change-me")
MYSQL = {"host": "localhost", "port": int(os.environ.get("P6_MYSQL_PORT", "3317")),
         "user": "root", "password": "demandhub123", "database": "demandhub"}

PASS, FAIL = [], []
RUN = str(int(time.time()))[-8:]
CJ_USER = f"cj_p6_{RUN}"   # 契约渠道用户（企微 userid 形态），本轮唯一


def report(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}")


def req(method, path, token=None, body=None, headers=None, base=BASE, timeout=30):
    url = base + path
    data = json.dumps(body).encode("utf-8") if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", f"Bearer {token}")
    for k, v in (headers or {}).items():
        r.add_header(k, v)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
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


def raw_get(url, timeout=15):
    """拉取非 JSON 资源（nginx 静态页），返回 (status, text)"""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")


def issue_ticket(channel_user_id=CJ_USER, scenario=None, name=None):
    body = {"channelUserId": channel_user_id}
    if scenario:
        body["scenario"] = scenario
    if name:
        body["name"] = name
    s, b = req("POST", "/ticket", body=body, base=MOCK)
    assert s == 200 and b.get("ticket"), f"契约Mock签票失败: {s} {b}"
    return b["ticket"]


def channel_sso(ticket, channel="chuangjinls", extra_qs="", timeout=30):
    return req("GET", f"/system/auth/channel-sso?channel={channel}&ticket={ticket}{extra_qs}", timeout=timeout)


def sso_token(channel_user_id=CJ_USER, extra_qs=""):
    s, b = channel_sso(issue_ticket(channel_user_id), extra_qs=extra_qs)
    assert s == 200 and b["code"] == 0, f"SSO 登录失败: {s} {b}"
    return b["data"]["accessToken"], b["data"]["user"]


def raw_verify(sign_secret=APP_SECRET, timestamp=None, nonce="nonce" + RUN, ticket="x", app_key=APP_KEY):
    """直调契约 verify（AC-08 契约层负例：签名/时间戳/nonce 由服务端强制校验）"""
    import uuid
    ts = str(timestamp if timestamp is not None else int(time.time() * 1000))
    body = json.dumps({"ticket": ticket})
    s2s = "\n".join(["POST", "/openapi/demandhub/sso/verify", app_key, ts, nonce, body])
    sign = hmac.new(sign_secret.encode(), s2s.encode(), hashlib.sha256).hexdigest()
    r = urllib.request.Request(VERIFY_URL, data=body.encode(), method="POST")
    r.add_header("Content-Type", "application/json")
    r.add_header("X-App-Key", app_key)
    r.add_header("X-Timestamp", ts)
    r.add_header("X-Nonce", nonce)
    r.add_header("X-Sign", sign)
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode("utf-8", errors="replace"))


# ---------------- 0. test profile 前置 ----------------
print("== 0. test profile 前置（内置Mock下线 + admin 免强制改密） ==")
s, b = req("POST", "/system/mock-sso/ticket", body={"channelUserId": "x"})
report("0.1 内置Mock端点不暴露(CHANNEL_SSO_MOCK=false)", not (s == 200 and b.get("code") == 0),
       f"status={s} code={b.get('code')}")

db("UPDATE demand_user SET password_updated_at=NOW(3) WHERE id=1001")  # 新库首登强制改密，置为已改（幂等）
s, b = req("POST", "/system/auth/login", body={"loginName": "admin", "password": "Admin@123456"})
adm_tok = (b.get("data") or {}).get("accessToken")
report("0.2 PC admin 账密登录(test库)", s == 200 and b["code"] == 0 and adm_tok, f"code={b.get('code')}")

# ---------------- 1. 6.1 test profile 全链路 ----------------
print("== 1. test profile 全链路（env覆盖→契约Mock→免登→提报→PC可见） ==")
tok1, user1 = sso_token()
uid1 = user1.get("id")
report("1.1 契约Mock免登建号(channel=CHUANGJIN_LS)", uid1 and user1.get("name"),
       f"userId={uid1} name={user1.get('name')}")

tok2, user2 = sso_token()
report("1.2 同人同号(AC-03)", user2.get("id") == uid1, f"idA={uid1} idB={user2.get('id')}")

s, b = req("GET", "/system/auth/me", token=tok1)
report("1.3 me返回会话渠道", s == 200 and (b.get("data") or {}).get("channel") == "CHUANGJIN_LS"
       and (b.get("data") or {}).get("id") == uid1, f"channel={(b.get('data') or {}).get('channel')}")

s, b = req("POST", "/demand/demand/submit", token=tok1, body={
    "title": f"P6E2E-提报{RUN}", "content": "P6 test profile 全链路", "demandTypeCode": "TECH"})
d1 = (b.get("data") or {}).get("id")
db_ch1 = db("SELECT channel FROM demand WHERE id=%s", (d1,), fetch=True)[0][0] if d1 else None
report("1.4 提报落库CHUANGJIN_LS", s == 200 and b["code"] == 0 and db_ch1 == "CHUANGJIN_LS", f"db={db_ch1}")

# ADMIN 已放行全部业务操作与数据范围（P12 产品决策），此处沿用 EXECUTIVE(1002，种子映射 wq_u_exec_001) 验证业务角色视角
exec_tok, _ = sso_token("wq_u_exec_001")
s, b = req("GET", "/demand/demand/page?channel=CHUANGJIN_LS&size=100", token=exec_tok)
titles = [r.get("title") for r in ((b.get("data") or {}).get("records") or [])]
report("1.5 PC来源筛选可见(创金零售)", f"P6E2E-提报{RUN}" in titles, f"hits={len(titles)}")

s_h5, html_h5 = raw_get(NGINX + "/h5/")
s_pc, html_pc = raw_get(NGINX + "/")
s3, b3 = req("GET", "/api/system/ping", base=NGINX)
report("1.6 nginx同域(H5/PC/api可达)", s_h5 == 200 and "<" in html_h5 and s_pc == 200 and "<" in html_pc
       and s3 == 200 and b3.get("code") == 0, f"h5={s_h5} pc={s_pc} api={s3}/{b3.get('code')}")

# ---------------- 2. AC-08 签名安全（契约层） ----------------
print("== 2. AC-08 签名/时间戳/nonce（契约Mock强制验签） ==")
r = raw_verify(sign_secret="wrong-secret")
report("2.1 签名错误被据(40003)", r.get("errcode") == 40003, f"errcode={r.get('errcode')}")
r = raw_verify(timestamp=int(time.time() * 1000) - 6 * 60 * 1000, nonce="oldts" + RUN)
report("2.2 时间戳偏差>5min被据(40003)", r.get("errcode") == 40003, f"errcode={r.get('errcode')}")
r1 = raw_verify(nonce="replay" + RUN)
r2 = raw_verify(nonce="replay" + RUN)  # 同 nonce+同签名重放
report("2.3 nonce重放被据(40003)", r1.get("errcode") != 40003 and r2.get("errcode") == 40003,
       f"first={r1.get('errcode')} replay={r2.get('errcode')}")
report("2.4 我方客户端签名通过严格验签(1.1成功即证据)", uid1 is not None, "")

# ---------------- 3. AC-07 异常态（test profile） ----------------
print("== 3. AC-07 异常态 ==")
t_replay = issue_ticket()
s, b = channel_sso(t_replay)
s, b = channel_sso(t_replay)  # 重放：上游 40002 → 1107
report("3.1 重放ticket→1107(上游40002)", s == 200 and b.get("code") == 1107
       and "重新进入" in (b.get("message") or ""), f"code={b.get('code')}")
s, b = channel_sso(issue_ticket(scenario="expired"))
report("3.2 过期ticket(AC07文案)", s == 200 and b.get("code") == 1107
       and "重新进入" in (b.get("message") or ""), f"code={b.get('code')}")
s, b = channel_sso(issue_ticket(scenario="resigned"))
report("3.3 离职账号(AC07文案)", s == 200 and b.get("code") == 1113
       and "联系管理员" in (b.get("message") or ""), f"code={b.get('code')}")
s, b = channel_sso(issue_ticket(scenario="missing_name"))
report("3.4 缺必填姓名(40005→1107)", s == 200 and b.get("code") == 1107
       and "重新进入" in (b.get("message") or ""), f"code={b.get('code')}")
s, b = channel_sso("forged-ticket-" + RUN)
report("3.5 伪造ticket被拒", s == 200 and b.get("code") == 1107, f"code={b.get('code')}")
s, b = req("GET", "/system/auth/channel-sso?channel=chuangjinls")
report("3.6 无ticket参数被拒", s == 200 and b.get("code") in (400, 500), f"code={b.get('code')}")

# ---------------- 4. 防伪复核（开发计划行201） ----------------
print("== 4. 防伪复核 ==")
forged_qs = "&userid=wq_u_admin_001&name=" + urllib.parse.quote("伪造管理员") + "&phone=13800000000"
s, b = channel_sso(issue_ticket(), extra_qs=forged_qs)
u41 = ((b.get("data") or {}).get("user") or {})
report("4.1 URL明文身份无效(仍票据绑定)", s == 200 and b["code"] == 0 and u41.get("id") == uid1
       and u41.get("name") != "伪造管理员", f"userId={u41.get('id')} name={u41.get('name')}")
s, b = channel_sso(issue_ticket(), channel="hacked")
report("4.2 from篡改(hacked)被拒", s == 200 and b.get("code") == 400, f"code={b.get('code')}")
s, b = req("POST", "/demand/demand/submit", token=tok1, body={
    "title": f"P6E2E-防伪{RUN}", "content": "请求体传channel=WEB", "demandTypeCode": "TECH",
    "channel": "WEB"})
d43 = (b.get("data") or {}).get("id")
db_ch43 = db("SELECT channel FROM demand WHERE id=%s", (d43,), fetch=True)[0][0] if d43 else None
report("4.3 请求体channel=WEB落库仍CHUANGJIN_LS", s == 200 and b["code"] == 0 and db_ch43 == "CHUANGJIN_LS",
       f"db={db_ch43}")
s, b = req("POST", "/demand/demand/submit", body={
    "title": f"P6E2E-无token{RUN}", "content": "x", "demandTypeCode": "TECH"})
report("4.4 无token直调提交→401", s == 401, f"status={s}")
s, b = req("GET", "/system/auth/me", headers={"X-User-Id": "1001", "X-User-Roles": "ADMIN"})
report("4.5a 仅伪造头无token→401", s == 401, f"status={s}")
s, b = req("GET", "/system/auth/me", token=tok1, headers={"X-User-Id": "1001", "X-Channel": "WEB"})
me45 = b.get("data") or {}
report("4.5b 伪造头被剥离(仍以token为准)", s == 200 and me45.get("id") == uid1
       and me45.get("channel") == "CHUANGJIN_LS", f"id={me45.get('id')} channel={me45.get('channel')}")
s, b = channel_sso(issue_ticket(f"cj_p6_dept_{RUN}", scenario="dept_unmapped", name="未映射员工"))
ok46 = s == 200 and b.get("code") == 0
time.sleep(0.5)
row46 = db("SELECT hit_count FROM channel_dept_unmapped WHERE channel_code='CHUANGJIN_LS' AND dept_id='D_UNMAPPED_999'",
           fetch=True)
report("4.6 部门未映射不阻塞+校准清单落库", ok46 and len(row46) > 0, f"login={b.get('code')} rows={len(row46)}")

# ---------------- 5. 6.5 verify 超时降级与熔断 ----------------
print("== 5. verify 超时(3s)快速失败 → 熔断 → 自愈 ==")
for i in range(3):
    s, b = channel_sso(issue_ticket(scenario="slow"), timeout=15)
    if b.get("code") != 1102:
        break
report("5.1 slow场景3s超时→1102(AC07文案)", b.get("code") == 1102 and "稍后重试" in (b.get("message") or ""),
       f"code={b.get('code')}")
t_normal = issue_ticket()
s, b = channel_sso(t_normal)  # 熔断开启期：fail-fast 不放行、不回源（票据不被消耗）
report("5.2 熔断期fail-fast(不放行未核验身份)", s == 200 and b.get("code") == 1102, f"code={b.get('code')}")
print(".. 等待 31s 熔断恢复")
time.sleep(31)
s, b = channel_sso(t_normal)  # 同一票据重试：证明 fail-fast 未消耗 + 熔断自愈
report("5.3 熔断自愈+fail-fast未耗票", s == 200 and b.get("code") == 0, f"code={b.get('code')}")

# ---------------- 6. 6.5 登录锁定与越权 ----------------
print("== 6. 登录锁定 + 越权 403 ==")
lock_name = f"locktest_p6_{int(time.time())}"
for i in range(4):
    req("POST", "/system/auth/login", body={"loginName": lock_name, "password": f"bad{i}"})
s, b = req("POST", "/system/auth/login", body={"loginName": lock_name, "password": "any"})
report("6.1 连续5次失败锁定(1110)", s == 200 and b.get("code") == 1110, f"code={b.get('code')}")

s, b = req("GET", "/system/user/page?current=1&size=1", token=tok1)
report("6.2 无角色会话访问管理接口→403", s == 200 and b.get("code") == 403, f"code={b.get('code')}")

# ---------------- 7. 清理 ----------------
print("== 7. 清理 ==")
db("DELETE FROM demand_transition_log WHERE demand_id IN (SELECT id FROM demand WHERE title LIKE %s)", (f"P6E2E-%{RUN}%",))
db("DELETE FROM demand_ext_tech WHERE demand_id IN (SELECT id FROM demand WHERE title LIKE %s)", (f"P6E2E-%{RUN}%",))
db("DELETE FROM demand WHERE title LIKE %s", ("P6E2E-%",))
db("DELETE FROM channel_dept_unmapped WHERE dept_id='D_UNMAPPED_999'")
db("DELETE FROM channel_user_mapping WHERE channel_user_id LIKE %s", ("cj\\_p6\\_%",))
db("DELETE FROM demand_user WHERE wecom_userid LIKE %s", ("cj\\_p6\\_%",))
left = db("SELECT COUNT(*) FROM demand WHERE title LIKE %s", ("P6E2E%",), fetch=True)[0][0]
left_u = db("SELECT COUNT(*) FROM demand_user WHERE wecom_userid LIKE %s", ("cj\\_p6\\_%",), fetch=True)[0][0]
report("7.1 测试数据清理", left == 0 and left_u == 0, f"demand={left} user={left_u}")

print(f"\n===== P6 验收：{len(PASS)} 通过 / {len(FAIL)} 失败 =====")
if FAIL:
    print("失败项：")
    for f in FAIL:
        print(" -", f)
    sys.exit(1)
