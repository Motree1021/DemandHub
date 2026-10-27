"""P2 验收：判型确认/改判（FR-01/FR-03）、大段拆解原文保真（FR-02/D6）、FR-08 新增事实过滤、BR-T13 粒度治理、FR-06 修改留痕。"""
import pytest
from sqlalchemy import select

from app.agent.guide import GuideService
from app.agent.policy import process
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


# ---- FR-01/FR-03 判型（2026-10-26 拍板派生制：层级由表单素材位置派生，模型不再打分）----

@pytest.mark.parametrize("structured,text,expected_level,expected_basis", [
    # B1（业务目标）附原话证据验真通过（出处升 user_evidence）→ 业务需求
    ({"elements": {"B": {"businessGoal": {"value": "达成部门年度考核指标", "evidence": "达成部门年度考核指标"}}}}, "要达成部门年度考核指标", "business", "businessGoal"),
    # B3（业务价值）附原话证据验真通过（出处升 user_evidence）→ 业务需求
    ({"elements": {"B": {"businessValue": {"value": "其他银行渠道可复用", "evidence": "其他银行渠道可复用"}}}}, "其他银行渠道可复用", "business", "businessValue"),
    # C 区三件套（角色/场景/痛点）齐全 → 用户需求
    ({"elements": {"C": {"userRole": "客户经理", "useScenario": "客户经理每天晨会前查看各机构持仓",
                         "painPoint": "手工汇总持仓每次近一小时还容易出错"}}}, "补充", "user", "useScenario"),
    # 只有功能素材 → 功能需求
    ({"elements": {"D": {"functionDescription": "按机构汇总前一交易日持仓并展示"}}}, "补充", "function", "functionDescription"),
])
def test_derive_recognition_three_layers(structured, text, expected_level, expected_basis):
    result = process(ModelOutput(structured=structured, elements=[]), FORM, {}, [], None, {}, text)
    recognition = result["typeRecognition"]
    assert recognition["level"] == expected_level and recognition["basis"]["field"] == expected_basis
    assert business_confirmed(recognition) is (expected_level == "business")


def test_derive_recognition_empty_form_and_agent_drafted_b3_no_recognition():
    # 空表单不出判型（H5 归类标签不渲染）；AI 代拟的 B3（未附原话证据、出处 agent）不参与派生——
    # 防「因为判业务所以代拟 B3、因为 B3 有值所以判业务」循环自证
    empty = {"demandTypeCode": "TECH"}
    result = process(ModelOutput(structured={}, elements=[]), empty, {}, [], None, {}, "继续")
    assert result["typeRecognition"] is None
    drafted = process(ModelOutput(structured={"elements": {"B": {"businessValue": "释放部门人力"}}}, elements=[]),
                      empty, {}, [], None, {}, "继续")
    assert drafted["typeRecognition"] is None
    assert drafted["fieldSources"]["elements.B.businessValue"] == "agent"


def test_type_signals_malformed_is_contract_error():
    # 解析容错保留：模型仍可能输出旧 typeSignals 字段，格式畸形即契约错误（服务端不再消费该字段）
    with pytest.raises(ValueError):
        parse_model_output('{"structured":{},"elements":[],"typeSignals":{"business":{"confidence":1.5}}}')


# ---- 2026-10-10 判型三档化回归样本（用户拍板的三条真实需求，2026-10-26 派生制改素材构造、结论不变）----

@pytest.mark.parametrize("structured,expect_level", [
    # 需求1 语音生成智能体：用户故事句式（作为X…当…时我可以…）→ C 区三件套齐 → 用户需求
    ({"elements": {"C": {"userRole": "客服坐席", "useScenario": "客服坐席接到客户咨询电话时需要快速生成应答话术",
                         "painPoint": "手工编写话术响应慢且口径不统一"}}}, "user"),
    # 需求2 日均规模曲线：只抽到功能描述（「辅助管理层决策」类收益从句不再升格判型）→ 功能需求
    ({"elements": {"D": {"functionDescription": "展示日均规模曲线并支持导出"}}}, "function"),
    # 需求3 系统改名：纯功能语言 → 功能需求
    ({"elements": {"D": {"functionDescription": "系统名称由旧名改为新名"}}}, "function"),
])
def test_three_real_demand_samples_classification(structured, expect_level):
    result = process(ModelOutput(structured=structured, elements=[]), FORM, {}, [], None, {}, "样本")
    recognition = result["typeRecognition"]
    assert recognition["level"] == expect_level
    assert business_confirmed(recognition) is (expect_level == "business")


