#!/usr/bin/env python3
"""MVP HTTP 闭环；mock/real 标记由调用者明确指定，不在业务服务内注入假结果。"""
import argparse
import json
import sys
import time
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4


def http(base, path, *, method="GET", data=None, token=None, file=False):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    body = json.dumps(data, ensure_ascii=False).encode() if data is not None else None
    request = Request(base.rstrip("/") + path, data=body, headers=headers, method=method)
    try:
        with urlopen(request, timeout=90) as response:
            value = response.read()
    except HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} {path.split('?')[0]}") from None
    if file:
        if value.startswith(b'{"code"'):
            raise RuntimeError("导出返回错误JSON")
        return value
    value = json.loads(value)
    if "code" in value:
        if value["code"] != 0:
            raise RuntimeError(f"接口失败 code={value['code']} path={path.split('?')[0]}")
        return value["data"]
    return value


def login(args, user, name):
    ticket = http(args.mock_base, "/ticket", method="POST", data={"channelUserId": user, "name": name})["ticket"]
    return http(args.api_base, "/auth/channel-sso?" + urlencode({"channel": "chuangjinls", "ticket": ticket, "state": "mvp-e2e"}))["accessToken"]


def http_error_message(base, path, *, method="GET", data=None, token=None):
    """调用预期失败的接口并返回业务错误 message（http() 只对成功响应解包）。"""
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    body = json.dumps(data, ensure_ascii=False).encode() if data is not None else None
    request = Request(base.rstrip("/") + path, data=body, headers=headers, method=method)
    with urlopen(request, timeout=90) as response:
        value = json.loads(response.read())
    if value.get("code") == 0:
        raise RuntimeError(f"预期失败却成功 path={path.split('?')[0]}")
    return value.get("message", "")


