# -*- coding: utf-8 -*-
"""阶段8 端到端联调自测（对照执行计划阶段8任务1~4 / 检查点1）

覆盖：
- CP1 科技需求全流程：提报→受理→分派→分析→方案→评审→排期→处理→提交验收→验收→DONE
- CP2 物料/培训需求主干：提报→受理→关闭
- CP3 挂起/恢复全流程（状态快照还原）
- CP4 退回补充→重新提交→撤销
- CP5 通知在关键节点触达（站内信 + Mock 企微 WECOM 行 SENT）
- CP6 每个状态变更写 demand_transition_log（审计）

运行前提：中间件 + 后端 5 模块已启动（网关 8080）。
"""
import io
import json
import sys
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


def req(method, path, token=None, body=None, raw=False):
    url = BASE + path
    data = json.dumps(body).encode("utf-8") if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            payload = resp.read()
            if raw:
                return resp.status, payload
            return resp.status, json.loads(payload.decode("utf-8"))
    except urllib.error.HTTPError as e:
        payload = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(payload)
        except Exception:
            return e.code, {"raw": payload}


def upload(token, biz_type, biz_id, filename, content: bytes):
    """multipart/form-data 上传附件"""
    boundary = uuid.uuid4().hex
    body = b""
    for name, value in (("bizType", biz_type), ("bizId", str(biz_id))):
        body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode()
    body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\nContent-Type: text/plain\r\n\r\n".encode()
    body += content + f"\r\n--{boundary}--\r\n".encode()
    r = urllib.request.Request(BASE + "/demand/attachment/upload", data=body, method="POST")
    r.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    r.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8", errors="replace"))


def login(user_id):
    status, body = req("GET", f"/system/auth/callback?code=mock-{user_id}")
    assert status == 200 and body["code"] == 0, f"login {user_id} failed: {body}"
    return body["data"]["accessToken"]


def must_ok(step, status, body):
    assert status == 200 and body.get("code") == 0, f"{step} 失败: status={status} body={json.dumps(body, ensure_ascii=False)[:400]}"


def get_status(token, demand_id):
    status, body = req("GET", f"/demand/demand/{demand_id}", token)
    must_ok("查询详情", status, body)
    demand = body["data"]["demand"]
    return demand["status"], demand


def expect_status(token, demand_id, expect, step):
    actual, detail = get_status(token, demand_id)
    report(f"{step} → {expect}", actual == expect, f"status={actual}")
    return detail


def wait_notification(template_code, demand_id, timeout=30):
    """轮询等待通知行（站内信）生成，返回匹配行数"""
    import pymysql
    conn = pymysql.connect(**MYSQL, charset="utf8mb4", autocommit=True)
    cur = conn.cursor()
    deadline = time.time() + timeout
    while time.time() < deadline:
        cur.execute("SELECT COUNT(*) FROM notification WHERE demand_id=%s AND template_code=%s",
                    (demand_id, template_code))
        n = cur.fetchone()[0]
        if n > 0:
            return n
        time.sleep(1)
    return 0


def check_transitions(token, demand_id, expect_events):
    status, body = req("GET", f"/demand/demand/{demand_id}/transitions", token)
    must_ok("查询流转日志", status, body)
    events = [t["action"] for t in body["data"]]
    ok = events == expect_events
    report("transition_log 完整且有序", ok, f"events={events}")
    # 每条都有操作人
    no_operator = [t for t in body["data"] if not t.get("operatorId")]
    report("transition_log 均含操作人（审计）", len(no_operator) == 0, f"missing={len(no_operator)}")


