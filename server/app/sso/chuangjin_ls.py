import asyncio
import json
import time
from uuid import uuid4

import httpx
from pydantic import ValidationError

from app.core.errors import BizError, ErrorCode
from app.sso.schemas import ChannelSsoConfig, SsoProfile
from app.sso.sign import VERIFY_PATH, hmac_sha256_hex, string_to_sign

MSG_REENTER = "登录已失效，请从创金零售重新进入"
MSG_UNAVAILABLE = "登录服务暂时不可用，请稍后重试"


class ChuangjinLsSsoClient:
    def __init__(self, config: ChannelSsoConfig, client: httpx.AsyncClient | None = None):
        self.config = config
        self.client = client
        self.consecutive_failures = 0
        self.breaker_open_until = 0.0
        self._half_open_lock = asyncio.Lock()

    def transport_failure(self):
        self.consecutive_failures += 1
        if self.consecutive_failures >= 3:
            self.breaker_open_until = time.monotonic() + 30
            self.consecutive_failures = 0
        return BizError(ErrorCode.AUTH_SERVICE_UNAVAILABLE, MSG_UNAVAILABLE)

    async def verify(self, ticket: str) -> SsoProfile:
        if not ticket or not ticket.strip():
            raise BizError(ErrorCode.CHANNEL_TICKET_INVALID, MSG_REENTER)
        if time.monotonic() < self.breaker_open_until:
            raise BizError(ErrorCode.AUTH_SERVICE_UNAVAILABLE, MSG_UNAVAILABLE)
        body = json.dumps({"ticket": ticket}, separators=(",", ":"), ensure_ascii=False)
        timestamp, nonce = str(int(time.time() * 1000)), uuid4().hex
        cfg = self.config
        headers = {"Content-Type": "application/json", "X-App-Key": cfg.app_key,
                   "X-Timestamp": timestamp, "X-Nonce": nonce,
                   "X-Sign": hmac_sha256_hex(cfg.app_secret, string_to_sign(VERIFY_PATH, cfg.app_key, timestamp, nonce, body))}
        try:
            if self.client:
                response = await self.client.post(cfg.base_url.rstrip("/") + VERIFY_PATH, content=body, headers=headers, timeout=cfg.timeout_ms / 1000)
            else:
                async with httpx.AsyncClient() as client:
                    response = await client.post(cfg.base_url.rstrip("/") + VERIFY_PATH, content=body, headers=headers, timeout=cfg.timeout_ms / 1000)
        except httpx.TransportError:
            raise self.transport_failure() from None
        if response.status_code != 200:
            raise self.transport_failure()
        try:
            data = response.json()
        except ValueError:
            raise self.transport_failure() from None
        if not isinstance(data, dict):
            raise self.transport_failure()
        code = data.get("errcode")
        if code == 0:
            try:
                profile = SsoProfile.model_validate(data.get("user"))
                if not profile.user_id.strip() or not profile.name.strip():
                    raise ValueError
            except (ValidationError, ValueError):
                raise BizError(ErrorCode.AUTH_SERVICE_UNAVAILABLE, MSG_UNAVAILABLE) from None
            self.consecutive_failures = 0
            self.breaker_open_until = 0
            return profile
        if code in (40001, 40002, 40005):
            raise BizError(ErrorCode.CHANNEL_TICKET_INVALID, MSG_REENTER)
        if code == 40004:
            raise BizError(ErrorCode.CHANNEL_ACCOUNT_UNAVAILABLE)
        raise BizError(ErrorCode.AUTH_SERVICE_UNAVAILABLE, MSG_UNAVAILABLE)
