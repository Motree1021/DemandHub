import asyncio
import json

import httpx
import pytest
from openai import AsyncOpenAI

from app.agent.llm_client import ArkClient, LlmContentRejected, LlmUnavailable
from app.config import Settings


@pytest.fixture
def llm_settings():
    return Settings(app_env="test", demandhub_database_url="mysql://test:test@localhost/demandhub_test", jwt_secret="test-secret-that-is-long-enough-32", llm_api_key="fake-unit-key", ark_base_url="https://ark.test/v3", llm_thinking="disabled")


def sse_body(content):
    chunks = [content[:12], content[12:]]
    body = "".join("data: " + json.dumps({"id": "x", "object": "chat.completion.chunk", "created": 0, "model": "fake", "choices": [{"index": 0, "delta": {"content": part}, "finish_reason": None}]}) + "\n\n" for part in chunks)
    return body + 'data: [DONE]\n\n'


def mocked_client(settings, router, **kwargs):
    sdk = AsyncOpenAI(api_key="fake", base_url=settings.ark_base_url, max_retries=0, http_client=httpx.AsyncClient(transport=httpx.MockTransport(router.handler)))
    return ArkClient(settings, client=sdk, **kwargs)


async def collect(client):
    return [event async for event in client.stream_json([{"role": "user", "content": "需求"}])]


async def test_stream_final_complete_json_and_no_transport_success_reset(respx_mock, llm_settings):
    raw = '{"structured":{},"elements":[]}'
    route = respx_mock.post("https://ark.test/v3/chat/completions").respond(200, text=sse_body(raw), headers={"content-type": "text/event-stream"})
    client = mocked_client(llm_settings, respx_mock)
    client.consecutive_failures = 2
    result = await collect(client)
    assert result[0].raw == raw and client.consecutive_failures == 2
    body = json.loads(route.calls[0].request.content)
    assert body["stream"] is True and body["thinking"] == {"type": "disabled"}
    assert body["response_format"] == {"type": "json_object"}
    client.on_success()
    assert client.consecutive_failures == 0
    await client.close()


async def test_http_500_auto_retry_then_cooldown(respx_mock, llm_settings):
    # 5xx 属可重试瞬时错误：每次请求 = 首次 + 自动重试 1 次（2026-10-15 拍板），重试仍败计一次请求级失败
    route = respx_mock.post("https://ark.test/v3/chat/completions").respond(500, json={"error": {"message": "upstream-secret"}})
    client = mocked_client(llm_settings, respx_mock, clock=lambda: 100, retry_delay=0)
    for _ in range(3):
        with pytest.raises(LlmUnavailable):
            await collect(client)
    assert route.call_count == 6  # 3 次请求 × 2 次尝试
    assert not client.available() and client.cooldown_until == 160
    with pytest.raises(LlmUnavailable):
        await collect(client)
    assert route.call_count == 6
    await client.close()


async def test_retryable_error_auto_recovers_without_failure_count(respx_mock, llm_settings):
    """瞬时 5xx 自动重试 1 次即恢复：不计失败、用户无感。"""
    raw = '{"structured":{},"elements":[]}'
    route = respx_mock.post("https://ark.test/v3/chat/completions")
    route.side_effect = [httpx.Response(500, json={"error": {"message": "upstream glitch"}}), httpx.Response(200, text=sse_body(raw), headers={"content-type": "text/event-stream"})]
    client = mocked_client(llm_settings, respx_mock, retry_delay=0)
    result = await collect(client)
    assert result[0].raw == raw and route.call_count == 2 and client.consecutive_failures == 0
    await client.close()


async def test_content_rejected_not_retried_not_counted(respx_mock, llm_settings):
    """内容安全审核拦截 → LlmContentRejected：不重试、不计熔断，由 guide 转 1405 提示改写。"""
    route = respx_mock.post("https://ark.test/v3/chat/completions").respond(400, json={"error": {"code": "ContentFilter", "message": "The input text contains sensitive information."}})
    client = mocked_client(llm_settings, respx_mock, retry_delay=0)
    with pytest.raises(LlmContentRejected):
        await collect(client)
    assert route.call_count == 1 and client.consecutive_failures == 0
    await client.close()


