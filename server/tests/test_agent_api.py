import json

from app.agent.llm_client import get_llm_client
from tests.test_guide import FakeArk


async def setup(client, auth_headers):
    draft = (await client.post("/demandhub-api/demand", headers=auth_headers, json={"clientRequestId": "api-draft", "title": "渠道日报", "content": "客户经理每天需要查看渠道日报", "demandTypeCode": "TECH", "fieldSources": {"demandTypeCode": "default"}})).json()["data"]
    session = (await client.post("/demandhub-api/agent/session", headers=auth_headers, json={"demandId": draft["id"], "scene": "SUBMIT_GUIDE"})).json()["data"]
    return {"demandId": draft["id"], "sessionId": session["id"], "requestId": "api-turn", "revision": draft["revision"], "message": "要一个数据报表"}


def override(client, fake):
    client._transport.app.dependency_overrides[get_llm_client] = lambda: fake


async def test_success_sse_contract_immediate_query_and_replay(client, auth_headers):
    req = await setup(client, auth_headers)
    fake = FakeArk({"structured": {"ext": {"techSubtype": "DATA_RPT"}}, "elements": []})
    override(client, fake)
    response = await client.post("/demandhub-api/agent/guide/chat/stream", headers=auth_headers, json=req)
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["x-accel-buffering"] == "no"
    events = [chunk.splitlines()[0] for chunk in response.text.strip().split("\n\n")]
    assert events == ["event: processing", "event: message", "event: structured", "event: done"]
    messages = (await client.get(f'/demandhub-api/agent/session/{req["sessionId"]}/messages', headers=auth_headers)).json()["data"]
    assert len(messages) == 2 and isinstance(messages[-1]["structuredPayload"], str)
    payload = json.loads(messages[-1]["structuredPayload"])
    assert payload["revision"] == 1 and payload["askedTarget"] == "businessScenario"
    again = await client.post("/demandhub-api/agent/guide/chat", headers=auth_headers, json=req)
    assert again.json()["code"] == 0 and fake.calls == 1
    req["message"] = "换一个消息"
    assert (await client.post("/demandhub-api/agent/guide/chat/stream", headers=auth_headers, json=req)).json()["code"] == 409


async def test_unavailable_before_sse_is_json_and_extra_form_context_rejected(client, auth_headers):
    req = await setup(client, auth_headers)
    fake = FakeArk()
    fake.settings = fake.settings.model_copy(update={"llm_api_key": ""})
    override(client, fake)
    response = await client.post("/demandhub-api/agent/guide/chat/stream", headers=auth_headers, json=req)
    assert response.headers["content-type"].startswith("application/json") and response.json()["code"] == 1401
    req["formContext"] = {"title": "旁路"}
    assert (await client.post("/demandhub-api/agent/guide/chat/stream", headers=auth_headers, json=req)).json()["code"] == 400


async def test_invalid_model_stream_explicit_error_eof_no_success(client, auth_headers):
    req = await setup(client, auth_headers)
    override(client, FakeArk("bad json"))
    response = await client.post("/demandhub-api/agent/guide/chat/stream", headers=auth_headers, json=req)
    assert "event: error" in response.text and '"code":1401' in response.text
    assert "event: done" not in response.text and "event: structured" not in response.text


async def test_authenticated_standard_api_camel_case_and_list_code(client, auth_headers):
    assert (await client.get("/demandhub-api/standards")).status_code == 401
    values = (await client.get("/demandhub-api/standards", headers=auth_headers)).json()["data"]
    assert {s["code"] for s in values} == {"TECH", "MATL", "TRAIN"}
    std = (await client.get("/demandhub-api/standards/TECH", headers=auth_headers)).json()["data"]
    assert "optionalFields" in std and "followUpOrder" in std and "optional_fields" not in std