def test_confirmed_user_and_function_are_final_and_non_business():
    # 改判四选一：confirmed=user/function 定稿不被派生覆盖，且按非业务处理（B 区不激活）——
    # 即便本轮 B1 附证据验真落库派生出业务层级，人工定稿仍最高优先
    for confirmed in ("user", "function"):
        prev = {"ext": {"typeRecognition": {"confirmed": confirmed}}}
        output = ModelOutput(structured={"elements": {"B": {"businessGoal": {"value": "达成部门年度考核指标", "evidence": "达成部门年度考核指标"}}}}, elements=[])
        result = process(output, prev, {}, [], None, {}, "达成部门年度考核指标")
        recognition = result["typeRecognition"]
        assert recognition["confirmed"] == confirmed
        assert not business_confirmed(recognition)


async def test_user_override_type_clears_recognition_and_marks_user(session_factory, user):
    # 首轮对话：无 B1/B3 用户证据、C 三件套未齐 → 派生功能需求（AI 判型来源 agent）
    did, sid, rev = await make_draft(session_factory, user, content="机构业务部为达成部门年度考核指标，需要把晨会持仓整理从手工40分钟压缩到自动出具")
    fake = FakeArk({"structured": {"elements": {"A": {"techSubtype": "DATA_RPT"}}}, "elements": []})
    async with session_factory() as db:
        result = await GuideService(db, user, fake).execute(chat_req(did, sid, rev))
    assert result.type_recognition["level"] == "function" and not business_confirmed(result.type_recognition)
    async with session_factory() as db:
        demand = await db.get(Demand, did)
        assert demand.ext["typeRecognition"]["level"] == "function"
        assert demand.field_sources["ext.typeRecognition"] == "agent"
        rev = demand.revision
    async with session_factory() as db:
        async with db.begin():
            demand = await demand_service.update_draft(db, user, did, {"expectedRevision": rev, "ext": {"typeRecognition": {"confirmed": "none"}}})
            # 改判只更新 confirmed，派生层级与依据不丢；来源落 user
            assert demand.ext["typeRecognition"]["level"] == "function"
            assert demand.ext["typeRecognition"]["confirmed"] == "none"
            assert not business_confirmed(demand.ext["typeRecognition"])
            assert demand.field_sources["ext.typeRecognition"] == "user"
        logs = (await db.execute(select(DemandChangeLog).where(DemandChangeLog.demand_id == did, DemandChangeLog.field_key == "ext.typeRecognition"))).scalars().all()
        assert logs and logs[-1].new_value["confirmed"] == "none"


def test_channel_reuse_value_lands_b3_not_d9_and_derives_business():
    # 张征案例回归（2026-10-27 拍板 evidence 机制）：「其他银行渠道可复用，添加我司渠道赋能新能力」
    # 是受益方为组织的表述 → 归 B3 并附原话证据（验真通过、出处升 user_evidence）→ 派生业务需求、B 区必填当场生效；
    # 一事实一槽位：不占 D9 候选方案槽位
    text = "希望支持企业微信扫码登录，其他银行渠道可复用，添加我司渠道赋能新能力"
    output = ModelOutput(structured={"elements": {
        "B": {"businessValue": {"value": "其他银行渠道可复用，添加我司渠道赋能新能力", "evidence": "其他银行渠道可复用，添加我司渠道赋能新能力"}},
        "D": {"functionDescription": "支持企业微信扫码登录"}}}, elements=[])
    base = {"title": "企业微信扫码登录", "demandTypeCode": "TECH", "content": text, "urgency": "NORMAL",
            "elements": {"A": {"techSubtype": "SYS_INT"},
                         "C": {"userRole": "客户经理", "userGoal": "快速登录系统开展日常展业工作",
                               "useScenario": "客户经理登录展业系统时扫码进入",
                               "painPoint": "账号密码登录经常忘记且输入繁琐"},
                         "D": {"functionDescription": "支持企业微信扫码登录",
                               "inputOutput": "输入企业微信扫码授权，输出登录态",
                               "acceptanceCriteria": "扫码后3秒内完成登录"}}}
    result = process(output, base, {}, [], None, base, text)
    merged = result["structured"]["elements"]
    assert merged["B"]["businessValue"] == "其他银行渠道可复用，添加我司渠道赋能新能力"
    assert "proposedSolution" not in merged.get("D", {})
    assert result["fieldSources"]["elements.B.businessValue"] == "user_evidence"
    recognition = result["typeRecognition"]
    assert recognition["level"] == "business" and business_confirmed(recognition)
    assert recognition["basis"]["field"] == "businessValue"
    # B 区必填生效：B1 未答 → 不可提交，追问沉底接上 B1
    assert result["canSubmit"] is False and result["askedTarget"] == "businessGoal"


