"""方舟传输使用真正的流；只有完整业务校验成功才清零失败计数。"""
import asyncio
import logging
import time
from dataclasses import dataclass
from functools import lru_cache

from httpx import AsyncClient as HttpxAsyncClient
from httpx import HTTPError
from openai import APIConnectionError, APIError, APIStatusError, APITimeoutError, AsyncOpenAI

from app.config import get_settings

logger = logging.getLogger(__name__)

# 瞬时错误（429/5xx/超时/连接）自动重试 1 次的间隔秒数（2026-10-15 拍板；测试注入 0）
RETRY_DELAY_S = 2.0

# 上游内容安全审核拦截的响应特征（Ark 无公开稳定错误码，按响应体关键词识别）
_MODERATION_TERMS = ("contentfilter", "content_filter", "sensitive", "inappropriate", "moderation", "审核", "敏感", "安全风险")


class LlmUnavailable(Exception):
    pass


class LlmContentRejected(LlmUnavailable):
    """输入被上游内容安全审核拦截：改表述才可能成功，重试无意义、不计熔断。
    继承 LlmUnavailable 让处理辅助/RAG 等链路按既有降级自动兜底；提报主流程（guide）单独捕获转 1405。"""


class _Retryable(Exception):
    """内部用：429/5xx/超时/连接类瞬时错误，携带原异常供留痕，由 _with_retry 统一计次。"""

    def __init__(self, error):
        super().__init__(str(error))
        self.error = error


@dataclass(frozen=True)
class StreamEvent:
    kind: str
    raw: str = ""
    usage: dict | None = None


