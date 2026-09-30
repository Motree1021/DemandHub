import asyncio
import json

import httpx
import pytest
from openai import AsyncOpenAI

from app.agent.llm_client import ArkClient, LlmUnavailable
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


async def test_http_500_fails_fast_and_actual_settings_cooldown(respx_mock, llm_settings):
    route = respx_mock.post("https://ark.test/v3/chat/completions").respond(500, json={"error": {"message": "upstream-secret"}})
    client = mocked_client(llm_settings, respx_mock, clock=lambda: 100)
    for _ in range(3):
        with pytest.raises(LlmUnavailable):
            await collect(client)
    assert route.call_count == 3  # SDK重试已经关闭。
    assert not client.available() and client.cooldown_until == 160
    with pytest.raises(LlmUnavailable):
        await collect(client)
    assert route.call_count == 3
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
async def test_stream_read_error_counted_and_resource_closed(llm_settings, error):
    broken = BrokenStream(error)
    transport = httpx.MockTransport(lambda request: httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=broken))
    sdk = AsyncOpenAI(api_key="fake", base_url="https://ark.test/v3", http_client=httpx.AsyncClient(transport=transport), max_retries=0)
    client = ArkClient(llm_settings, client=sdk)
    with pytest.raises(LlmUnavailable):
        await collect(client)
    assert client.consecutive_failures == 1 and broken.closed
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
