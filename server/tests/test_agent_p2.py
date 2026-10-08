"""P2 验收：判型确认/改判（FR-01/FR-03）、大段拆解原文保真（FR-02/D6）、FR-08 新增事实过滤、BR-T13 粒度治理、FR-06 修改留痕。"""
import json

import pytest
from sqlalchemy import select

from app.agent.guide import GuideService
from app.agent.policy import impact_hints, process
from app.agent.schemas import GuideChatRequest, ModelOutput, parse_model_output
from app.db.models import Demand, DemandChangeLog
from app.services import demand_service, session_service
from app.standards.rules import business_confirmed
from tests.test_guide import FakeArk

FORM = {"title": "晨会持仓报表", "demandTypeCode": "TECH", "content": "机构业务部客户经理每天晨会前查看持仓", "urgency": "NORMAL"}

ACD = {"A": {"techSubtype": "DATA_RPT"},
       "C": {"userRole": "客户经理", "userGoal": "晨会前快速查看各机构持仓汇总",
             "useScenario": "客户经理每天晨会前查看各机构持仓", "painPoint": "手工汇总20多个机构持仓每次近1小时"},
       "D": {"functionDescription": "按机构汇总前一交易日持仓并展示", "inputOutput": "输入交易流水输出持仓汇总报表",
             "acceptanceCriteria": "连续7天与核心系统对账误差为0"}}

ZONE_B = {"businessGoal": "把晨会准备时长从40分钟压缩到5分钟", "businessBackground": "目前客户经理手工整理持仓效率低影响晨会质量",
          "businessValue": "20名客户经理每天节省40分钟", "stakeholders": ["机构业务部", "科技中心"]}

LONG_TEXT = ("机构业务部20名客户经理每天晨会前需要查看各机构前一交易日的持仓汇总，目前靠手工从核心系统导出再逐行整理成Excel，"
             "每次花费近40分钟还容易出错。希望系统每天早上8点前自动按机构汇总持仓并生成报表，支持导出Excel，"
             "连续7天与核心系统对账误差为0就算达标，这样每人每天能节省40分钟。")


def chat_req(demand_id, session_id, revision=0, request_id="p2-1", message="补充业务背景"):
    return GuideChatRequest(demandId=demand_id, sessionId=session_id, revision=revision, requestId=request_id, message=message)


async def make_draft(factory, user, *, content=None, request="p2-create", elements=None):
    payload = {"clientRequestId": request, "title": "持仓报表", "demandTypeCode": "TECH", "fieldSources": {"demandTypeCode": "default"}}
    if content is not None:
        payload["content"] = content
    if elements is not None:
        payload["elements"] = elements
    async with factory() as db:
        async with db.begin():
            demand = await demand_service.create_draft(db, user, payload)
            session = await session_service.create(db, user, "SUBMIT_GUIDE", demand.id)
            return demand.id, session.id, demand.revision


def signals_output(business, user_conf, function):
    return parse_model_output(json.dumps({"structured": {}, "elements": [], "typeSignals": {
        "business": {"confidence": business, "evidence": "部门年度考核指标"},
        "user": {"confidence": user_conf, "evidence": ""},
        "function": {"confidence": function, "evidence": ""}}}, ensure_ascii=False))


# ---- FR-01/FR-03 判型 ----

@pytest.mark.parametrize("business,user_conf,function,expected", [(0.9, 0.4, 0.3, True), (0.2, 0.9, 0.5, False), (0.1, 0.3, 0.8, False)])
def test_type_signals_three_layers_recognized(business, user_conf, function, expected):
    result = process(signals_output(business, user_conf, function), FORM, {}, [], None, {}, "部门年度考核指标需要系统支撑")
    recognition = result["typeRecognition"]
    assert recognition["business"] == business and recognition["user"] == user_conf and recognition["function"] == function
    assert recognition["evidence"]["business"] == "部门年度考核指标"
    assert business_confirmed(recognition) is expected


def test_type_signals_malformed_is_contract_error():
    with pytest.raises(ValueError):
        parse_model_output('{"structured":{},"elements":[],"typeSignals":{"business":{"confidence":1.5}}}')