class ArkClient:
    def __init__(self, settings=None, *, client=None, clock=time.monotonic, retry_delay=RETRY_DELAY_S):
        self.settings = settings or get_settings()
        self.clock = clock
        self.retry_delay = retry_delay
        self.consecutive_failures = 0
        self.cooldown_until = 0.0
        self.thinking_supported = True
        # trust_env=False：不隐式继承系统代理——本机代理软件会劫持上游请求造成假"上游故障"（与 SSO 客户端同口径）
        self.client = client or AsyncOpenAI(api_key=self.settings.llm_api_key or "not-configured", base_url=self.settings.ark_base_url, timeout=self.settings.llm_read_timeout_s, max_retries=0, http_client=HttpxAsyncClient(trust_env=False))

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
        # max_tokens=8192（2026-10-16 拍板）：30要素结构化JSON在整段大段需求下实测需~1500 tokens，
        # 原 1500 顶格会被截断→JSON解析失败→修复重试同样顶格→1401；8192 覆盖 20000 字最长输入。
        # 官方上限 384k、默认 4k，token 按实际生成量计费，调大上限不增加常规成本。
        options = dict(model=self.settings.llm_chat_model, messages=messages, temperature=0.3, max_tokens=8192, response_format={"type": "json_object"}, stream=stream)
        if stream:
            options["stream_options"] = {"include_usage": True}
        if self.settings.llm_thinking and self.thinking_supported:
            options["extra_body"] = {"thinking": {"type": self.settings.llm_thinking}}
        return options

    @staticmethod
    def _thinking_rejected(error):
        # 仅明确指出参数不支持才降级；其他400绝不能被当成兼容问题。
        if getattr(error, "status_code", None) != 400:  # 网络类异常（超时/连接失败）无 status_code，不算参数拒绝
            return False
        body = str(getattr(error, "body", "")).lower()
        return "thinking" in body and any(term in body for term in ("not supported", "unsupported", "unknown parameter", "unrecognized", "不支持"))

    @staticmethod
    def _classify(error):
        """审核拒绝(rejected) / 瞬时可重试(retryable) / 其他4xx业务错误(fatal，不重试不冒充兼容)。"""
        if isinstance(error, APIStatusError):
            body = str(error.body).lower()
            if error.status_code in (400, 403, 422) and any(term in body for term in _MODERATION_TERMS):
                return "rejected"
            if error.status_code == 429 or error.status_code >= 500:
                return "retryable"
            return "fatal"
        return "retryable"  # 连接/读流/超时等传输层错误

    def _fail(self, label, error):
        self.on_failure()
        # 1401 对用户是黑盒，必须留痕：记录异常类型/完整详情/连续失败数，供排查瞬时故障与冷却级联
        logger.warning("%s consecutive=%s %s: %s", label, self.consecutive_failures, type(error).__name__, str(error))
        raise LlmUnavailable from None

    @staticmethod
    def _reject(error):
        # 审核拦截对提报人是可改写信号：不计熔断、不重试，单独错误码直达用户
        logger.warning("LLM输入被内容安全审核拦截 %s: %s", type(error).__name__, str(error))
        raise LlmContentRejected from None

    async def _create(self, messages, *, stream):
        """单次尝试。审核拦截 → LlmContentRejected；瞬时错误 → _Retryable；其他 4xx → LlmUnavailable。"""
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
            kind = self._classify(error)
            if kind == "rejected":
                self._reject(error)
            if kind == "retryable":
                raise _Retryable(error) from None
            self._fail("LLM请求失败(4xx)", error)

    async def _with_retry(self, action):
        """瞬时错误自动重试 1 次；重试仍败才计一次请求级失败并抛 1401（重试成功不计失败）。"""
        for attempt in range(2):
            try:
                return await action()
            except _Retryable as retry:
                if attempt == 1:
                    self._fail("LLM请求重试后仍失败", retry.error)
                logger.warning("LLM瞬时故障，%.0fs后自动重试一次 %s: %s", self.retry_delay, type(retry.error).__name__, str(retry.error))
                await asyncio.sleep(self.retry_delay)

    async def stream_json(self, messages):
        """创建与读流两段各自带 1 次自动重试：单次请求最坏 4 次上游调用（总重试预算）。
        流中断重试安全：半成品尚未 yield，重来不会重复输出。"""
        raw, usage = "", {}
        for attempt in range(2):
            stream = await self._with_retry(lambda: self._create(messages, stream=True))
            try:
                async with stream:
                    async for chunk in stream:
                        if chunk.usage:
                            usage = chunk.usage.model_dump()
                        for choice in chunk.choices:
                            raw += choice.delta.content or ""
                yield StreamEvent(kind="final", raw=raw, usage=usage)
                return
            except (APIError, HTTPError) as error:
                kind = self._classify(error)
                if kind == "rejected":
                    self._reject(error)
                if kind == "fatal" or attempt == 1:
                    self._fail("LLM流中断", error)
                logger.warning("LLM流中断，%.0fs后自动重试一次 %s: %s", self.retry_delay, type(error).__name__, str(error))
                raw, usage = "", {}
                await asyncio.sleep(self.retry_delay)

    async def complete_json(self, messages):
        response = await self._with_retry(lambda: self._create(messages, stream=False))
        return StreamEvent(kind="final", raw=response.choices[0].message.content or "", usage=response.usage.model_dump() if response.usage else {})

    async def complete_vision(self, messages):
        """视觉模型单次调用（图→文本转写，2026-10-22 拍板）：独立模型/超时/max_tokens，
        不做自动重试——用户同步等待（上限见 llm_vision_timeout_s），重试会倍增等待；瞬时故障由业务层降级为普通附件。
        输出为纯文本约定（转写文本或 NO_TEXT），不带 JSON 模式；
        显式关闭深度思考（2026-10-23 实测：Seed 系列端点默认开启 thinking，转写任务思考纯属浪费——
        同一张长截图 92.5s → 5.3s），端点不支持该参数时省略后重试一次（400 即时返回，非超时重试）；
        连接级故障（网络抖动/端点瞬时不可达，通常秒级返回）重试一次——2026-10-23 实测连接抖动
        12s 快速失败误杀真实解析；超时（APITimeoutError）不重试，用户已等满上限重试会倍增等待；
        llm_vision_model 为空（未启用）即抛 LlmUnavailable，业务层按降级兜底。
        熔断计数与 chat/embed 共用（同一上游服务）；on_success 由业务层在校验输出有效后调用。"""
        if not self.available() or not self.settings.llm_vision_model:
            raise LlmUnavailable
        options = dict(
            model=self.settings.llm_vision_model,
            messages=messages,
            temperature=0.1,  # 转写任务求稳不求活
            max_tokens=self.settings.llm_vision_max_tokens,
            stream=False,
            timeout=self.settings.llm_vision_timeout_s,
            extra_body={"thinking": {"type": "disabled"}},
        )
        try:
            response = await self.client.chat.completions.create(**options)
        except (APIError, HTTPError) as error:
            if self._thinking_rejected(error):
                options.pop("extra_body")
                try:
                    response = await self.client.chat.completions.create(**options)
                except (APIError, HTTPError) as retry_error:
                    self._fail("LLM视觉解析失败", retry_error)
            elif isinstance(error, APIConnectionError) and not isinstance(error, APITimeoutError):
                # 连接级故障重试一次（秒级返回，不倍增等待）；第二次失败按统一口径计一次失败
                try:
                    response = await self.client.chat.completions.create(**options)
                except (APIError, HTTPError) as retry_error:
                    self._fail("LLM视觉解析失败", retry_error)
            else:
                kind = self._classify(error)
                if kind == "rejected":
                    self._reject(error)
                self._fail("LLM视觉解析失败", error)
        return response.choices[0].message.content or ""

    async def embed(self, text: str) -> list[float]:
        """文本向量化（P3 RAG）：与 chat 同口径的可用性闸门与熔断（3 次失败冷却 60s）。

        llm_embedding_model 配置位为空（未启用）或处于冷却期 → LlmUnavailable，
        调用方按降级处理（相似推荐返回空、向量化跳过），不阻塞业务主流程。
        """
        if not self.available() or not self.settings.llm_embedding_model:
            raise LlmUnavailable
        try:
            response = await self.client.embeddings.create(model=self.settings.llm_embedding_model, input=text)
        except (APIError, HTTPError) as error:
            self.on_failure()
            logger.warning("LLM embedding请求失败 consecutive=%s %s: %s", self.consecutive_failures, type(error).__name__, str(error))
            raise LlmUnavailable from None
        self.on_success()
        return list(response.data[0].embedding)

    async def close(self):
        await self.client.close()


@lru_cache
def get_llm_client():
    return ArkClient()