async def test_business_confirmed_submit_zone_b_unified_gate(session_factory, user):
    # B 区统一必填（2026-10-26 拍板，撤销同日「路径分流」）：判型归业务需求（confirmed=business，
    # 含残留 b1Backfill 标记的存量草稿）一律 B1~B4 动态必填，缺了提交拦截；补齐后放行
    from app.core.errors import BizError, ErrorCode

    async def create_acd_draft(request_id):
        async with session_factory() as db:
            async with db.begin():
                draft = await demand_service.create_draft(db, user, {"clientRequestId": request_id, "title": "晨会持仓报表", "demandTypeCode": "TECH",
                                                                     "content": "客户经理每天晨会前查看各机构持仓", "urgency": "NORMAL", "elements": ACD})
                return draft.id

    # 无判型：B 区不激活，缺 B 区照常提交成功
    plain = await create_acd_draft("p2-gate-1")
    async with session_factory() as db:
        async with db.begin():
            assert (await demand_service.submit(db, user, plain, 0)).demand_no.startswith("TECH-")

    # confirmed=business（无标记）→ 缺 B 区提交拦截（B1 未填写）
    native = await create_acd_draft("p2-gate-2")
    async with session_factory() as db:
        async with db.begin():
            await demand_service.update_draft(db, user, native, {"expectedRevision": 0, "ext": {"typeRecognition": {"confirmed": "business", "business": 0.9}}})
    async with session_factory() as db:
        async with db.begin():
            with pytest.raises(BizError) as error:
                await demand_service.submit(db, user, native, 1)
            assert error.value.code == ErrorCode.PARAM_INVALID.code and "未填写" in str(error.value)

    # 存量草稿残留 b1Backfill 标记：概念作废无读取方，confirmed=business 同样拦截
    legacy = await create_acd_draft("p2-gate-3")
    async with session_factory() as db:
        async with db.begin():
            await demand_service.update_draft(db, user, legacy, {"expectedRevision": 0, "ext": {"typeRecognition": {"confirmed": "business", "business": 0.9, "b1Backfill": True}}})
    async with session_factory() as db:
        async with db.begin():
            with pytest.raises(BizError) as error:
                await demand_service.submit(db, user, legacy, 1)
            assert error.value.code == ErrorCode.PARAM_INVALID.code and "未填写" in str(error.value)

    # 补齐 B 区四要素后提交成功
    async with session_factory() as db:
        async with db.begin():
            await demand_service.update_draft(db, user, native, {"expectedRevision": 1, "elements": {"B": {
                "businessGoal": "达成部门年度考核指标", "businessBackground": "部门年度考核要求晨会材料自动化出具",
                "businessValue": "20名客户经理每人每天节省40分钟", "stakeholders": ["机构业务部负责人"]}}})
    async with session_factory() as db:
        async with db.begin():
            assert (await demand_service.submit(db, user, native, 2)).demand_no.startswith("TECH-")


# ---- FR-02/D6 大段拆解与原文保真 ----

async def test_long_text_split_keeps_source_text_verbatim(session_factory, user):
    did, sid, rev = await make_draft(session_factory, user)  # content 为空，等待原文回填
    fake = FakeArk({"structured": {"elements": {
                        "A": {"techSubtype": "DATA_RPT"},
                        "C": {"userRole": "机构业务部客户经理", "useScenario": "机构业务部20名客户经理每天晨会前查看各机构持仓汇总"},
                        "D": {"functionDescription": "每天8点前自动按机构汇总持仓并生成报表支持导出", "acceptanceCriteria": "连续7天与核心系统对账误差为0"}}},
                    "elements": []})
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