def upload(args, demand_id, token):
    """multipart 交付物上传（验收前置之一）；md 纯文本无魔数，服务端按不含 NUL 校验。"""
    boundary = "----e2e" + uuid4().hex
    body = b"\r\n".join([
        ("--" + boundary).encode(),
        b'Content-Disposition: form-data; name="file"; filename="delivery.md"',
        b"Content-Type: text/markdown",
        b"",
        "# 联调交付物\n持仓报表已按口径验证。\n".encode(),
        ("--" + boundary + "--").encode(),
        b"",
    ])
    request = Request(args.api_base + f"/demand/{demand_id}/attachments?bizType=DEMAND",
                      data=body, method="POST",
                      headers={"Authorization": "Bearer " + token,
                               "Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with urlopen(request, timeout=90) as response:
            value = json.loads(response.read())
    except HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} 附件上传") from None
    if value.get("code") != 0:
        raise RuntimeError(f"附件上传失败 code={value.get('code')}")
    return value["data"]


def run(args):
    run_id = uuid4().hex
    token = login(args, "e2e-" + run_id[:12], "MVP联调用户")
    admin = login(args, args.admin_user, "MVP联调管理员")
    # ---- P4 前置：给管理员补 MANAGER+EXECUTIVE 授权（接收人=经理∪高管，授权范围空=全类型），保证 SUBMIT 通知必达 ----
    admin_id = http(args.api_base, "/auth/me", token=admin)["id"]
    for role_code in ("MANAGER", "EXECUTIVE"):
        existing = http(args.api_base, f"/admin/grants?userId={admin_id}&roleCode={role_code}", token=admin)
        if existing["total"] == 0:
            http(args.api_base, "/admin/grants", method="POST", token=admin,
                 data={"userId": admin_id, "roleCode": role_code})
    admin_unread_base = http(args.api_base, "/notification/mine/unread-count", token=admin)["count"]
    user_unread_base = http(args.api_base, "/notification/mine/unread-count", token=token)["count"]
    assert http(args.api_base, "/standards/TECH", token=token)["type"] == "TECH"
    draft = http(args.api_base, "/demand", method="POST", token=token, data={"clientRequestId": run_id})
    assert draft["demandNo"] is None and draft["title"] is None
    if args.agent_mode != "none":
        session = http(args.api_base, "/agent/session", method="POST", token=token, data={"scene": "SUBMIT_GUIDE", "demandId": draft["id"]})
        chat = {"demandId": draft["id"], "sessionId": session["id"], "requestId": run_id + "-chat", "revision": draft["revision"], "message": "需要科技报表需求：每天晨会前客户经理查询各渠道持仓并整理晨会材料，连续7天对账误差为0，20人每天节省40分钟。请整理需求。"}
        if args.chat_transport == "stream":
            raw = http(args.api_base, "/agent/guide/chat/stream", method="POST", token=token, data=chat, file=True).decode()
            events = []
            for frame in raw.replace("\r\n", "\n").split("\n\n"):
                lines = frame.splitlines()
                event = next((line[6:].strip() for line in lines if line.startswith("event:")), None)
                data = "\n".join(line[5:].lstrip() for line in lines if line.startswith("data:"))
                if event and data:
                    events.append((event, json.loads(data)))
            assert events[0] == ("processing", {"requestId": chat["requestId"], "status": "processing"})
            assert "error" not in [event for event, _ in events]
            assert [event for event, _ in events][-3:] == ["message", "structured", "done"]
            result = next(data for event, data in events if event == "structured")
            done = events[-1][1]
            assert done == {"requestId": chat["requestId"], "status": "completed"}
        else:
            result = http(args.api_base, "/agent/guide/chat", method="POST", token=token, data=chat)
        assert result["requestId"] == run_id + "-chat" and result["revision"] > draft["revision"]
        draft = http(args.api_base, f"/demand/{draft['id']}", token=token)["demand"]
        assert draft["revision"] == result["revision"]
        # 同一个请求用原 revision 重放，必须返回已落库响应而不新增消息。
        replay_result = http(args.api_base, "/agent/guide/chat", method="POST", token=token, data=chat)
        assert replay_result["revision"] == result["revision"]
        assert replay_result["structured"] == result["structured"]
        saved = http(args.api_base, f"/demand/{draft['id']}", token=token)
        assert len(saved["messages"]) == 2 and saved["demand"]["revision"] == result["revision"]
    confirmed = {"expectedRevision": draft["revision"], "title": "持仓自动报表", "demandTypeCode": "TECH", "content": "每天晨会前客户经理需要查询渠道持仓并汇总报表，替代手工统计，提高晨会准备效率。", "urgency": "NORMAL", "elements": {"A": {"techSubtype": "DATA_RPT"}, "C": {"userRole": "客户经理", "userGoal": "晨会前快速查看各渠道持仓汇总", "useScenario": "客户经理每天晨会前查询各渠道持仓并整理晨会材料", "painPoint": "手工统计20多个渠道持仓每次近40分钟容易出错"}, "D": {"functionDescription": "按渠道汇总前一交易日持仓并生成报表支持导出", "inputOutput": "输入交易流水输出持仓汇总报表", "acceptanceCriteria": "连续7天与核心系统对账误差为0"}}, "fieldSources": {"title": "user", "demandTypeCode": "user", "content": "user"}}
    draft = http(args.api_base, f"/demand/{draft['id']}", method="PUT", token=token, data=confirmed)
    submitted = http(args.api_base, f"/demand/{draft['id']}/submit", method="POST", token=token, data={"expectedRevision": draft["revision"]})
    assert submitted["demandNo"].startswith("TECH-") and submitted["quality"]
    replay = http(args.api_base, f"/demand/{draft['id']}/submit", method="POST", token=token, data={"expectedRevision": draft["revision"]})
    assert replay["demandNo"] == submitted["demandNo"]
    # ---- P4 通知：SUBMIT → TODO 站内信直达经理/高管（同事事务），read-all 后未读归零（幂等） ----
    notice = None
    deadline = time.time() + 10
    while time.time() < deadline:
        inbox = http(args.api_base, "/notification/mine?current=1&size=20&isRead=false", token=admin)
        notice = next((row for row in inbox["records"]
                       if row["demandId"] == draft["id"] and row["templateCode"] == "SUBMIT"), None)
        if notice:
            break
        time.sleep(0.5)
    assert notice and notice["notifyType"] == "TODO" and notice["link"] == f"/demands/{draft['id']}"
    assert http(args.api_base, "/notification/mine/unread-count", token=admin)["count"] > admin_unread_base
    cleared = http(args.api_base, "/notification/mine/read-all", method="PUT", token=admin, data={})
    assert cleared["updated"] >= 1
    assert http(args.api_base, "/notification/mine/unread-count", token=admin)["count"] == 0
    # ---- P4 看板：实时 SQL 口径（不读快照表）；手动快照刷新可用，一致性由单测覆盖 ----
    board = http(args.api_base, "/dashboard/manager?range=month", token=admin)
    assert board["kpi"]["monthNew"] >= 1 and len(board["trend"]) == 12
    assert {"normal", "warn", "over"} <= set(board["slaHealth"])
    org = http(args.api_base, "/dashboard/org?range=week", token=admin)
    assert org["pendingAccept"] >= 1 and isinstance(org["memberWorkload"], list)
    refreshed = http(args.api_base, "/dashboard/stat-refresh", method="POST", token=admin, data={})
    assert refreshed["rows"] >= 1
    mine = http(args.api_base, "/demand/my", token=token)
    assert any(row["id"] == draft["id"] for row in mine["records"])
    detail = http(args.api_base, f"/demand/{draft['id']}", token=token)
    assert detail["standard"] and (args.agent_mode == "none" or len(detail["messages"]) >= 2)
    markdown = http(args.api_base, f"/demand/{draft['id']}/export.md", token=token, file=True).decode()
    assert "持仓自动报表" in markdown and "误差为0" in markdown
    page = http(args.api_base, "/admin/demand/list?type=TECH", token=admin)
    assert page["total"] >= 1
    workbook = http(args.api_base, "/admin/demand/export.xlsx?type=TECH", token=admin, file=True)
    assert workbook.startswith(b"PK")
    p3 = {}
    if args.agent_mode != "none":
        # ---- P3 处理辅助 + RAG：受理分派 → AI 草稿（人工确认入库）→ 评审 → 验收 DONE → 相似召回 ----
        admin_me = http(args.api_base, "/auth/me", token=admin)
        http(args.api_base, f"/triage/{draft['id']}/accept", method="POST", token=admin, data={})
        http(args.api_base, f"/triage/{draft['id']}/assign", method="POST", token=admin, data={"assigneeId": admin_me["id"]})
        assist = http(args.api_base, "/agent/session", method="POST", token=admin,
                      data={"scene": "HANDLE_ASSIST", "demandId": draft["id"]})
        reopened = http(args.api_base, "/agent/session", method="POST", token=admin,
                        data={"scene": "HANDLE_ASSIST", "demandId": draft["id"]})
        assert reopened["id"] == assist["id"]  # 需求级共享会话：重复打开返回同一会话
        q_draft = http(args.api_base, "/agent/assist/questions", method="POST", token=admin,
                       data={"sessionId": assist["id"]})
        assert q_draft["draftType"] == "QUESTIONS" and q_draft["status"] == "PENDING" and len(q_draft["content"]) >= 3
        s_draft = http(args.api_base, "/agent/assist/solution", method="POST", token=admin,
                       data={"sessionId": assist["id"]})
        assert s_draft["draftType"] == "SOLUTION" and s_draft["status"] == "PENDING"
        # 编辑后确认入库：solution 版本 1、DRAFT、备注「AI 生成，人工确认入库」
        confirmed = http(args.api_base, f"/agent/assist/drafts/{s_draft['id']}/confirm", method="POST", token=admin,
                         data={"specContent": "人工修订：晨会持仓自动汇总，8:30前出具",
                               "solutionContent": "人工修订：每日7:30跑批生成渠道持仓报表",
                               "planDeliveryAt": "2026-11-30"})
        assert confirmed["status"] == "CONFIRMED" and confirmed["targetSolutionId"]
        solution_id = confirmed["targetSolutionId"]
        solutions = http(args.api_base, "/solution/list?demandId=" + str(draft["id"]), token=admin)
        mine = next(row for row in solutions if row["id"] == solution_id)
        assert mine["version"] == 1 and mine["status"] == "DRAFT" and mine["remark"] == "AI 生成，人工确认入库"
        http(args.api_base, f"/solution/{solution_id}/submit-review", method="POST", token=admin)
        http(args.api_base, f"/solution/{solution_id}/review", method="POST", token=admin,
             data={"result": "PASS", "opinion": "方案可行"})
        http(args.api_base, f"/demand/{draft['id']}/start", method="POST", token=admin)
        # 验收三前置：方案已确认（上面 PASS）+ 工时 + 交付物
        http(args.api_base, "/effort", method="POST", token=admin,
             data={"demandId": draft["id"], "workDate": "2026-10-14", "hours": 2, "remark": "联调填报"})
        upload(args, draft["id"], admin)
        http(args.api_base, f"/demand/{draft['id']}/submit-acceptance", method="POST", token=admin)
        done = http(args.api_base, f"/demand/{draft['id']}/acceptance-review", method="POST", token=token,
                    data={"result": "PASS", "qualityScore": 5, "satisfactionScore": 5, "opinion": "验收通过，比手工快"})
        assert done["status"] == "DONE"
        # DONE 触发后台向量化（即发即忘）：第二个需求作查询端，轮询相似召回直至命中
        probe = http(args.api_base, "/demand", method="POST", token=token,
                     data={"clientRequestId": run_id + "-probe", "title": "渠道持仓周报", "demandTypeCode": "TECH",
                           "content": "客户经理每周晨会前查询渠道持仓并输出报表"})
        hits = []
        deadline = time.time() + 20
        while time.time() < deadline:
            hits = http(args.api_base, f"/agent/rag/similar?demandId={probe['id']}&topN=5", token=admin)
            if any(hit["demandId"] == draft["id"] for hit in hits):
                break
            time.sleep(0.5)
        assert any(hit["demandId"] == draft["id"] for hit in hits), "DONE 需求未被 RAG 相似召回"
        p3 = {"assistSessionId": assist["id"], "questionCount": len(q_draft["content"]),
              "solutionId": solution_id, "ragHits": len(hits)}
        # 提报人侧通知：ACCEPT/SUBMIT_ACCEPTANCE 等处理人事件必达本人信箱（mock 链路）
        assert http(args.api_base, "/notification/mine/unread-count", token=token)["count"] > user_unread_base
    if args.agent_mode == "none":
        # 提报人侧通知闭环（none 链路无处理人事件）：退回补充（RETURN→提报人）→ 重提 → 提报人撤销
        http(args.api_base, f"/triage/{draft['id']}/return", method="POST", token=admin,
             data={"reason": "联调退回补充：痛点需量化"})
        assert http(args.api_base, "/notification/mine/unread-count", token=token)["count"] > user_unread_base
        current = http(args.api_base, f"/demand/{draft['id']}", token=token)["demand"]
        assert current["status"] == "NEED_INFO"
        resubmitted = http(args.api_base, f"/demand/{draft['id']}/submit", method="POST", token=token,
                           data={"expectedRevision": current["revision"]})
        assert resubmitted["demandNo"] == submitted["demandNo"]
        closed = http(args.api_base, f"/demand/{draft['id']}/close", method="POST", token=token, data={"reason": "联调验证完成"})
        assert closed["status"] == "CLOSED"
    # ---- P4 报表：异步导出任务轮询到 SUCCESS 后可下载（本地目录替代 MinIO） ----
    task = http(args.api_base, "/report/export", method="POST", token=admin,
                data={"reportType": "DEMAND_LIST", "params": {"keyword": "持仓"}})
    assert task["taskNo"].startswith("RPT-")
    task_row = None
    deadline = time.time() + 20
    while time.time() < deadline:
        tasks = http(args.api_base, "/report/tasks?current=1&size=10", token=admin)
        task_row = next((item for item in tasks["records"] if item["id"] == task["id"]), None)
        if task_row and task_row["status"] in ("SUCCESS", "FAILED"):
            break
        time.sleep(0.5)
    assert task_row and task_row["status"] == "SUCCESS", f"报表任务未成功: {task_row and task_row.get('errorMsg')}"
    report_book = http(args.api_base, f"/report/download/{task['id']}", token=admin, file=True)
    assert report_book.startswith(b"PK")
    p4 = {"notifyId": notice["id"], "statRows": refreshed["rows"],
          "reportTaskNo": task["taskNo"], "reportBytes": len(report_book)}
    # ---- P5 系统管理域：字典/类型/状态机/SLA/渠道 CRUD + 组织树 + 需求组织回填 ----
    suffix = run_id[:8].upper()
    # 字典：新增 → 停用（按设计字典无删除，保留停用记录）
    dict_row = http(args.api_base, "/admin/dicts", method="POST", token=admin,
                    data={"dictType": "E2E_G", "itemCode": "X" + suffix, "itemName": "联调字典项", "sort": 1})
    assert http(args.api_base, f"/admin/dicts/{dict_row['id']}", method="PUT", token=admin,
                data={"status": "DISABLED"})["status"] == "DISABLED"
    # 组织树：首个条线下新增部门，物化路径自动回填（尾斜杠、父级前缀）
    tree = http(args.api_base, "/admin/orgs/tree", token=admin)
    assert tree, "组织树为空（种子缺失）"
    line = next(node for node in tree if node["level"] == "LINE")
    org = http(args.api_base, "/admin/orgs", method="POST", token=admin,
               data={"name": "联调部门" + suffix, "level": "DEPT", "parentId": line["orgId"], "orgKind": "BOTH"})
    assert org["path"] == f"{line['path']}{org['orgId']}/"
    # 类型：注册并绑定组织与 DEFAULT 状态机（五区标准仍走 yaml，此处只管注册/绑定/排序）
    p5_type = http(args.api_base, "/admin/types", method="POST", token=admin,
                   data={"typeCode": "E2E" + suffix, "typeName": "联调类型", "defaultOrgId": org["orgId"],
                         "stateMachineKey": "DEFAULT", "sort": 900})
    assert p5_type["defaultOrgId"] == org["orgId"]
    # 状态机：取默认规则模板 → 新建 → 热重载（不重启）→ 列表即时可见
    default_json = http(args.api_base, "/admin/state-machines/default-json", token=admin)["configJson"]
    machine = http(args.api_base, "/admin/state-machines", method="POST", token=admin,
                   data={"configKey": "E2E_" + suffix, "configName": "联调流程", "configJson": default_json})
    http(args.api_base, "/admin/state-machines/reload", method="POST", token=admin, data={})
    keys = [row["configKey"] for row in http(args.api_base, "/admin/state-machines", token=admin)]
    assert machine["configKey"] in keys
    # SLA：新档（黄牌先于红牌）→ 调整黄牌 → 删除（SLA 允许删除，用完即清不留残留）
    sla = http(args.api_base, "/admin/sla-configs", method="POST", token=admin,
               data={"demandTypeCode": p5_type["typeCode"], "status": "TRIAGE", "warnMinutes": 60, "maxMinutes": 120})
    assert http(args.api_base, f"/admin/sla-configs/{sla['id']}", method="PUT", token=admin,
                data={"warnMinutes": 30})["warnMinutes"] == 30
    http(args.api_base, f"/admin/sla-configs/{sla['id']}", method="DELETE", token=admin)
    # 渠道：列表含登录渠道；停用后立即启回（避免影响后续登录链路）
    channels = http(args.api_base, "/admin/channels", token=admin)
    channel = next(row for row in channels if row["channelCode"] == "CHUANGJIN_LS")
    assert http(args.api_base, f"/admin/channels/{channel['id']}/status", method="PUT", token=admin,
                data={"status": "DISABLED"})["status"] == "DISABLED"
    assert http(args.api_base, f"/admin/channels/{channel['id']}/status", method="PUT", token=admin,
                data={"status": "ACTIVE"})["status"] == "ACTIVE"
    # 组织回填端到端：TECH 改绑联调组织 → 新需求提报 → 组织被需求引用不可删（间接证明 assigneeOrgId 已回填）
    types = http(args.api_base, "/admin/types", token=admin)
    tech = next(row for row in types if row["typeCode"] == "TECH")
    old_org = tech["defaultOrgId"]
    http(args.api_base, f"/admin/types/{tech['id']}", method="PUT", token=admin, data={"defaultOrgId": org["orgId"]})
    p5_draft = http(args.api_base, "/demand", method="POST", token=token,
                    data={"clientRequestId": run_id + "-p5"})
    p5_form = {"expectedRevision": p5_draft["revision"], "title": "联调组织回填需求", "demandTypeCode": "TECH",
               "content": "每天晨会前客户经理需要查询渠道持仓并汇总报表，替代手工统计，提高晨会准备效率。",
               "urgency": "NORMAL",
               "elements": {"A": {"techSubtype": "DATA_RPT"},
                            "C": {"userRole": "客户经理", "userGoal": "晨会前快速查看各渠道持仓汇总",
                                  "useScenario": "客户经理每天晨会前查询各渠道持仓并整理晨会材料",
                                  "painPoint": "手工统计20多个渠道持仓每次近40分钟容易出错"},
                            "D": {"functionDescription": "按渠道汇总前一交易日持仓并生成报表支持导出",
                                  "inputOutput": "输入交易流水输出持仓汇总报表",
                                  "acceptanceCriteria": "连续7天与核心系统对账误差为0"}},
               "fieldSources": {"title": "user", "demandTypeCode": "user", "content": "user"}}
    p5_draft = http(args.api_base, f"/demand/{p5_draft['id']}", method="PUT", token=token, data=p5_form)
    p5_submitted = http(args.api_base, f"/demand/{p5_draft['id']}/submit", method="POST", token=token,
                        data={"expectedRevision": p5_draft["revision"]})
    assert p5_submitted["demandNo"].startswith("TECH-")
    rejected = http_error_message(args.api_base, f"/admin/orgs/{org['orgId']}", method="DELETE", token=admin)
    assert "需求引用" in rejected, f"组织删除应被需求引用拦截，实际: {rejected}"
    # 现场还原：TECH defaultOrgId 复原，避免污染 dev 库主类型配置（联调类型/组织停用留存）
    http(args.api_base, f"/admin/types/{tech['id']}", method="PUT", token=admin, data={"defaultOrgId": old_org})
    p5 = {"orgId": org["orgId"], "orgPath": org["path"], "stateMachineKey": machine["configKey"],
          "p5DemandNo": p5_submitted["demandNo"]}
    print(json.dumps({"status": "passed", "agentMode": args.agent_mode, "chatTransport": args.chat_transport, "demandId": draft["id"], "demandNo": submitted["demandNo"], "messageCount": len(detail["messages"]), "xlsxBytes": len(workbook), **p3, **p4, **p5}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base", default="http://127.0.0.1:8000/demandhub-api")
    parser.add_argument("--mock-base", default="http://127.0.0.1:8199")
    parser.add_argument("--admin-user", default="mvp-admin")
    parser.add_argument("--agent-mode", choices=["none", "mock", "real"], default="none")
    parser.add_argument("--chat-transport", choices=["stream", "chat"], default="stream")
    args = parser.parse_args()
    try:
        run(args)
    except (RuntimeError, AssertionError, KeyError, URLError, HTTPException, OSError) as exc:
        print(json.dumps({"status": "failed", "error": type(exc).__name__, "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