async def test_user_override_type_keeps_confidence_and_marks_user(session_factory, user):
    did, sid, rev = await make_draft(session_factory, user, content="机构业务部为达成部门年度考核指标，需要把晨会持仓整理从手工40分钟压缩到自动出具")
    fake = FakeArk({"structured": {"elements": {"A": {"techSubtype": "DATA_RPT"}}}, "elements": [],
                    "typeSignals": {"business": {"confidence": 0.9, "evidence": "部门年度考核指标"}, "user": {"confidence": 0.3, "evidence": ""}, "function": {"confidence": 0.2, "evidence": ""}}})
    async with session_factory() as db:
        result = await GuideService(db, user, fake).execute(chat_req(did, sid, rev))
    assert result.type_recognition["business"] == 0.9 and business_confirmed(result.type_recognition)
    async with session_factory() as db:
        demand = await db.get(Demand, did)
        assert demand.ext["typeRecognition"]["business"] == 0.9
        assert demand.field_sources["ext.typeRecognition"] == "agent"
        rev = demand.revision
    async with session_factory() as db:
        async with db.begin():
            demand = await demand_service.update_draft(db, user, did, {"expectedRevision": rev, "ext": {"typeRecognition": {"confirmed": "none"}}})
            # 改判只更新 confirmed，置信度与依据不丢；来源落 user
            assert demand.ext["typeRecognition"]["business"] == 0.9
            assert demand.ext["typeRecognition"]["confirmed"] == "none"
            assert not business_confirmed(demand.ext["typeRecognition"])
            assert demand.field_sources["ext.typeRecognition"] == "user"
        logs = (await db.execute(select(DemandChangeLog).where(DemandChangeLog.demand_id == did, DemandChangeLog.field_key == "ext.typeRecognition"))).scalars().all()
        assert logs and logs[-1].new_value["confirmed"] == "none"


async def test_business_confirmed_submit_requires_zone_b(session_factory, user):
    # 未判型：A/C/D 必填齐全即可提交（B 区不强制）
    async with session_factory() as db:
        async with db.begin():
            plain = await demand_service.create_draft(db, user, {"clientRequestId": "p2-gate-1", "title": "晨会持仓报表", "demandTypeCode": "TECH",
                                                                 "content": "客户经理每天晨会前查看各机构持仓", "urgency": "NORMAL", "elements": ACD})
            assert (await demand_service.submit(db, user, plain.id, 0)).demand_no.startswith("TECH-")
    # 判型确认为业务：B 区必填生效，缺 B 区提交报 400
    async with session_factory() as db:
        async with db.begin():
            demand = await demand_service.create_draft(db, user, {"clientRequestId": "p2-gate-2", "title": "晨会持仓报表", "demandTypeCode": "TECH",
                                                                  "content": "客户经理每天晨会前查看各机构持仓", "urgency": "NORMAL", "elements": ACD})
            did = demand.id
    async with session_factory() as db:
        async with db.begin():
            await demand_service.update_draft(db, user, did, {"expectedRevision": 0, "ext": {"typeRecognition": {"confirmed": "business", "business": 0.9}}})
    async with session_factory() as db:
        with pytest.raises(Exception) as error:
            async with db.begin():
                await demand_service.submit(db, user, did, 1)
        assert error.value.code == 400 and "业务目标" in str(error.value)
    # 补齐 B 区必填后提交成功
    async with session_factory() as db:
        async with db.begin():
            await demand_service.update_draft(db, user, did, {"expectedRevision": 1, "elements": {"B": ZONE_B}})
    async with session_factory() as db:
        async with db.begin():
            submitted = await demand_service.submit(db, user, did, 2)
            assert submitted.demand_no.startswith("TECH-") and submitted.elements["B"]["stakeholders"] == ["机构业务部", "科技中心"]


# ---- FR-02/D6 大段拆解与原文保真 ----

async def test_long_text_split_keeps_source_text_verbatim(session_factory, user):
    did, sid, rev = await make_draft(session_factory, user)  # content 为空，等待原文回填
    fake = FakeArk({"structured": {"elements": {
                        "A": {"techSubtype": "DATA_RPT"},
                        "C": {"userRole": "机构业务部客户经理", "useScenario": "机构业务部20名客户经理每天晨会前查看各机构持仓汇总"},
                        "D": {"functionDescription": "每天8点前自动按机构汇总持仓并生成报表支持导出", "acceptanceCriteria": "连续7天与核心系统对账误差为0"}}},
                    "elements": [],
                    "typeSignals": {"user": {"confidence": 0.9, "evidence": "客户经理每天晨会前"}}})
    async with session_factory() as db:
        await GuideService(db, user, fake).execute(chat_req(did, sid, rev, message=LONG_TEXT))
    async with session_factory() as db:
        demand = await db.get(Demand, did)
        assert demand.content == LONG_TEXT  # A8 原文一字不变
        assert demand.field_sources["content"] == "user"
        zones = demand.elements
        # 一段混合文本拆出 A/C/D 三区要素（≥3 区）
        assert zones["A"]["techSubtype"] == "DATA_RPT"
        assert zones["C"]["userRole"] == "机构业务部客户经理"
        assert zones["D"]["acceptanceCriteria"] == "连续7天与核心系统对账误差为0"
        assert demand.field_sources["elements.C.userRole"] == "agent"


# ---- FR-08 提炼约束：新增事实过滤 ----

