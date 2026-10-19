import asyncio
import json

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


async def _last_manual_change(session_factory, user, session_id):
    """手改播报（kind=manualChange）不再是最后一条消息——2026-10-19 起播报后还有流程接续消息。"""
    from app.services import session_service
    async with session_factory() as db:
        messages = await session_service.messages(db, user, session_id)
    return next(m for m in reversed(messages)
                if isinstance(m.structured_payload, dict) and m.structured_payload.get("kind") == "manualChange")


async def test_manual_change_broadcast_filled_and_updated(session_factory, user):
    demand_id, session_id = await _draft_with_session(session_factory, user, "broadcast-1")
    async with session_factory() as db:
        async with db.begin():
            await service.update_draft(db, user, demand_id, {"expectedRevision": 0,
                "elements": {"D": {"acceptanceCriteria": "音色更具特色"}}, "notifyChanges": True})
    message = await _last_manual_change(session_factory, user, session_id)
    assert message.role == "ASSISTANT"
    assert "你已手动填写了「验收标准」：音色更具特色" in message.content
    assert message.structured_payload == {"kind": "manualChange",
        "changes": [{"action": "fill", "key": "acceptanceCriteria", "label": "验收标准", "old": "", "new": "音色更具特色"}]}
    async with session_factory() as db:
        async with db.begin():
            await service.update_draft(db, user, demand_id, {"expectedRevision": 1,
                "elements": {"D": {"acceptanceCriteria": "发音准确，多音字、金融术语都能读对"}}, "notifyChanges": True})
    message = await _last_manual_change(session_factory, user, session_id)
    assert "你已手动更新了「验收标准」：由「音色更具特色」改为「发音准确，多音字、金融术语都能读对」" in message.content
    assert message.structured_payload["changes"][0] == {"action": "update", "key": "acceptanceCriteria", "label": "验收标准",
        "old": "音色更具特色", "new": "发音准确，多音字、金融术语都能读对"}


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
    message = await _last_manual_change(session_factory, user, session_id)
    # enum 播报标签而非代码；多项改动逐行列出
    assert "你已手动更新了「紧急程度」：由「普通」改为「紧急」" in message.content
    assert "你已手动清空了「目标用户角色」" in message.content
    assert message.structured_payload["changes"] == [
        {"action": "update", "key": "urgency", "label": "紧急程度", "old": "普通", "new": "紧急"},
        {"action": "clear", "key": "userRole", "label": "目标用户角色", "old": "客户经理", "new": ""}]


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


async def test_manual_change_follow_up_resume(session_factory, user):
    """手改后的流程接续（2026-10-19 拍板问题②）：播报后 AI 不停顿——追问下一必填缺口、
    手改清空的必填项被重问、必填齐时给完成话术；agent_session.asked_target 同步更新。"""
    from app.db.models import AgentSession
    demand_id, session_id = await _draft_with_session(session_factory, user, "resume-1")
    # 手填一项必填：接续追问下一缺口（刚填的角色不再问），revision 用新值，无 kind 可回放
    async with session_factory() as db:
        async with db.begin():
            await service.update_draft(db, user, demand_id, {"expectedRevision": 0,
                "elements": {"C": {"userRole": "客户经理"}}, "notifyChanges": True})
    follow = await _last_message(session_factory, user, session_id)
    assert follow.role == "ASSISTANT"
    payload = follow.structured_payload
    assert "kind" not in payload
    assert payload["askedTarget"] and payload["askedTarget"] != "userRole"
    assert payload["revision"] == 1 and payload["canSubmit"] is False
    assert payload["elements"] and payload["structured"]["elements"]["C"]["userRole"] == "客户经理"
    assert follow.content == payload["reply"]
    async with session_factory() as db:
        agent_session = await db.get(AgentSession, session_id)
        assert agent_session.asked_target == payload["askedTarget"]
    # 手改清空必填项：接续重问该缺口
    async with session_factory() as db:
        async with db.begin():
            await service.update_draft(db, user, demand_id, {"expectedRevision": 1,
                "elements": {"C": {"userRole": None}}, "notifyChanges": True})
    follow = await _last_message(session_factory, user, session_id)
    assert follow.structured_payload["askedTarget"] == "userRole"
    # 必填全填：接续给完成话术，引导结束
    async with session_factory() as db:
        async with db.begin():
            await service.update_draft(db, user, demand_id, {"expectedRevision": 2, "urgency": "NORMAL",
                "content": "整理需求并记录完整业务信息",
                "elements": {"C": {"userRole": "客户经理", "userGoal": "晨会前快速掌握各机构持仓汇总情况",
                                   "useScenario": "客户经理每天晨会前查各机构持仓汇总",
                                   "painPoint": "手工汇总20个机构数据要40分钟且易出错"},
                             "D": {"functionDescription": "自动生成持仓汇总报表并推送到企微群",
                                   "inputOutput": "输入交易流水，输出按机构汇总的持仓报表",
                                   "acceptanceCriteria": "连续5个工作日8点前生成且与核心对账一致"}},
                "notifyChanges": True})
    follow = await _last_message(session_factory, user, session_id)
    assert follow.structured_payload["canSubmit"] is True
    assert follow.structured_payload["guidanceComplete"] is True
    assert follow.structured_payload["askedTarget"] is None
    assert "可以提交" in follow.content


