import asyncio
import json
import time

import pytest
from sqlalchemy import func, select

from app.agent.guide import GuideService
from app.agent.llm_client import ArkClient, StreamEvent
from app.agent.schemas import GuideChatRequest
from app.config import Settings
from app.core.errors import BizError
from app.db.models import AgentMessage, AgentSession, Demand, PromptVersion, User
from app.services import demand_service, session_service


class FakeArk(ArkClient):
    def __init__(self, output=None, repair=None, gate=False):
        self.settings = Settings(app_env="test", demandhub_database_url="mysql://test:test@localhost/demandhub_test", jwt_secret="test-secret-that-is-long-enough-32", llm_api_key="fake-test-key")
        self.clock = time.monotonic
        self.consecutive_failures = 0
        self.cooldown_until = 0
        self.calls = self.repairs = 0
        self.output = output if output is not None else {"structured": {}, "elements": []}
        self.repair = repair if repair is not None else self.output
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        if not gate:
            self.release.set()

    async def stream_json(self, messages):
        self.calls += 1
        self.started.set()
        await self.release.wait()
        yield StreamEvent("final", raw=self.raw(self.output), usage={"prompt_tokens": 10, "completion_tokens": 20})

    async def complete_json(self, messages):
        self.repairs += 1
        return StreamEvent("final", raw=self.raw(self.repair), usage={})

    @staticmethod
    def raw(output):
        return output if isinstance(output, str) else json.dumps(output, ensure_ascii=False)


async def make_draft(factory, user, *, type_code="TECH", extra=None, request="create-1"):
    payload = {"clientRequestId": request, "title": "渠道日报", "demandTypeCode": type_code, "content": "客户经理每天需要查看渠道业务日报", "fieldSources": {"demandTypeCode": "default"}, **(extra or {})}
    async with factory() as db:
        async with db.begin():
            demand = await demand_service.create_draft(db, user, payload)
            session = await session_service.create(db, user, "SUBMIT_GUIDE", demand.id)
            return demand.id, session.id, demand.revision


def request(demand_id, session_id, revision=0, request_id="turn-1", message="需要一份业务日报"):
    return GuideChatRequest(demandId=demand_id, sessionId=session_id, revision=revision, requestId=request_id, message=message)


async def message_count(factory):
    async with factory() as db:
        return (await db.execute(select(func.count()).select_from(AgentMessage))).scalar_one()


async def test_first_question_is_saved_target_and_success_commits_before_message(session_factory, user):
    did, sid, revision = await make_draft(session_factory, user)
    fake = FakeArk({"structured": {"elements": {"A": {"techSubtype": "DATA_RPT"}}}, "elements": []})
    req = request(did, sid, revision)
    async with session_factory() as db:
        stream = GuideService(db, user, fake).stream(req)
        assert "event: processing" in await anext(stream)
        first = await anext(stream)
        assert "event: message" in first and "紧急" in first
        async with session_factory() as observer:
            persisted = await observer.get(Demand, did)
            session = await observer.get(AgentSession, sid)
            saved = (await observer.execute(select(AgentMessage).where(AgentMessage.role == "ASSISTANT"))).scalar_one()
            version = await observer.get(PromptVersion, saved.prompt_version_id)
            assert persisted.revision == revision + 1
            assert session.asked_target == saved.structured_payload["askedTarget"] == "urgency"
            assert "{{standard_section}}" in version.snapshot["promptTemplate"]
            assert "{{standard_section}}" not in version.snapshot["renderedPrompt"]
            assert len(version.snapshot["injectedStandards"]) == 3
        structured, done = await anext(stream), await anext(stream)
        assert "event: structured" in structured and '"revision":1' in structured
        assert '"status":"completed"' in done
        await stream.aclose()
    assert await message_count(session_factory) == 2


async def test_duplicate_success_replays_after_revision_and_state_change(session_factory, user):
    did, sid, rev = await make_draft(session_factory, user, type_code="MATL")
    fake = FakeArk()
    req = request(did, sid, rev)
    async with session_factory() as db:
        first = await GuideService(db, user, fake).execute(req)
    async with session_factory() as db:
        async with db.begin():
            await demand_service.submit(db, user, did, first.revision)
    fake.settings = fake.settings.model_copy(update={"llm_api_key": ""})
    async with session_factory() as db:
        replay = await GuideService(db, user, fake).execute(req)
    assert first.model_dump() == replay.model_dump() and fake.calls == 1
    assert await message_count(session_factory) == 2
    async with session_factory() as db:
        with pytest.raises(BizError) as error:
            await GuideService(db, user, fake).execute(req.model_copy(update={"message": "不同输入"}))
        assert error.value.code == 409


async def test_concurrent_same_request_calls_model_once(session_factory, user):
    did, sid, rev = await make_draft(session_factory, user)
    fake = FakeArk()
    req = request(did, sid, rev)
    async def run():
        async with session_factory() as db:
            return await GuideService(db, user, fake).execute(req)
    first, second = await asyncio.gather(run(), run())
    assert first == second and fake.calls == 1
    assert await message_count(session_factory) == 2


