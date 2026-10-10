"""方舟传输使用真正的流；只有完整业务校验成功才清零失败计数。"""
import logging
import time
from dataclasses import dataclass
from functools import lru_cache

from httpx import HTTPError
from openai import APIError, APIStatusError, AsyncOpenAI

from app.config import get_settings

logger = logging.getLogger(__name__)


class LlmUnavailable(Exception):
    pass


@dataclass(frozen=True)
class StreamEvent:
    kind: str
    raw: str = ""
    usage: dict | None = None


class ArkClient:
    def __init__(self, settings=None, *, client=None, clock=time.monotonic):
        self.settings = settings or get_settings()
        self.clock = clock
        self.consecutive_failures = 0
        self.cooldown_until = 0.0
        self.thinking_supported = True
        self.client = client or AsyncOpenAI(api_key=self.settings.llm_api_key or "not-configured", base_url=self.settings.ark_base_url, timeout=self.settings.llm_read_timeout_s, max_retries=0)

    def available(self):
        return bool(self.settings.llm_api_key) and self.clock() >= self.cooldown_until

    def on_failure(self):
        self.consecutive_failures += 1
        if self.consecutive_failures >= self.settings.llm_failure_threshold:
            self.cooldown_until = self.clock() + self.settings.llm_failure_cooldown_s

    def on_success(self):
        self.consecutive_failures = 0
        self.cooldown_until = 0.0

    def _options(self, messages, *, stream):
        options = dict(model=self.settings.llm_chat_model, messages=messages, temperature=0.3, max_tokens=1500, response_format={"type": "json_object"}, stream=stream)
        if stream:
            options["stream_options"] = {"include_usage": True}
        if self.settings.llm_thinking and self.thinking_supported:
            options["extra_body"] = {"thinking": {"type": self.settings.llm_thinking}}
        return options

    @staticmethod
    def _thinking_rejected(error):
        # 仅明确指出参数不支持才降级；其他400绝不能被当成兼容问题。
        if error.status_code != 400:
            return False
        body = str(error.body).lower()
        return "thinking" in body and any(term in body for term in ("not supported", "unsupported", "unknown parameter", "unrecognized", "不支持"))

    async def _create(self, messages, *, stream):
        if not self.available():
            raise LlmUnavailable
        try:
            try:
                return await self.client.chat.completions.create(**self._options(messages, stream=stream))
            except APIStatusError as error:
                if not (self.settings.llm_thinking and self.thinking_supported and self._thinking_rejected(error)):
                    raise
                self.thinking_supported = False
                logger.warning("模型端点不支持thinking扩展，后续请求省略该参数")
                return await self.client.chat.completions.create(**self._options(messages, stream=stream))
        except (APIError, HTTPError) as error:
            self.on_failure()
            # 1401 对用户是黑盒，必须留痕：记录异常类型/详情/连续失败数，供排查瞬时故障与冷却级联
            logger.warning("LLM请求失败 consecutive=%s %s: %s", self.consecutive_failures, type(error).__name__, str(error)[:300])
            raise LlmUnavailable from None

    async def stream_json(self, messages):
        stream = await self._create(messages, stream=True)
        raw, usage = "", {}
        try:
            async with stream:
                async for chunk in stream:
                    if chunk.usage:
                        usage = chunk.usage.model_dump()
                    for choice in chunk.choices:
                        raw += choice.delta.content or ""
            yield StreamEvent(kind="final", raw=raw, usage=usage)
        except (APIError, HTTPError) as error:
            self.on_failure()
            logger.warning("LLM流中断 consecutive=%s %s: %s", self.consecutive_failures, type(error).__name__, str(error)[:300])
            raise LlmUnavailable from None

    async def complete_json(self, messages):
        response = await self._create(messages, stream=False)
        return StreamEvent(kind="final", raw=response.choices[0].message.content or "", usage=response.usage.model_dump() if response.usage else {})

    async def close(self):
        await self.client.close()


@lru_cache
def get_llm_client():
    return ArkClient()
