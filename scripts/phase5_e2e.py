# -*- coding: utf-8 -*-
"""P5 验收自测：H5 嵌入创金零售（开发计划 v2.0 任务 5.1~5.6，SRS AC-03~06）

覆盖：
- 5.5 渠道落库（核心）：SSO 会话提报/草稿落 CHUANGJIN_LS；PC 账密会话落 WEB；
  防伪自测——请求体传 channel（'H5'/'CHUANGJIN_LS'）均不能改变落库渠道（只信会话 claims 经网关注入的 X-Channel）。
- 5.1 票据链路安全：from 篡改（channel=hacked/WEB）被拒；无 ticket/伪造 ticket 被拒并复用 AC07 文案；
  URL 明文身份（userid/name 拼接）不影响登录身份（仅认票据绑定用户）。
- AC-03：同一人多次持票进入为同一账号。
- 5.6 站内信/红点：未读数与消息列表接口对 H5 渠道会话可用。
- 5.4 工程：H5 构建产物引用 /h5/ 前缀；nginx 同域 /h5/ 分流且无 81 端口；vite base='/h5/'。

运行前提：中间件栈 + gateway:8080 + system:8081 + demand:8082（P5 代码）已启动；H5 已执行 npm run build。
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import urllib.error

import pymysql

BASE = "http://localhost:8080/api"
MYSQL = {"host": "localhost", "port": 3307, "user": "root", "password": "demandhub123", "database": "demandhub"}
H5_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend", "h5"))
NGINX_CONF = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend", "nginx.conf"))

PASS, FAIL = [], []
RUN = str(int(time.time()))[-8:]


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


def issue_ticket(channel_user_id, scenario=None):
    body = {"channelUserId": channel_user_id}
    if scenario:
        body["scenario"] = scenario
    s, b = req("POST", "/system/mock-sso/ticket", body=body)
    assert s == 200 and b["code"] == 0, f"签票失败: {s} {b}"
    return b["data"]["ticket"]


def channel_sso(ticket, channel="chuangjinls", extra_qs=""):
    return req("GET", f"/system/auth/channel-sso?channel={channel}&ticket={ticket}{extra_qs}")


def sso_token(channel_user_id, extra_qs=""):
    s, b = channel_sso(issue_ticket(channel_user_id), extra_qs=extra_qs)
    assert s == 200 and b["code"] == 0, f"SSO 登录失败: {s} {b}"
    return b["data"]["accessToken"], b["data"]["user"]


def pc_token(login_name, password):
    s, b = req("POST", "/system/auth/login", body={"loginName": login_name, "password": password})
    assert s == 200 and b["code"] == 0, f"账密登录失败: {s} {b}"
    return b["data"]["accessToken"], b["data"]["user"]


# ---------------- 0. 预热（熔断残留自愈） ----------------
s, b = channel_sso(issue_ticket("wq_u_reporter_1"))
if b.get("code") == 1102:
    print(".. 检测到熔断残留，等待 31s 恢复")
    time.sleep(31)
    s, b = channel_sso(issue_ticket("wq_u_reporter_1"))
assert b.get("code") == 0, f"预热登录失败: {b}"

# ---------------- 1. 5.5 渠道落库（防伪核心） ----------------
print("== 1. 渠道落库：会话为准，请求体伪造无效 ==")
h5_tok, h5_user = sso_token("wq_u_reporter_1")  # 1006 赵一线（无角色，可提报）

# 1.1 SSO 会话提报：请求体故意带 channel='H5' → 落库必须为 CHUANGJIN_LS
s, b = req("POST", "/demand/demand/submit", token=h5_tok, body={
    "title": f"P5E2E-SSO提报{RUN}", "content": "P5 渠道落库验收", "demandTypeCode": "TECH",
    "channel": "H5"})
d1 = (b.get("data") or {}).get("id")
ch1 = (b.get("data") or {}).get("channel")
db_ch1 = db("SELECT channel FROM demand WHERE id=%s", (d1,), fetch=True)[0][0] if d1 else None
report("1.1 SSO提报落库CHUANGJIN_LS(请求体H5无效)", s == 200 and b["code"] == 0
       and ch1 == "CHUANGJIN_LS" and db_ch1 == "CHUANGJIN_LS", f"resp={ch1} db={db_ch1}")

# 1.2 SSO 会话草稿：请求体故意带 channel='H5' → 落库必须为 CHUANGJIN_LS
s, b = req("POST", "/demand/draft/save", token=h5_tok, body={
    "formPayload": json.dumps({"title": f"P5E2E-草稿{RUN}"}), "channel": "H5"})
draft1 = (b.get("data") or {}).get("id")
dch1 = (b.get("data") or {}).get("channel")
db_dch1 = db("SELECT channel FROM demand_draft WHERE id=%s", (draft1,), fetch=True)[0][0] if draft1 else None
report("1.2 SSO草稿落库CHUANGJIN_LS(请求体H5无效)", s == 200 and b["code"] == 0
       and dch1 == "CHUANGJIN_LS" and db_dch1 == "CHUANGJIN_LS", f"resp={dch1} db={db_dch1}")

# 1.3 PC 账密会话提报：请求体伪造 channel='CHUANGJIN_LS' → 落库必须为 WEB
pc_tok, pc_user = pc_token("admin", "Admin@123456")
s, b = req("POST", "/demand/demand/submit", token=pc_tok, body={
    "title": f"P5E2E-PC提报{RUN}", "content": "P5 渠道落库验收", "demandTypeCode": "TECH",
    "channel": "CHUANGJIN_LS"})
d2 = (b.get("data") or {}).get("id")
db_ch2 = db("SELECT channel FROM demand WHERE id=%s", (d2,), fetch=True)[0][0] if d2 else None
report("1.3 PC提报落库WEB(请求体伪造无效)", s == 200 and b["code"] == 0 and db_ch2 == "WEB", f"db={db_ch2}")

# 1.4 PC 账密会话草稿：伪造 channel → WEB
s, b = req("POST", "/demand/draft/save", token=pc_tok, body={
    "formPayload": json.dumps({"title": f"P5E2E-PC草稿{RUN}"}), "channel": "CHUANGJIN_LS"})
draft2 = (b.get("data") or {}).get("id")
db_dch2 = db("SELECT channel FROM demand_draft WHERE id=%s", (draft2,), fetch=True)[0][0] if draft2 else None
report("1.4 PC草稿落库WEB(伪造无效)", s == 200 and b["code"] == 0 and db_dch2 == "WEB", f"db={db_dch2}")

# 1.5 草稿转化正式需求：渠道仍以提交时会话为准
s, b = req("POST", "/demand/demand/submit", token=h5_tok, body={
    "draftId": draft1, "title": f"P5E2E-草稿转化{RUN}", "content": "草稿转化", "demandTypeCode": "TECH"})
d3 = (b.get("data") or {}).get("id")
db_ch3 = db("SELECT channel FROM demand WHERE id=%s", (d3,), fetch=True)[0][0] if d3 else None
report("1.5 草稿转化提报落库CHUANGJIN_LS", s == 200 and b["code"] == 0 and db_ch3 == "CHUANGJIN_LS", f"db={db_ch3}")

# ---------------- 2. 5.1 票据链路安全 ----------------
print("== 2. 票据链路安全（from 篡改/伪造 ticket/明文身份） ==")
# 2.1 from 篡改：channel=hacked → 后端白名单拒绝
s, b = channel_sso(issue_ticket("wq_u_reporter_1"), channel="hacked")
report("2.1 from篡改(hacked)被拒", s == 200 and b.get("code") == 400, f"code={b.get('code')}")
# 2.2 channel=WEB 不支持票据登录
s, b = channel_sso(issue_ticket("wq_u_reporter_1"), channel="WEB")
report("2.2 WEB渠道票据登录被拒", s == 200 and b.get("code") == 400, f"code={b.get('code')}")
# 2.3 伪造 ticket → 1107 + AC07 文案
s, b = channel_sso("forged-ticket-" + RUN)
report("2.3 伪造ticket被拒(AC07文案)", s == 200 and b.get("code") == 1107
       and "重新进入" in (b.get("message") or ""), f"code={b.get('code')} msg={b.get('message')}")
# 2.4 过期 ticket → 1107 同文案
s, b = channel_sso(issue_ticket("wq_u_reporter_1", scenario="expired"))
report("2.4 过期ticket(AC07文案)", s == 200 and b.get("code") == 1107
       and "重新进入" in (b.get("message") or ""), f"code={b.get('code')} msg={b.get('message')}")
# 2.5 离职账号 → 1113 文案
s, b = channel_sso(issue_ticket("wq_u_reporter_1", scenario="resigned"))
report("2.5 离职账号(AC07文案)", s == 200 and b.get("code") == 1113
       and "联系管理员" in (b.get("message") or ""), f"code={b.get('code')} msg={b.get('message')}")
# 2.6 URL 明文身份拼接：userid/name 不影响登录身份（仅认票据绑定用户 1006）
forged_qs = "&userid=wq_u_admin_001&name=" + urllib.parse.quote("伪造管理员") + "&phone=13800000000"
s, b = channel_sso(issue_ticket("wq_u_reporter_1"), extra_qs=forged_qs)
uid26 = ((b.get("data") or {}).get("user") or {}).get("id")
ch26 = (b.get("data") or {}).get("channel")
report("2.6 URL明文身份无效(仍票据绑定用户)", s == 200 and b["code"] == 0 and uid26 == 1006
       and ch26 == "CHUANGJIN_LS", f"userId={uid26} channel={ch26}")
# 2.7 无 ticket 参数 → 400
s, b = req("GET", "/system/auth/channel-sso?channel=chuangjinls")
report("2.7 无ticket参数被拒", s == 200 and b.get("code") in (400, 500), f"code={b.get('code')}")

# ---------------- 3. AC-03 同一人多次进入同一账号 ----------------
print("== 3. AC-03 重复进入同人同号 ==")
tok_a, user_a = sso_token("wq_u_reporter_1")
tok_b, user_b = sso_token("wq_u_reporter_1")
report("3.1 同一人多次进入同一账号", user_a["id"] == user_b["id"] == 1006,
       f"idA={user_a['id']} idB={user_b['id']}")
s, b = req("GET", "/system/auth/me", token=tok_b)
report("3.2 me返回渠道与身份", s == 200 and b["code"] == 0
       and (b.get("data") or {}).get("channel") == "CHUANGJIN_LS"
       and (b.get("data") or {}).get("id") == 1006, f"channel={(b.get('data') or {}).get('channel')}")

# ---------------- 4. 5.6 站内信/红点（D6 一期口径） ----------------
print("== 4. 站内信/红点 ==")
s, b = req("GET", "/notification/mine/unread-count", token=h5_tok)
uc = (b.get("data") or {}).get("count")
report("4.1 未读数接口可用(H5渠道会话)", s == 200 and b["code"] == 0 and uc is not None, f"count={uc}")
s, b = req("GET", "/notification/mine?current=1&size=10", token=h5_tok)
recs = (b.get("data") or {}).get("records")
report("4.2 消息列表接口可用(H5渠道会话)", s == 200 and b["code"] == 0 and recs is not None,
       f"rows={len(recs) if recs is not None else '-'}")

# ---------------- 5. 5.4 工程产物检查 ----------------
print("== 5. 工程与部署产物 ==")
idx_path = os.path.join(H5_DIR, "dist", "index.html")
idx = open(idx_path, encoding="utf-8").read() if os.path.exists(idx_path) else ""
report("5.1 H5构建产物引用/h5/前缀", "/h5/assets/" in idx, idx_path)

vite_cfg = open(os.path.join(H5_DIR, "vite.config.ts"), encoding="utf-8").read()
report("5.2 vite base='/h5/'", "base: '/h5/'" in vite_cfg, "")

router_src = open(os.path.join(H5_DIR, "src", "router", "index.ts"), encoding="utf-8").read()
report("5.3 路由base=/h5/", "createWebHistory('/h5/')" in router_src, "")

nginx = open(NGINX_CONF, encoding="utf-8").read()
report("5.4 nginx同域/h5/分流且无81端口", "location /h5/" in nginx and "listen 81" not in nginx, "")

report_src = open(os.path.join(H5_DIR, "src", "views", "report", "index.vue"), encoding="utf-8").read()
report("5.5 H5无写死channel('H5')", "'H5'" not in report_src, "")

# ---------------- 6. 清理 ----------------
print("== 6. 清理 ==")
db("DELETE FROM demand_transition_log WHERE demand_id IN (SELECT id FROM demand WHERE title LIKE %s)", (f"P5E2E-%{RUN}%",))
db("DELETE FROM demand_ext_tech WHERE demand_id IN (SELECT id FROM demand WHERE title LIKE %s)", (f"P5E2E-%{RUN}%",))
db("DELETE FROM demand WHERE title LIKE %s", (f"P5E2E-%",))
db("DELETE FROM demand_draft WHERE form_payload LIKE %s", (f"%P5E2E-%",))
left = db("SELECT COUNT(*) FROM demand WHERE title LIKE %s", ("P5E2E%",), fetch=True)[0][0]
left_d = db("SELECT COUNT(*) FROM demand_draft WHERE form_payload LIKE %s", ("%P5E2E-%",), fetch=True)[0][0]
report("6.1 测试数据清理", left == 0 and left_d == 0, f"demand={left} draft={left_d}")

print(f"\n===== P5 验收：{len(PASS)} 通过 / {len(FAIL)} 失败 =====")
if FAIL:
    print("失败项：")
    for f in FAIL:
        print(" -", f)
    sys.exit(1)
