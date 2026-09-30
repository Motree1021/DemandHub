# -*- coding: utf-8 -*-
"""创金零售 verify 契约级 Mock（P6 测试环境专用，对接标准 v2.1 §3.3 同一契约）。

与 dev 内置 MockChannelSsoController 的区别：本服务独立于 DemandHub 运行（test 栈 CHANNEL_SSO_MOCK=false），
用于在 test profile 下验证 ChuangjinLsSsoClient 真实 HTTP + HMAC 签名链路——签名严格校验在服务端发生，
任何签名错误/时间戳偏差/nonce 重放均由本服务拒绝（40003），覆盖 AC-08。

端点：
- POST /openapi/demandhub/sso/verify  契约 verify（签名校验 → 票据一次性消费 → errcode 契约响应）
- POST /ticket                        签票（测试脚手架，非契约）：{channelUserId, scenario?, name?, phone?, deptId?, deptName?}
- GET  /health                        健康检查（compose healthcheck 用）

场景（issue 的 scenario 参数）：normal 正常 / expired 签出即过期(40001) / no_phone 无手机不阻塞 /
resigned 离职(40004) / missing_name 缺必填(40005) / dept_unmapped 部门未映射(挂 900) / slow 延迟 5s(超时熔断用)；
重放场景：同一 ticket 自然消费两次 → 40002。

配置（环境变量）：APP_KEY / APP_SECRET（须与 DemandHub 侧 CHANNEL_LS_APP_KEY/SECRET 一致）、PORT（默认 8099）。
仅标准库，无第三方依赖，可直接跑在 python:3.11-slim 容器。
"""
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

APP_KEY = os.environ.get("APP_KEY", "demandhub-test")
APP_SECRET = os.environ.get("APP_SECRET", "chuangjinls-test-secret-please-change-me")
PORT = int(os.environ.get("PORT", "8099"))

VERIFY_PATH = "/openapi/demandhub/sso/verify"
TICKET_TTL_SECONDS = 60
USED_MARK_TTL_SECONDS = 600
NONCE_TTL_SECONDS = 300
TIMESTAMP_TOLERANCE_MS = 5 * 60 * 1000
SLOW_RESPONSE_SECONDS = 5

_lock = threading.Lock()
_tickets = {}   # ticket -> (payload dict, expire_at_epoch)
_used = {}      # ticket -> mark_expire_at_epoch（区分 40001 与 40002）
_nonces = {}    # nonce -> expire_at_epoch


def _sweep(store):
    now = time.time()
    for k in [k for k, v in store.items() if v < now]:
        store.pop(k, None)


def _sweep_tickets():
    """_tickets 值为 (payload, expire_at) 元组，按 expire_at 清理"""
    now = time.time()
    for k in [k for k, v in _tickets.items() if v[1] < now]:
        _tickets.pop(k, None)


def mask_ticket(t):
    return (t[:6] + "***") if t else t


def string_to_sign(path, app_key, timestamp, nonce, body):
    return "\n".join(["POST", path, app_key, timestamp, nonce, body])


def expected_sign(timestamp, nonce, body):
    s2s = string_to_sign(VERIFY_PATH, APP_KEY, timestamp, nonce, body)
    return hmac.new(APP_SECRET.encode("utf-8"), s2s.encode("utf-8"), hashlib.sha256).hexdigest()


