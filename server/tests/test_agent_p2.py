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

@pytest.mark.parametrize("business,user_conf,function,expected", [
    (0.9, 0.4, 0.3, True),      # 业务明显占优
    (0.2, 0.9, 0.5, False),     # 低于 0.7 门槛
    (0.1, 0.3, 0.8, False),
    # 2026-10-24 拍板层级倾斜 + 档位对齐（覆盖 2026-10-10 占优口径）：business≥0.7（主句级起点）即业务需求，
    # 不再要求严格占优——三票是证据强度而非互斥概率，判型仅作归类展示，往高层级倾斜
    (0.7, 0.7, 0.8, True),
    (0.8, 0.3, 0.8, True),
    (0.6, 0.4, 0.4, False),     # 从句级顶格 0.6（收益从句封顶）天然不过 0.7 判线——档位对齐的隔离带效应
])
def test_type_signals_three_layers_recognized(business, user_conf, function, expected):
    result = process(signals_output(business, user_conf, function), FORM, {}, [], None, {}, "部门年度考核指标需要系统支撑")
    recognition = result["typeRecognition"]
    assert recognition["business"] == business and recognition["user"] == user_conf and recognition["function"] == function
    assert recognition["evidence"]["business"] == "部门年度考核指标"
    assert business_confirmed(recognition) is expected


def test_type_signals_malformed_is_contract_error():
    with pytest.raises(ValueError):
        parse_model_output('{"structured":{},"elements":[],"typeSignals":{"business":{"confidence":1.5}}}')


# ---- 2026-10-10 判型三档化回归样本（用户拍板的三条真实需求）----

def signals(business, user_conf, function):
    return parse_model_output(json.dumps({"structured": {}, "elements": [], "typeSignals": {
        "business": {"confidence": business, "evidence": ""}, "user": {"confidence": user_conf, "evidence": ""}, "function": {"confidence": function, "evidence": ""}}}, ensure_ascii=False))


@pytest.mark.parametrize("business,user_conf,function,expect_biz", [
    # 需求1 语音生成智能体：用户故事句式（作为X…当…时我可以…），business 0.2 低于门槛 → 用户需求
    (0.2, 0.85, 0.6, False),
    # 需求2 日均规模曲线：business 0.6 为「辅助管理层决策」收益从句顶格分，档位对齐（2026-10-24 二次拍板）后
    # 判线=主句级起点 0.7，从句级信号（封顶 0.6）天然不过线 → 不判业务（口径演变：2026-10-10 占优 False
    # → 2026-10-24 层级 0.5 True → 2026-10-24 档位对齐 0.7 False；存量 0.6 挂账数据显示层自愈，不做迁移）
    (0.6, 0.6, 0.8, False),
    # 需求3 系统改名：纯功能语言 → 功能需求
    (0.1, 0.2, 0.9, False),
])
def test_three_real_demand_samples_classification(business, user_conf, function, expect_biz):
    result = process(signals(business, user_conf, function), FORM, {}, [], None, {}, "样本")
    recognition = result["typeRecognition"]
    assert business_confirmed(recognition) is expect_biz


def test_confirmed_user_and_function_are_final_and_non_business():
    # 改判四选一：confirmed=user/function 定稿不被模型覆盖，且按非业务处理（B 区不激活）
    for confirmed in ("user", "function"):
        prev = {"ext": {"typeRecognition": {"business": 0.9, "user": 0.3, "function": 0.2, "confirmed": confirmed}}}
        result = process(signals(0.9, 0.3, 0.2), prev, {}, [], None, {}, "样本")
        recognition = result["typeRecognition"]
        assert recognition["confirmed"] == confirmed
        assert not business_confirmed(recognition)


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


async def test_business_confirmed_submit_no_longer_requires_zone_b(session_factory, user):
    # 判型与 B 区解耦（2026-10-24 拍板）：B 区要素全部非必填，提交门槛恒为 A/C/D 三区——
    # 判型确认业务的需求缺 B 区也照常提交成功（治理前置改为提报侧 B1 白话一问 + 受理侧 accept 强校验兜底）
    async with session_factory() as db:
        async with db.begin():
            plain = await demand_service.create_draft(db, user, {"clientRequestId": "p2-gate-1", "title": "晨会持仓报表", "demandTypeCode": "TECH",
                                                                 "content": "客户经理每天晨会前查看各机构持仓", "urgency": "NORMAL", "elements": ACD})
            assert (await demand_service.submit(db, user, plain.id, 0)).demand_no.startswith("TECH-")
    # 判型确认为业务：缺 B 区不再 400 拦截，直接提交成功
    async with session_factory() as db:
        async with db.begin():
            demand = await demand_service.create_draft(db, user, {"clientRequestId": "p2-gate-2", "title": "晨会持仓报表", "demandTypeCode": "TECH",
                                                                  "content": "客户经理每天晨会前查看各机构持仓", "urgency": "NORMAL", "elements": ACD})
            did = demand.id
    async with session_factory() as db:
        async with db.begin():
            await demand_service.update_draft(db, user, did, {"expectedRevision": 0, "ext": {"typeRecognition": {"confirmed": "business", "business": 0.9}}})
    async with session_factory() as db:
        async with db.begin():
            assert (await demand_service.submit(db, user, did, 1)).demand_no.startswith("TECH-")


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
    assert impact_hints(previous, changed) == ["你前面说的目标/背景/价值有调整，后面「给谁用、做什么」这些内容可能也要跟着改，请确认一下。"]
    assert impact_hints({}, changed) == []  # 首轮填写不算修改
    assert impact_hints(previous, previous) == []


