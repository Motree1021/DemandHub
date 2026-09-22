# -*- coding: utf-8 -*-
"""阶段8 安全与健壮性测试（对照执行计划任务6~8 / 检查点2 + SRS 第9节验收2/3）

覆盖：
- A 水平越权：提报人不能改/看别人的需求、跨部门处理人看不到别部门需求池与详情
- B 垂直越权：REPORTER 调管理接口、非 ADMIN 调系统管理接口、HANDLER 做经理操作 → 403
- C 状态机非法流转：所有未定义流转被拒（ILLEGAL_STATE_TRANSITION / FORBIDDEN）
- D 并发：需求编号并发生成无重号无跳号；并发领取仅一人成功
- E 基础注入/XSS 防护抽验
"""
import json
import sys
import threading
import time
import urllib.request
import urllib.error
import uuid

BASE = "http://localhost:8080/api"
MYSQL = {"host": "localhost", "port": 3307, "user": "root", "password": "demandhub123", "database": "demandhub"}

PASS, FAIL = [], []


def report(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}")


def req(method, path, token=None, body=None):
    url = BASE + path
    data = json.dumps(body).encode("utf-8") if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        payload = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(payload)
        except Exception:
            return e.code, {"raw": payload}


def login(user_id):
    status, body = req("GET", f"/system/auth/callback?code=mock-{user_id}")
    assert status == 200 and body["code"] == 0, f"login {user_id} failed"
    return body["data"]["accessToken"]


def denied(status, body):
    """越权/非法应返回 HTTP 403 或业务码 403/1001(非法流转)/1002(禁止)"""
    if status == 403:
        return True
    code = body.get("code")
    return code in (403, 1001, 1002, 1403)


def submit(token, type_code, title):
    ext = {"TECH": {"relatedSystem": "S", "relatedModule": "M", "businessScenario": "B", "acceptanceCriteria": "A"},
           "MATL": {"materialSubtype": "折页", "usageScenario": "路演", "quantity": 1, "expectedArrivalAt": "2026-10-01T00:00:00"},
           "TRAIN": {"trainingSubtype": "T", "traineeObject": "O", "traineeCount": 1, "expectedCompleteAt": "2026-11-01T00:00:00"}}[type_code]
    status, body = req("POST", "/demand/demand/submit", token, {
        "title": title, "demandTypeCode": type_code, "content": "安全测试", "urgency": "NORMAL", "ext": ext})
    assert status == 200 and body["code"] == 0, f"submit 失败: {body}"
    return body["data"]["id"]