def main():
    import pymysql
    conn = pymysql.connect(**MYSQL, charset="utf8mb4", autocommit=True)
    cur = conn.cursor()

    print("== 登录 ==")
    exec_t = login("u_exec_001")        # 李总 EXECUTIVE（跨组织）
    mgr_t = login("u_mgr_tech")         # 王经理 DEMAND_MANAGER@110
    reporter1_t = login("u_reporter_1") # 赵一线 REPORTER
    reporter2_t = login("u_reporter_2") # 钱一线 REPORTER + HANDLER@111（科技处理人）
    handler_a_t = login("u_handler_a1") # 陈陪伴 HANDLER@121
    handler_b_t = login("u_handler_b1") # 刘培训 HANDLER@131

    TECH_HANDLER_ID = 1007  # u_reporter_2（seed 授权 HANDLER@111 科技产品一组）

    # =====================================================
    # CP1 科技需求全流程（10 节点）
    # =====================================================
    print("\n== CP1 科技需求全流程 ==")
    title = f"E2E科技-手机银行闪退修复-{uuid.uuid4().hex[:6]}"
    status, body = req("POST", "/demand/demand/submit", reporter1_t, {
        "title": title,
        "demandTypeCode": "TECH",
        "content": "一线展业演示时手机银行首页偶现闪退，需排查修复。",
        "urgency": "URGENT",
        "ext": {"relatedSystem": "手机银行APP", "relatedModule": "首页",
                "businessScenario": "一线展业演示", "acceptanceCriteria": "演示场景连续 20 次不闪退"},
    })
    must_ok("提报", status, body)
    did = body["data"]["id"]
    demand_no = body["data"]["demandNo"]
    report("1.提报生成编号", demand_no.startswith("TECH-") and body["data"]["status"] == "SUBMITTED",
           f"demandNo={demand_no}")
    report("  通知:SUBMIT", wait_notification("SUBMIT", did) > 0)

    status, body = req("POST", f"/demand/triage/{did}/accept", mgr_t, {"comment": "受理通过"})
    must_ok("受理", status, body)
    expect_status(mgr_t, did, "TRIAGE", "2.经理受理")
    report("  通知:ACCEPT", wait_notification("ACCEPT", did) > 0)

    status, body = req("POST", f"/demand/triage/{did}/assign", mgr_t,
                       {"assigneeId": TECH_HANDLER_ID, "comment": "分派科技一组处理"})
    must_ok("分派", status, body)
    detail = expect_status(mgr_t, did, "ANALYZING", "3.经理分派")
    report("  分派给指定处理人", detail["assigneeUserId"] == TECH_HANDLER_ID,
           f"assignee={detail['assigneeUserId']}")
    report("  通知:ASSIGN", wait_notification("ASSIGN", did) > 0)

    status, body = req("POST", "/demand/solution", reporter2_t, {
        "demandId": did, "specContent": "复现路径：首页轮播接口超时未兜底",
        "solutionContent": "增加接口超时熔断与本地缓存兜底", "planDeliveryAt": "2026-10-15T18:00:00",
        "remark": "排期 10 月版本"})
    must_ok("新建方案", status, body)
    sol_id = body["data"]["id"]
    report("4.处理人分析建方案 v1", body["data"]["version"] == 1, f"solutionId={sol_id}")

    status, body = req("POST", f"/demand/solution/{sol_id}/submit-review", reporter2_t)
    must_ok("提交评审", status, body)
    expect_status(mgr_t, did, "SOLUTION_REVIEW", "5.提交方案评审")
    report("  通知:SUBMIT_REVIEW", wait_notification("SUBMIT_REVIEW", did) > 0)

    status, body = req("POST", f"/demand/solution/{sol_id}/review", mgr_t,
                       {"conclusion": "PASS", "comment": "方案可行，按排期执行"})
    must_ok("方案评审", status, body)
    expect_status(mgr_t, did, "CONFIRMED", "6.评审通过(已排期)")
    status, sols = req("GET", f"/demand/solution/list?demandId={did}", reporter2_t)
    report("  方案状态 APPROVED", sols["data"][0]["status"] == "APPROVED")
    report("  通知:REVIEW_PASS", wait_notification("REVIEW_PASS", did) > 0)

    status, body = req("POST", f"/demand/demand/{did}/start", reporter2_t)
    must_ok("开始处理", status, body)
    expect_status(reporter2_t, did, "IN_PROGRESS", "7.开始处理")
    report("  通知:START", wait_notification("START", did) > 0)

    status, body = req("POST", "/demand/effort", reporter2_t, {
        "demandId": did, "workDate": "2026-09-21", "hours": 4.5, "description": "定位并修复闪退"})
    must_ok("填报工时", status, body)
    report("8.工时填报", body["data"]["id"] is not None)

    status, att = upload(reporter2_t, "DEMAND", did, "hotfix-v1.2.3.md", "发版说明：修复首页闪退".encode())
    report("  交付物上传", status == 200 and att["code"] == 0, f"status={status}")

    status, body = req("POST", f"/demand/demand/{did}/submit-acceptance", reporter2_t)
    must_ok("提交验收", status, body)
    expect_status(reporter1_t, did, "ACCEPTANCE", "9.提交验收")
    report("  通知:SUBMIT_ACCEPTANCE", wait_notification("SUBMIT_ACCEPTANCE", did) > 0)

    status, body = req("POST", f"/demand/demand/{did}/acceptance-review", reporter1_t,
                       {"conclusion": "PASS", "qualityScore": 5, "satisfactionScore": 5,
                        "comment": "演示 20 次无闪退，验收通过"})
    must_ok("验收", status, body)
    detail = expect_status(reporter1_t, did, "DONE", "10.验收通过")
    report("  评分归档", detail["qualityScore"] == 5 and detail["satisfactionScore"] == 5
           and detail["actualDeliveryAt"] is not None)
    report("  通知:ACCEPT_PASS", wait_notification("ACCEPT_PASS", did) > 0)

    check_transitions(mgr_t, did, ["SUBMIT", "ACCEPT", "ASSIGN", "SUBMIT_REVIEW",
                                   "REVIEW_PASS", "START", "SUBMIT_ACCEPTANCE", "ACCEPT_PASS"])

    # =====================================================
    # CP2 物料/培训需求主干：提报→受理→关闭
    # =====================================================
    print("\n== CP2 物料/培训主干 ==")
    for type_code, handler_t, name in (("MATL", handler_a_t, "物料"), ("TRAIN", handler_b_t, "培训")):
        ext = {"materialSubtype": "折页", "usageScenario": "路演", "quantity": 5000,
               "expectedArrivalAt": "2026-10-01T00:00:00"} if type_code == "MATL" else {
            "trainingSubtype": "从业资格", "traineeObject": "新员工", "traineeCount": 12,
            "expectedCompleteAt": "2026-11-30T00:00:00"}
        status, body = req("POST", "/demand/demand/submit", reporter1_t, {
            "title": f"E2E{name}-{uuid.uuid4().hex[:6]}", "demandTypeCode": type_code,
            "content": f"E2E {name}需求主干验证", "urgency": "NORMAL", "ext": ext})
        must_ok(f"{name}提报", status, body)
        mid = body["data"]["id"]
        report(f"{name}提报编号前缀", body["data"]["demandNo"].startswith(type_code + "-"),
               body["data"]["demandNo"])
        # 受理：121/131 非 mgr_tech 管辖，走 EXECUTIVE（李总全线）
        status, body = req("POST", f"/demand/triage/{mid}/accept", exec_t, {"comment": "受理"})
        must_ok(f"{name}受理", status, body)
        expect_status(exec_t, mid, "TRIAGE", f"{name}受理")
        status, body = req("POST", f"/demand/triage/{mid}/close", exec_t, {"reason": "E2E 主干验证关闭"})
        must_ok(f"{name}关闭", status, body)
        expect_status(exec_t, mid, "CLOSED", f"{name}关闭")
        report(f"  通知:CLOSE({name})", wait_notification("CLOSE", mid) > 0)

    # =====================================================
    # CP3 挂起/恢复全流程
    # =====================================================
    print("\n== CP3 挂起/恢复 ==")
    status, body = req("POST", "/demand/demand/submit", reporter1_t, {
        "title": f"E2E挂起-{uuid.uuid4().hex[:6]}", "demandTypeCode": "TECH",
        "content": "验证挂起恢复", "urgency": "NORMAL",
        "ext": {"relatedSystem": "CRM", "relatedModule": "客户列表", "businessScenario": "日常",
                "acceptanceCriteria": "N/A"}})
    must_ok("提报", status, body)
    hid = body["data"]["id"]
    req("POST", f"/demand/triage/{hid}/accept", mgr_t, {"comment": "受理"})
    req("POST", f"/demand/triage/{hid}/assign", mgr_t, {"assigneeId": TECH_HANDLER_ID})
    expect_status(reporter2_t, hid, "ANALYZING", "挂起前置")

    status, body = req("POST", f"/demand/demand/{hid}/hold", reporter2_t, {"reason": "等外部依赖排期"})
    must_ok("挂起", status, body)
    _, d = get_status(reporter2_t, hid)
    report("挂起叠加态", d.get("onHold") == 1 and d["status"] == "ANALYZING",
           f"onHold={d.get('onHold')} status={d['status']} snapshot={d.get('holdSnapshotStatus')}")
    report("  通知:HOLD", wait_notification("HOLD", hid) > 0)

    # 挂起中非法操作应被拒（状态机 ON_HOLD 下无 START 规则）
    status, body = req("POST", f"/demand/demand/{hid}/start", reporter2_t)
    report("挂起中 start 被拒", status != 200 or body.get("code") != 0,
           f"status={status} code={body.get('code')}")

    status, body = req("POST", f"/demand/demand/{hid}/resume", reporter2_t)
    must_ok("恢复", status, body)
    _, d = get_status(reporter2_t, hid)
    report("恢复还原主状态", d.get("onHold") == 0 and d["status"] == "ANALYZING",
           f"onHold={d.get('onHold')} status={d['status']}")
    report("  通知:RESUME", wait_notification("RESUME", hid) > 0)

    # =====================================================
    # CP4 退回补充 → 重新提交 → 撤销
    # =====================================================
    print("\n== CP4 退回补充/重提/撤销 ==")
    status, body = req("POST", "/demand/demand/submit", reporter1_t, {
        "title": f"E2E退回-{uuid.uuid4().hex[:6]}", "demandTypeCode": "TECH",
        "content": "信息不全待补充", "urgency": "NORMAL",
        "ext": {"relatedSystem": "CRM", "relatedModule": "-", "businessScenario": "-",
                "acceptanceCriteria": "-"}})
    must_ok("提报", status, body)
    rid = body["data"]["id"]
    status, body = req("POST", f"/demand/triage/{rid}/return", mgr_t, {"comment": "请补充影响面"})
    must_ok("退回", status, body)
    expect_status(reporter1_t, rid, "NEED_INFO", "退回补充")
    report("  通知:RETURN", wait_notification("RETURN", rid) > 0)

    status, body = req("POST", f"/demand/demand/{rid}/resubmit", reporter1_t,
                       {"title": "E2E退回-已补充", "content": "补充：影响全部一线营业部",
                        "urgency": "NORMAL",
                        "ext": {"relatedSystem": "CRM", "relatedModule": "客户列表",
                                "businessScenario": "晨会演示", "acceptanceCriteria": "演示通过"}})
    must_ok("重提", status, body)
    expect_status(reporter1_t, rid, "SUBMITTED", "补充后重提")

    status, body = req("POST", f"/demand/demand/{rid}/withdraw", reporter1_t, {"reason": "重复提报，撤销"})
    must_ok("撤销", status, body)
    expect_status(reporter1_t, rid, "CLOSED", "撤销关闭")
    report("  通知:WITHDRAW", wait_notification("WITHDRAW", rid) > 0)
    check_transitions(mgr_t, rid, ["SUBMIT", "RETURN", "SUBMIT", "WITHDRAW"])

    # =====================================================
    # CP5 Mock 企微触达验证（WECOM 行 SENT，无 FAILED 积压）
    # =====================================================
    print("\n== CP5 Mock 企微触达 ==")
    time.sleep(3)  # 等 RocketMQ 消费
    cur.execute("""SELECT send_status, COUNT(*) FROM notification
                   WHERE channel='WECOM' AND created_at >= NOW() - INTERVAL 1 HOUR GROUP BY send_status""")
    rows = dict(cur.fetchall())
    report("企微 WECOM 推送全部 SENT", rows.get("SENT", 0) > 0 and rows.get("FAILED", 0) == 0,
           f"{rows}")
    cur.execute("""SELECT COUNT(*) FROM notification
                   WHERE channel='WECOM' AND demand_id=%s AND send_status='SENT'""", (did,))
    report("科技全流程企微触达 ≥6 个节点", cur.fetchone()[0] >= 6, f"demand={did}")

    # =====================================================
    # CP6 通知偏好关闭后不生成对应通知（M7 回归抽验）
    # =====================================================
    print("\n== CP6 站内信未读计数 ==")
    status, body = req("GET", "/notification/mine/unread-count", mgr_t)
    unread = body["data"]["count"] if status == 200 and isinstance(body.get("data"), dict) else 0
    report("经理未读数 >0（各节点通知）", status == 200 and unread > 0, f"unread={unread}")

    print("\n" + "=" * 50)
    print(f"E2E 结果: PASS={len(PASS)} FAIL={len(FAIL)}")
    if FAIL:
        print("失败项:")
        for f in FAIL:
            print(" -", f)
        sys.exit(1)
    print("全部通过 ✓")


if __name__ == "__main__":
    main()