@pytest.mark.parametrize("competitor", ["hand_edit", "submit"])
async def test_model_waiting_has_no_lock_and_revision_rejects_competing_write(session_factory, user, competitor):
    did, sid, rev = await make_draft(session_factory, user, type_code="MATL")
    fake = FakeArk({"structured": {"ext": {"quantity": 50}}, "elements": []}, gate=True)
    async with session_factory() as db:
        task = asyncio.create_task(GuideService(db, user, fake).execute(request(did, sid, rev)))
        await fake.started.wait()
        assert not db.in_transaction()
        async with session_factory() as rival:
            async with rival.begin():
                if competitor == "hand_edit":
                    await asyncio.wait_for(demand_service.update_draft(rival, user, did, {"expectedRevision": rev, "title": "手工修改日报"}), 2)
                else:
                    await asyncio.wait_for(demand_service.submit(rival, user, did, rev), 2)
        fake.release.set()
        with pytest.raises(BizError) as error:
            await task
        assert error.value.code == 409
    assert await message_count(session_factory) == 0


async def test_saved_stream_interrupted_can_recover_same_request(session_factory, user):
    did, sid, rev = await make_draft(session_factory, user)
    fake = FakeArk()
    req = request(did, sid, rev)
    async with session_factory() as db:
        stream = GuideService(db, user, fake).stream(req)
        await anext(stream)
        await anext(stream)  # 保存成功后客户端断线。
        await stream.aclose()
    async with session_factory() as db:
        response = await GuideService(db, user, fake).execute(req)
    assert response.revision == rev + 1 and fake.calls == 1
    assert await message_count(session_factory) == 2


async def test_cancellation_before_save_has_no_half_success_and_releases_mutex(session_factory, user):
    did, sid, rev = await make_draft(session_factory, user)
    fake = FakeArk(gate=True)
    async with session_factory() as db:
        task = asyncio.create_task(GuideService(db, user, fake).execute(request(did, sid, rev)))
        await fake.started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert await message_count(session_factory) == 0
    fake.release.set()
    async with session_factory() as db:
        await asyncio.wait_for(GuideService(db, user, fake).execute(request(did, sid, rev)), 2)
    assert await message_count(session_factory) == 2


@pytest.mark.parametrize("output", ["not json", {"structured": {"demandTypeCode": "UNKNOWN"}, "elements": []}, {"structured": {"demandTypeCode": []}, "elements": []}, {"structured": {}, "elements": [{"key": "unknown", "status": "OK"}]}, {"structured": {}, "elements": [{"key": "title", "status": "OK"}, {"key": "title", "status": "OK"}]}])
async def test_invalid_complete_output_repairs_once_then_counts_failure(session_factory, user, output):
    did, sid, rev = await make_draft(session_factory, user)
    fake = FakeArk(output)
    for number in range(3):
        async with session_factory() as db:
            with pytest.raises(BizError) as error:
                await GuideService(db, user, fake).execute(request(did, sid, rev, request_id=f"bad-{number}"))
            assert error.value.code == 1401
    assert fake.calls == fake.repairs == 3
    assert not fake.available() and fake.consecutive_failures == 3
    assert await message_count(session_factory) == 0


async def test_repair_validates_then_clears_failure_count(session_factory, user):
    did, sid, rev = await make_draft(session_factory, user)
    fake = FakeArk("malformed", repair={"structured": {}, "elements": []})
    fake.consecutive_failures = 2
    async with session_factory() as db:
        response = await GuideService(db, user, fake).execute(request(did, sid, rev))
    assert response.revision == 1 and fake.repairs == 1 and fake.consecutive_failures == 0


async def test_atomic_db_failure_emits_error_without_done_or_half_messages(session_factory, user, monkeypatch):
    did, sid, rev = await make_draft(session_factory, user)
    original = session_service.append
    async def fail_second(db, session_id, role, content, *args, **kwargs):
        if role == "ASSISTANT":
            raise RuntimeError("database-write-failure")
        return await original(db, session_id, role, content, *args, **kwargs)
    monkeypatch.setattr(session_service, "append", fail_second)
    async with session_factory() as db:
        events = [e async for e in GuideService(db, user, FakeArk()).stream(request(did, sid, rev))]
    assert any("event: error" in event for event in events)
    assert not any("event: done" in event or "event: structured" in event or "event: message" in event for event in events)
    assert await message_count(session_factory) == 0
    async with session_factory() as db:
        assert (await db.get(Demand, did)).revision == rev


async def test_unique_session_owned_draft_and_two_drafts_isolate(session_factory, user):
    did, sid, rev = await make_draft(session_factory, user)
    other_did, other_sid, _ = await make_draft(session_factory, user, request="create-2")
    async with session_factory() as db:
        async with db.begin():
            same = await session_service.create(db, user, "SUBMIT_GUIDE", did)
            assert same.id == sid
    async with session_factory() as db:
        with pytest.raises(BizError) as error:
            await GuideService(db, user, FakeArk()).execute(request(did, other_sid, rev))
        assert error.value.code == 409
    async with session_factory() as db:
        async with db.begin():
            another = User(name="另一用户", wecom_userid="other-user")
            db.add(another)
            await db.flush()
        with pytest.raises(BizError) as error:
            await session_service.messages(db, another, sid)
        assert error.value.code == 1402
    assert other_did != did