async def test_429_auto_retry_once_then_unavailable(respx_mock, llm_settings):
    """限流 429 属可重试错误：重试 1 次仍败计一次请求级失败。"""
    route = respx_mock.post("https://ark.test/v3/chat/completions").respond(429, json={"error": {"message": "rate limited"}})
    client = mocked_client(llm_settings, respx_mock, retry_delay=0)
    with pytest.raises(LlmUnavailable):
        await collect(client)
    assert route.call_count == 2 and client.consecutive_failures == 1
    await client.close()


async def test_thinking_explicit_rejection_retries_once_then_remembers(respx_mock, llm_settings):
    route = respx_mock.post("https://ark.test/v3/chat/completions")
    route.side_effect = [httpx.Response(400, json={"error": {"message": "thinking is not supported"}}), httpx.Response(200, text=sse_body('{"structured":{},"elements":[]}'), headers={"content-type": "text/event-stream"}), httpx.Response(200, text=sse_body('{"structured":{},"elements":[]}'), headers={"content-type": "text/event-stream"})]
    client = mocked_client(llm_settings, respx_mock)
    await collect(client)
    await collect(client)
    assert route.call_count == 3
    assert "thinking" in json.loads(route.calls[0].request.content)
    assert all("thinking" not in json.loads(call.request.content) for call in route.calls[1:])
    await client.close()


async def test_other_400_is_not_thinking_compatibility_retry(respx_mock, llm_settings):
    route = respx_mock.post("https://ark.test/v3/chat/completions").respond(400, json={"error": {"message": "invalid max_tokens"}})
    client = mocked_client(llm_settings, respx_mock)
    with pytest.raises(LlmUnavailable):
        await collect(client)
    assert route.call_count == 1 and client.consecutive_failures == 1
    await client.close()


