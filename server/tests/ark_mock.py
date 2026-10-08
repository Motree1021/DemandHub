"""隔离网络联调用方舟契约Mock；生产服务没有假模型开关。"""
import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

EXTRACTION = {
    "structured": {
        "title": "渠道持仓日报", "demandTypeCode": "TECH",
        "content": "机构业务部客户经理每天晨会前查看各机构持仓，支持导出Excel。8:30前与核心系统对账误差为0，20名客户经理每天节省40分钟。",
        "urgency": "NORMAL",
        "elements": {
            "A": {"techSubtype": "DATA_RPT"},
            "B": {"businessGoal": "把晨会持仓整理从手工40分钟缩短到自动出具", "businessValue": "20名客户经理每天节省40分钟"},
            "C": {"userRole": "机构业务部客户经理", "useScenario": "机构业务部客户经理每天晨会前查看各机构持仓"},
            "D": {"acceptanceCriteria": "每天8:30前与核心系统对账误差为0，支持导出Excel", "dataRequirements": "核心系统持仓，按机构汇总前一交易日持仓，每个交易日8:00刷新"},
        },
    },
    "elements": [{"key": key, "status": "OK", "note": "测试契约固定样例"} for key in ("title", "demandTypeCode", "content", "techSubtype", "useScenario", "acceptanceCriteria", "businessValue")],
}

# 判型契约：按 tech.yaml type_signals 关键词表做轻量投票，只验证 wire format，不代表真实模型质量。
TYPE_SIGNAL_KEYS = {
    "business": ("部门目标", "组织目标", "效率", "成本", "投入产出", "合规", "监管", "立项", "考核", "指标", "部门"),
    "user": ("客户经理", "理财经理", "专员", "运营", "每天", "每周", "手工", "痛点", "流程", "晨会"),
    "function": ("系统应该", "系统必须", "自动", "支持", "接口", "报表", "推送", "按钮", "页面", "字段"),
}


def type_signals(text):
    votes = {}
    for layer, keys in TYPE_SIGNAL_KEYS.items():
        hits = [key for key in keys if key in text]
        votes[layer] = {"confidence": round(min(0.95, 0.25 + 0.25 * len(hits)), 4) if hits else 0.05, "evidence": hits[0] if hits else ""}
    return votes


def request_text(messages):
    parts = []
    for message in messages:
        if message.get("role") != "user":
            continue
        content = message.get("content", "")
        try:
            current = json.loads(content)
        except ValueError:
            parts.append(content)
            continue
        parts.append(str(current.get("message") or ""))
        form = current.get("form") or {}
        parts.append(str(form.get("title") or ""))
        parts.append(str(form.get("content") or ""))
    return "。".join(parts)



class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        try:
            body = json.loads(self.rfile.read(length))
        except (ValueError, UnicodeError):
            self.send_error(400)
            return
        if self.path.rstrip("/") not in {"/v3/chat/completions", "/chat/completions"}:
            self.send_error(404)
            return
        output = dict(EXTRACTION)
        for message in body.get("messages", []):
            if message.get("role") != "user":
                continue
            try:
                current = json.loads(message.get("content", ""))
            except ValueError:
                continue
            type_code = current.get("form", {}).get("demandTypeCode")
            if type_code in {"MATL", "TRAIN"}:
                output = {"structured": {"demandTypeCode": type_code}, "elements": EXTRACTION["elements"][:3]}
        output = json.loads(json.dumps(output, ensure_ascii=False))  # 深拷贝，避免污染固定样例
        text = request_text(body.get("messages", []))
        # 字段级需求契约：模型不应替用户发明 C/D 区内容，保持空缺由服务端追问
        if any(keyword in text for keyword in ("加个字段", "加字段", "加个列", "显示一下", "按钮")):
            output = {"structured": {"demandTypeCode": "TECH"}, "elements": EXTRACTION["elements"][:3]}
        if text.strip():
            output["typeSignals"] = type_signals(text)
        # FR-06 对话修改契约：用户明确说「目标…改…」时输出 B1 变更补丁（数字须可在原文溯源）
        if "改" in text and "目标" in text:
            output["structured"].setdefault("elements", {}).setdefault("B", {})["businessGoal"] = "把晨会准备时间从40分钟降到5分钟"
        raw = json.dumps(output, ensure_ascii=False)
        if body.get("stream"):
            pieces = [raw[start:start + 80] for start in range(0, len(raw), 80)]
            data = "".join("data: " + json.dumps({"id": "contract-mock", "object": "chat.completion.chunk", "created": int(time.time()), "model": "contract-mock", "choices": [{"index": 0, "delta": {"content": piece}, "finish_reason": None}]}, ensure_ascii=False) + "\n\n" for piece in pieces) + "data: [DONE]\n\n"
            content_type = "text/event-stream"
        else:
            data = json.dumps({"id": "contract-mock", "object": "chat.completion", "created": int(time.time()), "model": "contract-mock", "choices": [{"index": 0, "message": {"role": "assistant", "content": raw}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}, ensure_ascii=False)
            content_type = "application/json"
        encoded = data.encode()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def main():
    parser = argparse.ArgumentParser(description="本地测试专用方舟HTTP契约Mock")
    parser.add_argument("--port", type=int, default=8098)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
