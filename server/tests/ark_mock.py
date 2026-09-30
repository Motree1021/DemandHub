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
        "ext": {"techSubtype": "DATA_RPT", "businessScenario": "机构业务部客户经理每天晨会前查看各机构持仓", "acceptanceCriteria": "每天8:30前与核心系统对账误差为0，支持导出Excel", "valueImpact": "20名客户经理每天节省40分钟", "dataDimensions": "按机构汇总前一交易日持仓", "dataSource": "核心系统持仓", "refreshFrequency": "每个交易日8:00", "exportRequirement": "支持导出Excel"},
    },
    "elements": [{"key": key, "status": "OK", "note": "测试契约固定样例"} for key in ("title", "demandTypeCode", "content", "techSubtype", "businessScenario", "acceptanceCriteria", "valueImpact")],
}


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