def test_impact_hint_exempted_when_cd_zone_linked():
    """豁免（2026-10-25 拍板）：B 区变化伴随 C/D 区同步联动（AI 已改完，如改名波及多字段）时不再提示——
    联动已完成再问「请确认一下」属自相矛盾的噪音；只改 B 区、C/D 原封不动才提示。"""
    previous = {"elements": {"B": {"businessBackground": "张征一个人运营自媒体账号"}, "C": {"userRole": "产品经理张征"}}}
    # 改名联动：C 区已同步更新 → 豁免
    linked = {"elements": {"B": {"businessBackground": "张铮一个人运营自媒体账号"}, "C": {"userRole": "产品经理张铮"}}}
    assert impact_hints(previous, linked) == []
    # D 区同步联动同样豁免
    linked_d = {"elements": {"B": {"businessBackground": "张铮一个人运营自媒体账号"}, "D": {"functionDescription": "数字人口播平台"}}}
    assert impact_hints(previous, linked_d) == []
    # 只改 B 区、C/D 原封不动 → 仍提示（真正需要用户确认的场景）
    only_b = {"elements": {"B": {"businessBackground": "为满足监管报送要求改造"}, "C": {"userRole": "产品经理张征"}}}
    assert impact_hints(previous, only_b) != []


# ---- 微需求快速通道（2026-10-11 方案②）：modeSignal 判定与最小集提交 ----

LOGO_TEXT = "把首页顶部的logo换成新设计的蓝色版本，新logo设计稿已经给到了"


def test_mode_signal_malformed_is_contract_error():
    with pytest.raises(ValueError):
        parse_model_output('{"structured":{},"elements":[],"modeSignal":{"level":"quick"}}')


async def test_light_mode_flow_and_minimal_set_submit(session_factory, user):
    """换 logo 微需求全链路：AI 判 light → 只追问紧急度 → 最小集 4 项提交成功，C/D 12 项全空不拦截。"""
    did, sid, rev = await make_draft(session_factory, user, content=LOGO_TEXT, request="p2-light-1")
    # 第一轮：模型判 light 并代拟标题/期望效果；紧急度缺失 → light 首问紧急度，不可提交
    fake = FakeArk({"structured": {"title": "更换首页顶部logo", "elements": {"D": {"acceptanceCriteria": "首页顶部logo显示为新设计的蓝色版本"}}},
                    "elements": [], "modeSignal": {"level": "light", "evidence": "换logo属于微调"}})
    async with session_factory() as db:
        first = await GuideService(db, user, fake).execute(chat_req(did, sid, rev, request_id="p2-light-chat1", message=LOGO_TEXT))
    assert first.mode["level"] == "light" and first.asked_target == "urgency" and not first.can_submit
    assert "紧急" in first.reply
    async with session_factory() as db:
        demand = await db.get(Demand, did)
        assert demand.ext["mode"]["level"] == "light"
        assert demand.field_sources["ext.mode"] == "agent"
        rev2 = demand.revision
    # 第二轮：用户答紧急度 → 最小集齐，可提交
    fake2 = FakeArk({"structured": {"urgency": "NORMAL"}, "elements": [], "modeSignal": {"level": "light", "evidence": "换logo属于微调"}})
    async with session_factory() as db:
        second = await GuideService(db, user, fake2).execute(chat_req(did, sid, rev2, request_id="p2-light-chat2", message="普通就行，不着急"))
    assert second.can_submit and second.asked_target is None
    assert "可以提交" in second.reply
    # 提交：C/D 其余 11 项全空仍放行；质量快照按 light 口径落库（D8 无数字不降级）
    async with session_factory() as db:
        async with db.begin():
            submitted = await demand_service.submit(db, user, did, second.revision)
    assert submitted.demand_no.startswith("TECH-")
    assert submitted.ext["mode"]["level"] == "light"
    quality = {item["key"]: item["status"] for item in submitted.quality}
    assert quality["acceptanceCriteria"] == "OK" and quality["userRole"] == "MISSING"


async def test_standard_draft_minimal_set_still_blocked(session_factory, user):
    # 同样的最小集数据、未判 light（mode 缺省 standard）：C/D 12 项门槛照拦
    async with session_factory() as db:
        async with db.begin():
            demand = await demand_service.create_draft(db, user, {"clientRequestId": "p2-light-std", "title": "更换首页顶部logo",
                                                                  "demandTypeCode": "TECH", "content": LOGO_TEXT, "urgency": "NORMAL",
                                                                  "elements": {"D": {"acceptanceCriteria": "首页顶部logo显示为新设计的蓝色版本"}}})
            did = demand.id
    async with session_factory() as db:
        with pytest.raises(Exception) as error:
            async with db.begin():
                await demand_service.submit(db, user, did, 0)
        assert error.value.code == 400 and "未填写" in str(error.value)


async def test_update_draft_cannot_override_agent_mode(session_factory, user):
    # ext.mode 只归 AI 判定链路：H5 整表单回传携带的 mode 被剔除，不覆盖 AI 已判定的 light；判型仍可由用户回传
    did, sid, rev = await make_draft(session_factory, user, content=LOGO_TEXT, request="p2-light-keep")
    fake = FakeArk({"structured": {}, "elements": [], "modeSignal": {"level": "light", "evidence": "换logo"}})
    async with session_factory() as db:
        await GuideService(db, user, fake).execute(chat_req(did, sid, rev, request_id="p2-light-keep-chat", message=LOGO_TEXT))
    async with session_factory() as db:
        async with db.begin():
            await demand_service.update_draft(db, user, did, {"expectedRevision": 1, "ext": {"mode": {"level": "standard", "evidence": "伪造回退"},
                                                                                             "typeRecognition": {"confirmed": "function"}}})
    async with session_factory() as db:
        demand = await db.get(Demand, did)
        assert demand.ext["mode"]["level"] == "light"
        assert demand.ext["typeRecognition"]["confirmed"] == "function"
