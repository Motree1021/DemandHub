import asyncio

import pytest
from sqlalchemy import func, select

from app.db.models import Demand, DemandNoSeq
from app.services import demand_service as service
from app.standards.loader import get


def payload(key):
    # 五区标准下 TECH 提交需补齐 A/C/D 区必填（B 区 P1 阶段条件必填不生效）
    return {"clientRequestId": key, "title": "需求记录", "demandTypeCode": "TECH", "content": "整理需求并记录完整业务信息",
            "urgency": "NORMAL",
            "elements": {"A": {"techSubtype": "DATA_RPT"},
                         "C": {"userRole": "客户经理", "userGoal": "晨会前快速查看各机构持仓汇总",
                               "useScenario": "客户经理每天晨会前查看各机构持仓", "painPoint": "手工汇总20多个机构持仓每次近1小时"},
                         "D": {"functionDescription": "按机构汇总前一交易日持仓并展示", "inputOutput": "输入交易流水输出持仓汇总报表",
                               "acceptanceCriteria": "连续7天与核心系统对账误差为0"}}}


async def test_twenty_actual_demands_concurrently(session_factory, user):
    async def create_and_submit(index):
        async with session_factory() as db:
            async with db.begin():
                d = await service.create_draft(db, user, payload(f"parallel-{index}"))
                return (await service.submit(db, user, d.id, 0)).demand_no
    numbers = await asyncio.gather(*(create_and_submit(i) for i in range(20)))
    assert len(set(numbers)) == 20
    assert sorted(int(n.split("-")[-1]) for n in numbers) == list(range(1, 21))
    async with session_factory() as db:
        assert (await db.execute(select(func.count()).select_from(Demand).where(Demand.status == "SUBMITTED"))).scalar_one() == 20


async def test_same_create_and_submit_concurrent(session_factory, user):
    async def create():
        async with session_factory() as db:
            async with db.begin():
                return (await service.create_draft(db, user, payload("shared-create"))).id
    ids = await asyncio.gather(*(create() for _ in range(10)))
    assert len(set(ids)) == 1
    async def submit():
        async with session_factory() as db:
            async with db.begin():
                return (await service.submit(db, user, ids[0], 0)).demand_no
    numbers = await asyncio.gather(*(submit() for _ in range(10)))
    assert len(set(numbers)) == 1
    async with session_factory() as db:
        assert (await db.execute(select(DemandNoSeq.seq))).scalar_one() == 1


async def test_rollback_returns_number_and_session_state(session_factory, user):
    from app.services.session_service import create
    async with session_factory() as db:
        async with db.begin():
            demand = await service.create_draft(db, user, payload("rollback"))
            session = await create(db, user, "SUBMIT_GUIDE", demand.id)
            demand_id, session_id = demand.id, session.id
    async with session_factory() as db:
        with pytest.raises(RuntimeError):
            async with db.begin():
                await service.submit(db, user, demand_id, 0)
                raise RuntimeError("模拟事务失败")
    from app.db.models import AgentSession
    async with session_factory() as db:
        assert (await db.get(Demand, demand_id)).demand_no is None
        assert (await db.get(AgentSession, session_id)).status == "ACTIVE"
        assert (await db.execute(select(func.count()).select_from(DemandNoSeq))).scalar_one() == 0
    async with session_factory() as db:
        async with db.begin():
            assert (await service.submit(db, user, demand_id, 0)).demand_no.endswith("-001")


async def test_agent_sources_and_cleared_user_protection(session_factory, user):
    async with session_factory() as db:
        async with db.begin():
            d = await service.create_draft(db, user, {"clientRequestId": "sources", "demandTypeCode": "TECH", "fieldSources": {"demandTypeCode": "default"}})
            await service.update_draft(db, user, d.id, {"expectedRevision": 0, "title": "", "fieldSources": {"title": "user"}})
            full = {**service.form_of(d), "title": "模型填充", "content": "模型摘要"}
            d = await service.apply_agent_patch(db, user, d, expected_revision=1, patch=full, field_sources={"demandTypeCode": "default", "urgency": "default"})
            assert d.title is None and d.field_sources["title"] == "user"
            assert d.content == "模型摘要" and d.field_sources["content"] == "agent"
            assert d.field_sources["demandTypeCode"] == "default"