def err(errcode, errmsg):
    return {"errcode": errcode, "errmsg": errmsg}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # 静音默认访问日志（留痕用自有脱敏日志）
        pass

    def _send(self, obj, status=200):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length).decode("utf-8") if length > 0 else ""

    def do_GET(self):
        if self.path == "/health":
            self._send({"status": "UP"})
        else:
            self._send(err(40404, "not found"), status=404)

    def do_POST(self):
        body = self._read_body()
        if self.path == VERIFY_PATH:
            self._verify(body)
        elif self.path == "/ticket":
            self._issue(body)
        else:
            self._send(err(40404, "not found"), status=404)

    # ---- 签票（测试脚手架）----
    def _issue(self, body):
        try:
            req = json.loads(body) if body else {}
        except Exception:
            self._send(err(40005, "bad json"), status=400)
            return
        channel_user_id = req.get("channelUserId")
        if not channel_user_id:
            self._send(err(40005, "channelUserId required"), status=400)
            return
        scenario = req.get("scenario") or "normal"
        payload = {
            "user_id": channel_user_id,
            "name": req.get("name") or "契约测试员工",
            "phone": req.get("phone") or "13800001111",
            "dept_id": req.get("deptId") or "110",
            "dept_name": req.get("deptName") or "财管科技产品部",
            "dept_path": req.get("deptPath") or "创金合信零售业务线/财管科技产品部",
            "employee_no": req.get("employeeNo"),
            "email": req.get("email"),
            "scenario": scenario,
        }
        if scenario == "no_phone":
            payload["phone"] = None
        if scenario == "missing_name":
            payload["name"] = None
        if scenario == "dept_unmapped":
            payload["dept_id"] = "D_UNMAPPED_999"
            payload["dept_name"] = "未映射部门"
            payload["dept_path"] = "创金合信零售业务线/未映射部门"
        ticket = secrets.token_hex(32)
        with _lock:
            _sweep_tickets()
            if scenario != "expired":
                # expired 场景模拟"签出时已过期"：不下发存储，verify 取不到 → 40001
                _tickets[ticket] = (payload, time.time() + TICKET_TTL_SECONDS)
        print(f"[contract-mock] 签票 scenario={scenario} user={channel_user_id} ticket={mask_ticket(ticket)}", flush=True)
        self._send({"ticket": ticket, "expiresIn": TICKET_TTL_SECONDS})

    # ---- 契约 verify ----
    def _verify(self, raw_body):
        app_key = self.headers.get("X-App-Key") or ""
        timestamp = self.headers.get("X-Timestamp") or ""
        nonce = self.headers.get("X-Nonce") or ""
        sign = (self.headers.get("X-Sign") or "").lower()

        # 1. 服务间鉴权：app_key → 时间戳偏差≤5分钟 → nonce 5分钟不重复 → HMAC 签名（任一失败 → 40003）
        if app_key != APP_KEY:
            print(f"[contract-mock] 鉴权失败(app_key): appKey={app_key}", flush=True)
            return self._send(err(40003, "app_key invalid"))
        try:
            ts = int(timestamp)
        except ValueError:
            ts = -1
        if ts <= 0 or abs(int(time.time() * 1000) - ts) > TIMESTAMP_TOLERANCE_MS:
            print(f"[contract-mock] 鉴权失败(timestamp 偏差>5分钟): timestamp={timestamp}", flush=True)
            return self._send(err(40003, "timestamp expired"))
        with _lock:
            _sweep(_nonces)
            if not nonce or nonce in _nonces:
                print(f"[contract-mock] 鉴权失败(nonce 重复): nonce={nonce}", flush=True)
                return self._send(err(40003, "nonce replayed"))
            _nonces[nonce] = time.time() + NONCE_TTL_SECONDS
        if not sign or not hmac.compare_digest(expected_sign(timestamp, nonce, raw_body), sign):
            print(f"[contract-mock] 鉴权失败(sign 不匹配): nonce={nonce}", flush=True)
            return self._send(err(40003, "sign invalid"))

        # 2. 参数：ticket 缺失 → 40005
        ticket = None
        try:
            ticket = (json.loads(raw_body) or {}).get("ticket")
        except Exception:
            pass
        if not ticket:
            return self._send(err(40005, "ticket required"))

        # 3. 一次性消费；取不到时分流：已消费 → 40002 重放，否则 → 40001 无效/过期
        with _lock:
            _sweep(_used)
            entry = _tickets.pop(ticket, None)
            if entry is None:
                used = ticket in _used
                print(f"[contract-mock] 票据被拒: ticket={mask_ticket(ticket)} used={used}", flush=True)
                return self._send(err(40002, "ticket already used") if used
                                  else err(40001, "ticket invalid or expired"))
            payload, expire_at = entry
            if expire_at < time.time():
                # 超时未消费的票据：消费时判定过期（内存存储无 TTL 自动失效，等价 Redis TTL 语义）
                print(f"[contract-mock] 票据过期: ticket={mask_ticket(ticket)}", flush=True)
                return self._send(err(40001, "ticket invalid or expired"))
            _used[ticket] = time.time() + USED_MARK_TTL_SECONDS
        scenario = payload.get("scenario") or "normal"
        # slow 场景：签名校验通过后延迟 5s 响应（客户端 3s 超时 → 传输失败，用于熔断降级验证）
        if scenario == "slow":
            print(f"[contract-mock] slow 场景延迟 {SLOW_RESPONSE_SECONDS}s: ticket={mask_ticket(ticket)}", flush=True)
            time.sleep(SLOW_RESPONSE_SECONDS)
        if scenario == "resigned":
            print(f"[contract-mock] 离职场景: ticket={mask_ticket(ticket)}", flush=True)
            return self._send(err(40004, "user resigned"))
        if scenario == "missing_name":
            print(f"[contract-mock] 缺必填姓名场景(40005): ticket={mask_ticket(ticket)}", flush=True)
            return self._send(err(40005, "user name missing"))
        user = {k: payload.get(k) for k in
                ("user_id", "name", "phone", "dept_id", "dept_name", "dept_path", "employee_no", "email")}
        print(f"[contract-mock] verify 成功: user_id={user['user_id']} phone={'***' if user['phone'] else None}",
              flush=True)
        self._send({"errcode": 0, "errmsg": "ok", "user": user,
                    "ticket_expire_at": int((time.time() + TICKET_TTL_SECONDS) * 1000)})


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"[contract-mock] 创金零售 verify 契约 Mock 启动: port={PORT} appKey={APP_KEY}", flush=True)
    server.serve_forever()