class _FakeManualArk:
    """手改跨要素抽取的假模型（2026-10-19 拍板）：只实现 available/complete_json 两个被调用的方法。"""
    def __init__(self, output=None, error=None):
        self.output = output or {"structured": {}, "elements": []}
        self.error = error

    def available(self):
        return True

    async def complete_json(self, messages):
        if self.error:
            raise self.error
        from app.agent.llm_client import StreamEvent
        return StreamEvent("final", raw=json.dumps(self.output, ensure_ascii=False), usage={})


async def test_manual_long_text_triggers_model_extraction(session_factory, user, monkeypatch):
    """手填长文本触发补充式抽取（2026-10-19 拍板）：跨要素信息归位（agent 来源）、
    手填字段不被改写（user 来源保护）、引述确认只列额外抽出的要素（手填项播报已告知）。"""
    import app.agent.llm_client as llm_module
    demand_id, session_id = await _draft_with_session(session_factory, user, "extract-1")
    fake = _FakeManualArk({"structured": {"elements": {"C": {"userRole": "客户经理"}}}, "elements": []})
    monkeypatch.setattr(llm_module, "get_llm_client", lambda: fake)
    async with session_factory() as db:
        async with db.begin():
            await service.update_draft(db, user, demand_id, {"expectedRevision": 0,
                "elements": {"C": {"useScenario": "客户经理每天晨会前查各机构持仓并导出"}}, "notifyChanges": True})
    async with session_factory() as db:
        d = await db.get(Demand, demand_id)
        # 手填字段原样保留；抽中的角色归位、agent 来源
        assert d.elements["C"]["useScenario"] == "客户经理每天晨会前查各机构持仓并导出"
        assert d.elements["C"]["userRole"] == "客户经理"
        assert (d.field_sources or {}).get("elements.C.userRole") == "agent"
    follow = await _last_message(session_factory, user, session_id)
    assert "kind" not in follow.structured_payload
    assert "「目标用户角色」已按你补充的更新" in follow.content
    assert "使用场景」已按你补充的更新" not in follow.content


async def test_manual_extraction_failure_falls_back_to_rules(session_factory, user, monkeypatch):
    """模型失败静默降级（2026-10-19 拍板）：保存不受阻，接续退化为规则重算，无抽取归位。"""
    import app.agent.llm_client as llm_module
    demand_id, session_id = await _draft_with_session(session_factory, user, "extract-2")
    monkeypatch.setattr(llm_module, "get_llm_client", lambda: _FakeManualArk(error=RuntimeError("上游故障")))
    async with session_factory() as db:
        async with db.begin():
            await service.update_draft(db, user, demand_id, {"expectedRevision": 0,
                "elements": {"C": {"useScenario": "客户经理每天晨会前查各机构持仓并导出"}}, "notifyChanges": True})
    follow = await _last_message(session_factory, user, session_id)
    assert follow.structured_payload["askedTarget"]
    async with session_factory() as db:
        assert (await db.get(Demand, demand_id)).elements["C"].get("userRole") is None


async def test_submit_backfills_content_from_first_user_message(session_factory, user):
    """提交兜底回填（2026-10-19 拍板，仅科技需求）：底稿空 → 取会话首条用户消息，来源 user。"""
    from app.services import session_service
    data = payload("backfill-1")
    data["content"] = None
    async with session_factory() as db:
        async with db.begin():
            d = await service.create_draft(db, user, data)
            session = await session_service.create(db, user, "SUBMIT_GUIDE", d.id)
            await session_service.append(db, session.id, "USER", "报表想加个按机构导出")
            demand_id = d.id
    async with session_factory() as db:
        async with db.begin():
            d = await service.submit(db, user, demand_id, 0)
    assert d.content == "报表想加个按机构导出"
    assert (d.field_sources or {}).get("content") == "user"


async def test_submit_backfills_content_from_title_when_no_chat(session_factory, user):
    """提交兜底回填：纯手改没聊过（无会话）→ 标题兜底，不拦提交。"""
    data = payload("backfill-2")
    data["content"] = None
    async with session_factory() as db:
        async with db.begin():
            d = await service.create_draft(db, user, data)
            demand_id = d.id
    async with session_factory() as db:
        async with db.begin():
            d = await service.submit(db, user, demand_id, 0)
    assert d.content == "需求记录"
    assert (d.field_sources or {}).get("content") == "user"


async def test_submit_matl_does_not_backfill_content(session_factory, user):
    """MATL/TRAIN 维持现状（待独立助手重建）：content 仍必填，不兜底、照拦。"""
    from app.core.errors import BizError
    async with session_factory() as db:
        async with db.begin():
            d = await service.create_draft(db, user, {"clientRequestId": "backfill-3", "demandTypeCode": "MATL",
                                                      "title": "宣传折页", "urgency": "NORMAL",
                                                      "ext": {"materialSubtype": "宣传折页", "quantity": 100}})
            demand_id = d.id
    async with session_factory() as db:
        async with db.begin():
            with pytest.raises(BizError, match="需求描述"):
                await service.submit(db, user, demand_id, 0)
