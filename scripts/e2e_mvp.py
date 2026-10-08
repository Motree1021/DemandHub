#!/usr/bin/env python3
"""MVP HTTP 闭环；mock/real 标记由调用者明确指定，不在业务服务内注入假结果。"""
import argparse
import json
import sys
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


def run(args):
    run_id = uuid4().hex
    token = login(args, "e2e-" + run_id[:12], "MVP联调用户")
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
    mine = http(args.api_base, "/demand/my", token=token)
    assert any(row["id"] == draft["id"] for row in mine["records"])
    detail = http(args.api_base, f"/demand/{draft['id']}", token=token)
    assert detail["standard"] and (args.agent_mode == "none" or len(detail["messages"]) >= 2)
    markdown = http(args.api_base, f"/demand/{draft['id']}/export.md", token=token, file=True).decode()
    assert "持仓自动报表" in markdown and "误差为0" in markdown
    admin = login(args, args.admin_user, "MVP联调管理员")
    page = http(args.api_base, "/admin/demand/list?type=TECH", token=admin)
    assert page["total"] >= 1
    workbook = http(args.api_base, "/admin/demand/export.xlsx?type=TECH", token=admin, file=True)
    assert workbook.startswith(b"PK")
    closed = http(args.api_base, f"/demand/{draft['id']}/close", method="POST", token=token, data={"reason": "联调验证完成"})
    assert closed["status"] == "CLOSED"
    print(json.dumps({"status": "passed", "agentMode": args.agent_mode, "chatTransport": args.chat_transport, "demandId": draft["id"], "demandNo": submitted["demandNo"], "messageCount": len(detail["messages"]), "xlsxBytes": len(workbook)}, ensure_ascii=False))


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