def completion_body(content):
    return json.dumps({"id": "x", "object": "chat.completion", "created": 0, "model": "fake",
                       "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}]})


async def test_complete_vision_disables_thinking_without_json_mode(respx_mock, llm_settings):
    # 2026-10-23 实测：Seed 端点默认开启深度思考，转写任务 92.5s→5.3s；必须显式关闭
    route = respx_mock.post("https://ark.test/v3/chat/completions").respond(200, text=completion_body("转写文本"))
    client = mocked_client(llm_settings.model_copy(update={"llm_vision_model": "ep-vision"}), respx_mock)
    out = await client.complete_vision([{"role": "user", "content": [{"type": "text", "text": "读图"}]}])
    assert out == "转写文本"
    body = json.loads(route.calls[0].request.content)
    assert body["thinking"] == {"type": "disabled"} and body["model"] == "ep-vision"
    assert "response_format" not in body and body["stream"] is False
    await client.close()


async def test_complete_vision_thinking_rejected_retries_once_without(respx_mock, llm_settings):
    # 端点不支持 thinking 参数时省略后即时重试一次（400 快速返回，非超时重试）
    route = respx_mock.post("https://ark.test/v3/chat/completions")
    route.side_effect = [httpx.Response(400, json={"error": {"message": "thinking is not supported"}}), httpx.Response(200, text=completion_body("转写文本"))]
    client = mocked_client(llm_settings.model_copy(update={"llm_vision_model": "ep-vision"}), respx_mock)
    out = await client.complete_vision([{"role": "user", "content": "x"}])
    assert out == "转写文本" and route.call_count == 2
    assert "thinking" in json.loads(route.calls[0].request.content)
    assert "thinking" not in json.loads(route.calls[1].request.content)
    await client.close()


async def test_complete_vision_model_unconfigured_unavailable(llm_settings):
    # 视觉模型配置位为空（未启用）→ LlmUnavailable，业务层降级为普通附件
    client = ArkClient(llm_settings.model_copy(update={"llm_vision_model": ""}))
    with pytest.raises(LlmUnavailable):
        await client.complete_vision([{"role": "user", "content": "x"}])
    await client.close()


async def test_complete_vision_connection_error_retries_once(respx_mock, llm_settings):
    # 连接级故障（网络抖动/瞬时不可达）秒级重试一次即恢复：不计失败、用户无感（2026-10-23 误杀复盘）
    route = respx_mock.post("https://ark.test/v3/chat/completions")
    route.side_effect = [httpx.ConnectError("connection reset"), httpx.Response(200, text=completion_body("转写文本"))]
    client = mocked_client(llm_settings.model_copy(update={"llm_vision_model": "ep-vision"}), respx_mock)
    out = await client.complete_vision([{"role": "user", "content": "x"}])
    assert out == "转写文本" and route.call_count == 2 and client.consecutive_failures == 0
    await client.close()


async def test_complete_vision_connection_error_twice_counts_one_failure(respx_mock, llm_settings):
    # 连续连接故障：重试后仍败 → 按一次请求级失败计入熔断，超时类不在此重试口径内
    route = respx_mock.post("https://ark.test/v3/chat/completions")
    route.side_effect = [httpx.ConnectError("connection reset"), httpx.ConnectError("connection reset")]
    client = mocked_client(llm_settings.model_copy(update={"llm_vision_model": "ep-vision"}), respx_mock)
    with pytest.raises(LlmUnavailable):
        await client.complete_vision([{"role": "user", "content": "x"}])
    assert route.call_count == 2 and client.consecutive_failures == 1
    await client.close()


async def test_blank_key_unavailable_before_http(llm_settings):
    client = ArkClient(llm_settings.model_copy(update={"llm_api_key": ""}))
    assert not client.available()
    with pytest.raises(LlmUnavailable):
        await collect(client)
    await client.close()


class BrokenStream(httpx.AsyncByteStream):
    def __init__(self, error):
        self.error, self.closed = error, False
        self.started = asyncio.Event()

    async def __aiter__(self):
        self.started.set()
        yield sse_body("half")[:150].encode()
        if self.error:
            raise self.error("stream disconnected")
        await asyncio.Event().wait()

    async def aclose(self):
        self.closed = True


@pytest.mark.parametrize("error", [httpx.ReadError, httpx.RemoteProtocolError, httpx.ReadTimeout])
async def test_stream_read_error_retried_counted_and_resource_closed(llm_settings, error):
    # 流读取中断属可重试瞬时错误（2026-10-15 拍板）：换一条新流自动重试 1 次，仍败计一次请求级失败
    streams, calls = [], 0

    def handler(request):
        nonlocal calls
        calls += 1
        stream = BrokenStream(error)
        streams.append(stream)
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=stream)

    transport = httpx.MockTransport(handler)
    sdk = AsyncOpenAI(api_key="fake", base_url="https://ark.test/v3", http_client=httpx.AsyncClient(transport=transport), max_retries=0)
    client = ArkClient(llm_settings, client=sdk, retry_delay=0)
    with pytest.raises(LlmUnavailable):
        await collect(client)
    assert calls == 2 and client.consecutive_failures == 1 and all(stream.closed for stream in streams)
    await client.close()


async def test_cancellation_closes_resource_without_failure_count(llm_settings):
    broken = BrokenStream(None)
    transport = httpx.MockTransport(lambda request: httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=broken))
    sdk = AsyncOpenAI(api_key="fake", base_url="https://ark.test/v3", http_client=httpx.AsyncClient(transport=transport), max_retries=0)
    client = ArkClient(llm_settings, client=sdk)
    task = asyncio.create_task(collect(client))
    await broken.started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert broken.closed and client.consecutive_failures == 0
    await client.close()