async def test_history_snapshot_survives_live_standard_change(client, auth_headers, monkeypatch):
    from app.standards.loader import loader
    response = await client.post("/demandhub-api/demand", headers=auth_headers, json=payload("snapshot"))
    draft = response.json()["data"]
    submitted = await client.post(f"/demandhub-api/demand/{draft['id']}/submit", headers=auth_headers, json={"expectedRevision": 0})
    assert submitted.json()["code"] == 0
    original = get("TECH")
    replacement = original.model_copy(deep=True, update={"name": "新标准名称", "version": "999"})
    monkeypatch.setitem(loader._standards, "TECH", replacement)
    detail = await client.get(f"/demandhub-api/demand/{draft['id']}", headers=auth_headers)
    assert detail.json()["data"]["standard"]["version"] == original.version
    assert detail.json()["data"]["standard"]["name"] == original.name


async def _draft_with_session(session_factory, user, key):
    """建草稿并绑定提报会话（播报目标），返回 (demand_id, session_id)。"""
    from app.services import session_service
    async with session_factory() as db:
        async with db.begin():
            d = await service.create_draft(db, user, {"clientRequestId": key, "demandTypeCode": "TECH",
                                                      "title": "语音播报优化", "content": "整理需求"})
            session = await session_service.create(db, user, "SUBMIT_GUIDE", d.id)
            return d.id, session.id


async def _last_message(session_factory, user, session_id):
    from app.services import session_service
    async with session_factory() as db:
        return (await session_service.messages(db, user, session_id))[-1]


async def test_manual_change_broadcast_filled_and_updated(session_factory, user):
    demand_id, session_id = await _draft_with_session(session_factory, user, "broadcast-1")
    async with session_factory() as db:
        async with db.begin():
            await service.update_draft(db, user, demand_id, {"expectedRevision": 0,
                "elements": {"D": {"acceptanceCriteria": "音色更具特色"}}, "notifyChanges": True})
    message = await _last_message(session_factory, user, session_id)
    assert message.role == "ASSISTANT"
    assert "你已手动填写了「验收标准」：音色更具特色" in message.content
    async with session_factory() as db:
        async with db.begin():
            await service.update_draft(db, user, demand_id, {"expectedRevision": 1,
                "elements": {"D": {"acceptanceCriteria": "发音准确，多音字、金融术语都能读对"}}, "notifyChanges": True})
    message = await _last_message(session_factory, user, session_id)
    assert "你已手动更新了「验收标准」：由「音色更具特色」改为「发音准确，多音字、金融术语都能读对」" in message.content


async def test_manual_change_broadcast_enum_label_and_clear(session_factory, user):
    demand_id, session_id = await _draft_with_session(session_factory, user, "broadcast-2")
    async with session_factory() as db:
        async with db.begin():
            await service.update_draft(db, user, demand_id, {"expectedRevision": 0, "urgency": "NORMAL",
                "elements": {"C": {"userRole": "客户经理"}}})
    async with session_factory() as db:
        async with db.begin():
            await service.update_draft(db, user, demand_id, {"expectedRevision": 1, "urgency": "URGENT",
                "elements": {"C": {"userRole": None}}, "notifyChanges": True})
    message = await _last_message(session_factory, user, session_id)
    # enum 播报标签而非代码；多项改动逐行列出
    assert "你已手动更新了「紧急程度」：由「普通」改为「紧急」" in message.content
    assert "你已手动清空了「目标用户角色」" in message.content


async def test_manual_change_broadcast_guards(session_factory, user):
    from app.db.models import AgentMessage
    demand_id, session_id = await _draft_with_session(session_factory, user, "broadcast-3")
    async with session_factory() as db:
        async with db.begin():
            await service.update_draft(db, user, demand_id, {"expectedRevision": 0,
                "elements": {"D": {"acceptanceCriteria": "连续7天对账为0"}}})
    async with session_factory() as db:
        assert (await db.execute(select(func.count()).select_from(AgentMessage)
                                 .where(AgentMessage.session_id == session_id))).scalar_one() == 0
    # 无会话草稿带播报标志：只保存不播报、不报错
    async with session_factory() as db:
        async with db.begin():
            d = await service.create_draft(db, user, {"clientRequestId": "broadcast-4", "demandTypeCode": "TECH",
                                                      "title": "无会话草稿", "content": "x"})
            orphan_id = d.id
    async with session_factory() as db:
        async with db.begin():
            await service.update_draft(db, user, orphan_id, {"expectedRevision": 0,
                "elements": {"D": {"acceptanceCriteria": "y"}}, "notifyChanges": True})