def test_ungrounded_numbers_filtered_grounded_kept():
    output = ModelOutput(structured={"elements": {"C": {"painPoint": "手工汇总50个机构每次近2小时"}}})
    result = process(output, FORM, {}, [], None, {}, "手工汇总很慢，每次都出错")
    assert "painPoint" not in result["structured"].get("elements", {}).get("C", {})
    grounded = process(ModelOutput(structured={"elements": {"C": {"painPoint": "手工汇总20个机构每次近1小时"}}}),
                       FORM, {}, [], None, {}, "手工汇总20个机构数据每次近1小时")
    assert grounded["structured"]["elements"]["C"]["painPoint"] == "手工汇总20个机构每次近1小时"


# ---- BR-T13/FR-10 粒度治理 ----

def test_granularity_too_broad_guides_focus():
    form = {"title": "提升客户回访率到80%", "demandTypeCode": "TECH", "urgency": "NORMAL"}
    result = process(ModelOutput(), form, {}, [], None, {}, "提升客户回访率到80%")
    hint = result["granularityHint"]
    assert hint["level"] == "too_broad" and "聚焦" in hint["hint"]
    assert hint["converge"] == "可验证、可追踪、可独立受理"
    assert result["reply"].startswith(hint["hint"])


def test_granularity_too_narrow_guides_context():
    result = process(ModelOutput(), {"demandTypeCode": "TECH", "urgency": "NORMAL"}, {}, [], None, {}, "在持仓详情页加个字段显示一下基金净值日期")
    hint = result["granularityHint"]
    assert hint["level"] == "too_narrow" and "场景" in hint["hint"]


def test_granularity_converged_no_hint():
    form = {"title": "提升客户回访率到80%", "demandTypeCode": "TECH", "urgency": "NORMAL",
            "elements": {"D": {"functionDescription": "按机构汇总前一交易日持仓并展示"}}}
    assert process(ModelOutput(), form, {}, [], None, {}, "提升客户回访率到80%")["granularityHint"] is None


# ---- FR-06 修改留痕与影响提示 ----

async def test_change_log_two_edits_revision_and_old_values(session_factory, user):
    async with session_factory() as db:
        async with db.begin():
            demand = await demand_service.create_draft(db, user, {"clientRequestId": "p2-log", "title": "原标题", "demandTypeCode": "TECH",
                                                                  "content": "整理需求并记录完整业务信息",
                                                                  "elements": {"C": {"useScenario": "客户经理每天晨会前查看持仓"}}})
            did = demand.id
    async with session_factory() as db:
        async with db.begin():
            await demand_service.update_draft(db, user, did, {"expectedRevision": 0, "title": "新标题"})
    async with session_factory() as db:
        async with db.begin():
            await demand_service.update_draft(db, user, did, {"expectedRevision": 1, "elements": {"C": {"useScenario": "运营专员每周汇总渠道销量"}}})
    async with session_factory() as db:
        demand = await db.get(Demand, did)
        assert demand.revision == 2
        rows = (await db.execute(select(DemandChangeLog).where(DemandChangeLog.demand_id == did).order_by(DemandChangeLog.id))).scalars().all()
        assert [row.field_key for row in rows] == ["title", "elements.C.useScenario"]
        assert rows[0].old_value == "原标题" and rows[0].new_value == "新标题" and rows[0].source == "user"
        assert rows[1].old_value == "客户经理每天晨会前查看持仓" and rows[1].new_value == "运营专员每周汇总渠道销量"


async def test_agent_patch_change_log_marks_agent_source(session_factory, user):
    did, sid, rev = await make_draft(session_factory, user, content="客户经理每天需要查看渠道业务日报")
    fake = FakeArk({"structured": {"elements": {"A": {"techSubtype": "DATA_RPT"}}}, "elements": []})
    async with session_factory() as db:
        await GuideService(db, user, fake).execute(chat_req(did, sid, rev))
    async with session_factory() as db:
        rows = (await db.execute(select(DemandChangeLog).where(DemandChangeLog.demand_id == did))).scalars().all()
        assert [row.field_key for row in rows] == ["elements.A.techSubtype"]
        assert rows[0].old_value is None and rows[0].new_value == "DATA_RPT" and rows[0].source == "agent"


def test_impact_hint_only_on_filled_b_zone_change():
    previous = {"elements": {"B": {"businessGoal": "把客户回访覆盖率从60%提升到80%"}}}
    changed = {"elements": {"B": {"businessGoal": "把客户回访覆盖率从60%提升到90%"}}}
    assert impact_hints(previous, changed) == ["B 区业务要素已变更，C/D 区的用户与功能要素可能需要联动调整，请确认。"]
    assert impact_hints({}, changed) == []  # 首轮填写不算修改
    assert impact_hints(previous, previous) == []