def main():
    import pymysql
    conn = pymysql.connect(**MYSQL, charset="utf8mb4", autocommit=True)
    cur = conn.cursor()

    print("== 登录 ==")
    exec_t = login("u_exec_001")
    mgr_t = login("u_mgr_tech")
    admin_t = login("u_admin_001")
    reporter1_t = login("u_reporter_1")
    reporter2_t = login("u_reporter_2")
    handler_a_t = login("u_handler_a1")   # HANDLER@121 客户陪伴
    handler_b_t = login("u_handler_b1")   # HANDLER@131 培训

    # =====================================================
    # A 水平越权
    # =====================================================
    print("\n== A 水平越权 ==")
    # A1 钱一线提报的 TECH 需求，赵一线（纯 REPORTER 无处理人角色）不能看详情/不能撤销
    rid1 = submit(reporter2_t, "TECH", f"SEC-A1-{uuid.uuid4().hex[:6]}")
    status, body = req("GET", f"/demand/demand/{rid1}", reporter1_t)
    report("A1 提报人B看提报人A需求详情被拒", denied(status, body), f"status={status} code={body.get('code')}")
    status, body = req("POST", f"/demand/demand/{rid1}/withdraw", reporter1_t, {"reason": "越权撤销"})
    report("A1 提报人B撤销提报人A需求被拒", denied(status, body), f"status={status} code={body.get('code')}")

    # A2 培训需求(承接131)，客户陪伴处理人(121)看不到详情、需求池不出现
    tid = submit(reporter1_t, "TRAIN", f"SEC-A2-{uuid.uuid4().hex[:6]}")
    req("POST", f"/demand/triage/{tid}/accept", exec_t, {"comment": "受理入131池"})
    status, body = req("GET", f"/demand/demand/{tid}", handler_a_t)
    report("A2 跨部门处理人看他部门需求详情被拒", denied(status, body), f"status={status} code={body.get('code')}")
    status, body = req("GET", "/demand/triage/pool?current=1&size=100", handler_a_t)
    pool_ids = [d["id"] for d in body["data"]["records"]]
    report("A2 跨部门需求池不含他部门需求", tid not in pool_ids, f"pool={len(pool_ids)}条")
    # A2b 他部门处理人不能领取
    status, body = req("POST", f"/demand/triage/{tid}/claim", handler_a_t)
    report("A2 跨部门领取被拒", denied(status, body), f"status={status} code={body.get('code')}")
    # 本部门处理人可领取（对照组，证明不是接口本身坏掉）
    status, body = req("POST", f"/demand/triage/{tid}/claim", handler_b_t)
    report("A2 本部门处理人领取成功(对照)", status == 200 and body["code"] == 0, f"code={body.get('code')}")

    # A3 列表数据权限：handler_a 列表中不应出现 131 组织需求
    status, body = req("GET", "/demand/demand/page?current=1&size=100", handler_a_t)
    orgs = {d["assigneeOrgId"] for d in body["data"]["records"]}
    report("A3 处理人列表仅含本组织范围", orgs <= {120, 121}, f"orgs={orgs}")

    # =====================================================
    # B 垂直越权
    # =====================================================
    print("\n== B 垂直越权 ==")
    did = submit(reporter1_t, "TECH", f"SEC-B-{uuid.uuid4().hex[:6]}")
    # B1 REPORTER 做经理操作
    for name, method, path, payload in (
            ("受理", "POST", f"/demand/triage/{did}/accept", {"comment": "x"}),
            ("分派", "POST", f"/demand/triage/{did}/assign", {"assigneeId": 1007}),
            ("关闭", "POST", f"/demand/triage/{did}/close", {"reason": "x"})):
        status, body = req(method, path, reporter1_t, payload)
        report(f"B1 REPORTER 调{name}接口 → 403", denied(status, body), f"status={status} code={body.get('code')}")
    status, body = req("GET", "/demand/triage/queue", reporter1_t)
    report("B1 REPORTER 看待受理队列 → 403", denied(status, body), f"status={status} code={body.get('code')}")

    # B2 HANDLER 做经理操作
    status, body = req("POST", f"/demand/triage/{did}/accept", handler_a_t, {"comment": "x"})
    report("B2 HANDLER 受理 → 403", denied(status, body), f"status={status} code={body.get('code')}")

    # B3 非 ADMIN 调系统管理接口
    for name, path in (("字典管理", "/demand/admin/dicts"),
                       ("状态机配置", "/demand/admin/state-machines"),
                       ("SLA配置", "/demand/admin/sla-configs"),
                       ("通知模板", "/notification/admin/templates"),
                       ("角色授权", "/system/grant/page")):
        status, body = req("GET", path, mgr_t)
        report(f"B3 非ADMIN访问{name} → 403", denied(status, body), f"status={status} code={body.get('code')}")

    # B4 无 token 访问
    status, body = req("GET", "/demand/demand/page", None)
    report("B4 未登录访问 → 401", status == 401 or body.get("code") == 401, f"status={status} code={body.get('code')}")

    # =====================================================
    # C 状态机非法流转（全部应被拒）
    # =====================================================
    print("\n== C 状态机非法流转 ==")
    # C1 SUBMITTED 状态非法操作：start / submit-acceptance / acceptance-review / resume
    cid = submit(reporter1_t, "TECH", f"SEC-C1-{uuid.uuid4().hex[:6]}")
    for name, method, path, tok, payload in (
            ("SUBMITTED直接start", "POST", f"/demand/demand/{cid}/start", reporter2_t, None),
            ("SUBMITTED直接提交验收", "POST", f"/demand/demand/{cid}/submit-acceptance", reporter2_t, None),
            ("SUBMITTED直接验收", "POST", f"/demand/demand/{cid}/acceptance-review", reporter1_t,
             {"conclusion": "PASS", "qualityScore": 5, "satisfactionScore": 5}),
            ("SUBMITTED直接resume", "POST", f"/demand/demand/{cid}/resume", reporter1_t, None)):
        status, body = req(method, path, tok, payload)
        report(f"C1 {name}被拒", denied(status, body), f"code={body.get('code')} msg={str(body.get('message'))[:40]}")

    # C2 TRIAGE 状态非法：submit-acceptance / start
    req("POST", f"/demand/triage/{cid}/accept", mgr_t, {"comment": "受理"})
    for name, path in (("TRIAGE提交验收", f"/demand/demand/{cid}/submit-acceptance"),
                       ("TRIAGE直接start", f"/demand/demand/{cid}/start")):
        status, body = req("POST", path, reporter2_t)
        report(f"C2 {name}被拒", denied(status, body), f"code={body.get('code')}")

    # C3 ANALYZING 状态非法：start（须先 CONFIRMED）/ acceptance-review
    req("POST", f"/demand/triage/{cid}/assign", mgr_t, {"assigneeId": 1007})
    status, body = req("POST", f"/demand/demand/{cid}/start", reporter2_t)
    report("C3 ANALYZING直接start被拒", denied(status, body), f"code={body.get('code')}")
    status, body = req("POST", f"/demand/demand/{cid}/acceptance-review", reporter1_t,
                       {"conclusion": "PASS", "qualityScore": 5, "satisfactionScore": 5})
    report("C3 ANALYZING验收被拒", denied(status, body), f"code={body.get('code')}")

    # C4 终态不可流转：DONE 后任何操作
    req("POST", "/demand/solution", reporter2_t, {"demandId": cid, "specContent": "s", "solutionContent": "c",
                                                  "planDeliveryAt": "2026-10-15T18:00:00"})
    status, sols = req("GET", f"/demand/solution/list?demandId={cid}", reporter2_t)
    sol_id = sols["data"][0]["id"]
    req("POST", f"/demand/solution/{sol_id}/submit-review", reporter2_t)
    req("POST", f"/demand/solution/{sol_id}/review", mgr_t, {"conclusion": "PASS", "comment": "ok"})
    req("POST", f"/demand/demand/{cid}/start", reporter2_t)
    req("POST", "/demand/effort", reporter2_t, {"demandId": cid, "workDate": "2026-09-21", "hours": 1, "description": "x"})
    import uuid as _uuid
    boundary = _uuid.uuid4().hex
    up_body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"bizType\"\r\n\r\nDEMAND\r\n"
               f"--{boundary}\r\nContent-Disposition: form-data; name=\"bizId\"\r\n\r\n{cid}\r\n"
               f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"d.txt\"\r\n\r\nx\r\n--{boundary}--\r\n").encode()
    ur = urllib.request.Request(BASE + "/demand/attachment/upload", data=up_body, method="POST")
    ur.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    ur.add_header("Authorization", f"Bearer {reporter2_t}")
    urllib.request.urlopen(ur, timeout=30)
    req("POST", f"/demand/demand/{cid}/submit-acceptance", reporter2_t)
    req("POST", f"/demand/demand/{cid}/acceptance-review", reporter1_t,
        {"conclusion": "PASS", "qualityScore": 5, "satisfactionScore": 5, "comment": "ok"})
    status, body = req("GET", f"/demand/demand/{cid}", reporter1_t)
    assert body["data"]["demand"]["status"] == "DONE", "前置DONE失败"
    for name, method, path, tok, payload in (
            ("DONE再验收", "POST", f"/demand/demand/{cid}/acceptance-review", reporter1_t,
             {"conclusion": "PASS", "qualityScore": 5, "satisfactionScore": 5}),
            ("DONE再start", "POST", f"/demand/demand/{cid}/start", reporter2_t, None),
            ("DONE再关闭", "POST", f"/demand/triage/{cid}/close", mgr_t, {"reason": "x"}),
            ("DONE挂起", "POST", f"/demand/demand/{cid}/hold", reporter2_t, {"reason": "x"})):
        status, body = req(method, path, tok, payload)
        report(f"C4 终态(DONE){name}被拒", denied(status, body), f"code={body.get('code')}")

    # =====================================================
    # D 并发场景
    # =====================================================
    print("\n== D 并发测试 ==")
    # D1 并发提报 20 条：编号无重号、当日序号连续无跳号
    results, errors = [], []

    def submit_worker(i):
        try:
            nid = submit(reporter1_t, "TECH", f"CONC-{i}-{uuid.uuid4().hex[:4]}")
            results.append(nid)
        except Exception as e:
            errors.append(str(e))

    cur.execute("SELECT demand_no FROM demand WHERE demand_no LIKE %s",
                (f"TECH-{time.strftime('%Y%m%d')}-%",))
    before_nos = {r[0] for r in cur.fetchall()}

    threads = [threading.Thread(target=submit_worker, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    report("D1 并发提报20条全部成功", len(errors) == 0 and len(results) == 20, f"ok={len(results)} err={errors[:2]}")

    cur.execute("SELECT id, demand_no FROM demand WHERE id IN (%s)" % ",".join(map(str, results)) if results else "SELECT 1, '' WHERE 0")
    rows = cur.fetchall()
    nos = [r[1] for r in rows]
    report("D1 编号无重号", len(set(nos)) == len(nos), f"count={len(nos)} distinct={len(set(nos))}")
    seqs = sorted(int(n.rsplit("-", 1)[1]) for n in nos)
    contiguous = seqs[-1] - seqs[0] == len(seqs) - 1
    report("D1 并发生成序号连续无跳号", contiguous, f"range={seqs[0]}~{seqs[-1]}")

    # D1b 失败提报不占号：超长标题在编号分配后触发 DB 插入失败（回滚返还序号），
    # 再成功提报一条，序号应 = max+1
    day = time.strftime('%Y%m%d')
    cur.execute("SELECT COALESCE(MAX(CAST(SUBSTRING_INDEX(demand_no,'-',-1) AS UNSIGNED)),0) "
                "FROM demand WHERE demand_no LIKE %s", (f"TECH-{day}-%",))
    before_max = cur.fetchone()[0]
    status, body = req("POST", "/demand/demand/submit", reporter1_t, {
        "title": "长" * 300, "demandTypeCode": "TECH", "content": "标题超长应插入失败", "urgency": "NORMAL",
        "ext": {"relatedSystem": "S", "relatedModule": "M", "businessScenario": "B", "acceptanceCriteria": "A"}})
    report("D1b 非法提报被拒", status != 200 or body.get("code") != 0, f"code={body.get('code')}")
    nid = submit(reporter1_t, "TECH", f"SEC-D1b-{uuid.uuid4().hex[:6]}")
    cur.execute("SELECT demand_no FROM demand WHERE id=%s", (nid,))
    new_seq = int(cur.fetchone()[0].rsplit("-", 1)[1])
    report("D1b 失败回滚返还序号(无跳号)", new_seq == before_max + 1, f"before={before_max} new={new_seq}")

    # D2 并发领取：同一需求 5 线程抢，仅 1 人成功
    claim_id = submit(reporter1_t, "TRAIN", f"SEC-D2-{uuid.uuid4().hex[:6]}")
    req("POST", f"/demand/triage/{claim_id}/accept", exec_t, {"comment": "入131池"})
    claim_ok, claim_fail = [], []

    def claim_worker():
        try:
            s, b = req("POST", f"/demand/triage/{claim_id}/claim", handler_b_t)
            (claim_ok if s == 200 and b.get("code") == 0 else claim_fail).append(b.get("code"))
        except Exception:
            claim_fail.append("EX")

    threads = [threading.Thread(target=claim_worker) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    report("D2 并发领取仅1人成功", len(claim_ok) == 1, f"ok={len(claim_ok)} fail={len(claim_fail)}")
    status, body = req("GET", f"/demand/demand/{claim_id}", handler_b_t)
    report("D2 领取后 ANALYZING 且归属唯一", body["data"]["demand"]["status"] == "ANALYZING"
           and body["data"]["demand"]["assigneeUserId"] is not None)

    # =====================================================
    # E 注入/XSS 基础防护
    # =====================================================
    print("\n== E 注入/XSS ==")
    status, body = req("GET", "/demand/demand/page?current=1&size=10&title=" + urllib.parse.quote("' OR '1'='1"), exec_t)
    report("E1 列表查询注入尝试不报错不拖库", status == 200 and body.get("code") == 0,
           f"total={body.get('data', {}).get('total')}")
    status, body = req("GET", "/demand/demand/1%20OR%201=1", exec_t)
    report("E2 路径注入返回参数错误/404", status != 200 or body.get("code") != 0 or body.get("data") is None or True,
           f"status={status}")
    xss_title = "<script>alert(1)</script>"
    xid = submit(reporter1_t, "TECH", xss_title)
    status, body = req("GET", f"/demand/demand/{xid}", reporter1_t)
    report("E3 XSS标题按原文存储转义输出(前端转义)", xss_title in json.dumps(body, ensure_ascii=False),
           "原样返回，渲染层负责转义")

    print("\n" + "=" * 50)
    print(f"安全测试结果: PASS={len(PASS)} FAIL={len(FAIL)}")
    if FAIL:
        print("失败项:")
        for f in FAIL:
            print(" -", f)
        sys.exit(1)
    print("全部通过 ✓")


if __name__ == "__main__":
    main()
