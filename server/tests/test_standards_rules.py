from datetime import date

import pytest

from app.standards.loader import get
from app.standards.rules import (
    LIGHT_REQUIRED_KEYS,
    assess,
    demand_mode,
    field_error,
    filter_form,
    schema_errors,
)


def tech(**overrides):
    """五区全要素 OK 的基准表单；用 区__要素=值 覆盖 elements 内字段，其余键覆盖顶层。"""
    form = {"title": "渠道持仓报表", "demandTypeCode": "TECH",
            "content": "客户经理每天需要查看完整渠道持仓并导出", "urgency": "NORMAL",
            "expectDeliveryAt": "2099-12-31",
            "elements": {
                "A": {"techSubtype": "DATA_RPT"},
                "B": {"businessGoal": "把机构客户持仓查询覆盖率从60%提升到95%",
                      "businessBackground": "目前客户经理依赖人工向机构部索取持仓汇总，时效差",
                      "businessValue": "20名客户经理每人每天节省40分钟",
                      "stakeholders": ["机构业务部", "科技中心"],
                      "businessRules": "客户敏感信息需脱敏后展示",
                      "upstreamGoal": "机构客户服务质量提升年度目标",
                      "relatedDemands": ["TECH-20261001-001"]},
                "C": {"userRole": "机构业务部客户经理",
                      "userGoal": "每天晨会前快速查看各机构持仓汇总",
                      "useScenario": "机构业务部客户经理每天晨会前需要查各机构持仓",
                      "useFrequency": "每天",
                      "painPoint": "手工向机构部索取持仓并汇总每人每天约40分钟",
                      "userCount": 20},
                "D": {"functionDescription": "按机构汇总前一交易日持仓并支持导出",
                      "inputOutput": "输入交易流水，输出按机构汇总的持仓报表",
                      "businessRuleMap": "持仓数据展示前完成脱敏",
                      "dataRequirements": "代销系统交易库，按机构汇总，每交易日8:00前刷新",
                      "interfaceRequirements": "与核心系统单向同步，延迟不超过5分钟",
                      "nfrRequirements": ["查询3秒内返回", "客户敏感信息脱敏"],
                      "exceptionHandling": "同步失败自动重试并通知运维",
                      "acceptanceCriteria": "8:30前可查且与核心系统对账误差为0",
                      "proposedSolution": "提报人设想：优先基于现有报表平台扩展，无需新建系统（供评估，非定案）"}}}
    for key, value in overrides.items():
        if "__" in key:
            zone, element = key.split("__", 1)
            form["elements"][zone][element] = value
        else:
            form[key] = value
    return form


def test_full_element_collection_and_positive_java_examples():
    result = assess(get("TECH"), tech())
    assert len(result) == 26  # 30 要素减 A4/A5 system 快照，再减 D9 建议方案与 A3 子类（2026-10-15 起均不参与质量评估）
    assert all(e.status == "OK" and e.attempts == 0 for e in result)


def test_proposed_solution_not_assessed():
    """D9 建议方案有值也不进 quality（assessed: false），照常保存展示但不参与计数。"""
    form = tech()
    assert form["elements"]["D"]["proposedSolution"]  # 夹具自带 D9 值
    result = assess(get("TECH"), form)
    assert all(e.key != "proposedSolution" for e in result)


def test_tech_subtype_not_assessed_or_blocking():
    """A3 子类改 AI 自动归类（2026-10-15 拍板）：assessed:false 不进质量计数；选填空值不拦提交。"""
    form = tech(**{"A__techSubtype": None})
    result = assess(get("TECH"), form)
    assert all(e.key != "techSubtype" for e in result)
    assert schema_errors(get("TECH"), form, required=True, active_zones={"A", "C", "D"}) == []


@pytest.mark.parametrize("zone,key,value,note", [("C", "useScenario", "方便一下", "含歧义词"), ("C", "useScenario", "全部内容经过说明之后确实完整但没有关键词", "看不出"), ("D", "acceptanceCriteria", "希望改得好", "缺可检验"), ("B", "businessValue", "也许很有意义", "缺量化"), ("C", "useScenario", "", "未填写")])
def test_negative_java_examples(zone, key, value, note):
    item = next(e for e in assess(get("TECH"), tech(**{f"{zone}__{key}": value})) if e.key == key)
    assert item.status != "OK" and note in item.note


@pytest.mark.parametrize("value", [
    "零售有效规模管理系统，新增日均规模曲线，方便零售总部专员查看日均线的变化走势",  # 含歧义词「方便」
    "希望尽快上线，体验会好很多",  # 含多个歧义词
    "太短",  # 首句较短：原话非空即合格，长度不充分由场景/痛点等要素补全
])
def test_raw_content_any_nonblank_is_ok(value):
    # A8 原始提报文本是系统原样保留的用户原话底稿：非空即 OK，不做歧义词/长度软判质，
    # 永不成为追问目标（避免"请补充原始提报文本"这类无法回答、且补充也改不了原话的死循环）
    item = next(e for e in assess(get("TECH"), tech(content=value)) if e.key == "content")
    assert item.status == "OK"


def test_raw_content_blank_is_missing():
    # 原话为空仍判 MISSING，由提交必填门槛拦截
    item = next(e for e in assess(get("TECH"), tech(content="   ")) if e.key == "content")
    assert item.status == "MISSING"


@pytest.mark.parametrize("patch", [{"expectDeliveryAt": "0001-01-01"}, {"expectDeliveryAt": "2026-02-30"}, {"expectDeliveryAt": "2026-9-1"}, {"urgency": "HIGH"}, {"title": "长" * 61}, {"ext": {"quantity": True}}, {"ext": {"quantity": float("nan")}}, {"ext": {"quantity": -1}}, {"ext": {"quantity": "12"}}])
def test_known_bad_values_cannot_enter_draft(patch):
    with pytest.raises(ValueError):
        filter_form(get("MATL"), patch)


def test_unknown_fields_removed_and_subtype_fields_preserved():
    value = filter_form(get("TECH"), {**tech(), "submitterId": 999, "quality": ["OK"],
                                      "elements": {**tech()["elements"], "C": {"useScenario": "机构业务部客户经理每天晨会前查持仓", "intruder": "x"}, "Z": {"foo": 1}}})
    assert set(value["elements"]["C"]) == {"useScenario"}
    assert "Z" not in value["elements"]
    assert "submitterId" not in value and "quality" not in value


@pytest.mark.parametrize("field,value,expected", [("expectDeliveryAt", "  ", None), ("urgency", "  ", "NORMAL"), ("ext", {"quantity": "  "}, {"quantity": None})])
def test_optional_blank_values_are_normalized(field, value, expected):
    assert filter_form(get("MATL"), {field: value})[field] == expected


# ---- 期望交付时间语义：格式合法但早于今天也必须拦截（2026-10-12 真实事故：
# 用户说「10/30」，模型无日期锚点错补成 2015-10-30）。断言用显式 today 保证不随运行日期漂移 ----

def _delivery_field(standard):
    return next(f for f in standard.fields if f.key == "expectDeliveryAt")


def test_past_delivery_date_rejected_even_if_format_valid():
    ref = date(2026, 10, 12)
    assert field_error(_delivery_field(get("TECH")), "2015-10-30", today=ref) == "期望交付时间不能早于今天"
    # 今天当天合法，未来合法
    assert field_error(_delivery_field(get("TECH")), "2026-10-12", today=ref) is None
    assert field_error(_delivery_field(get("TECH")), "2026-10-30", today=ref) is None


def test_strict_api_rejects_past_delivery_date():
    # 提交/保存（validate=True）：过去日期直接拒绝
    with pytest.raises(ValueError, match="不能早于今天"):
        filter_form(get("TECH"), {"expectDeliveryAt": "2015-10-30"}, today=date(2026, 10, 12))


def test_agent_fault_tolerant_drops_past_delivery_date():
    # agent 链路（validate=False）：模型错补的过去日期静默丢弃，不杀整轮对话，交由追问补问
    result = filter_form(get("TECH"), {"expectDeliveryAt": "2015-10-30"}, validate=False, today=date(2026, 10, 12))
    assert result["expectDeliveryAt"] is None


def test_past_delivery_date_marked_vague_for_followup():
    # 判质把过去日期标 VAGUE，形成追问目标
    value = tech(expectDeliveryAt="2015-10-30")
    item = next(e for e in assess(get("TECH"), value) if e.key == "expectDeliveryAt")
    assert item.status == "VAGUE" and "不能早于今天" in item.note


def test_quality_gap_is_distinct_from_required_schema():
    value = tech(D__acceptanceCriteria="尽快", D__dataRequirements="")
    assert not schema_errors(get("TECH"), value, required=True)
    assert any(e.status != "OK" for e in assess(get("TECH"), value))
    assert schema_errors(get("TECH"), {"title": "标题"}, required=True)


# ---- 微需求快速通道（2026-10-11 方案②）：light 最小集门槛与 D8 放宽 ----


def light_form(**overrides):
    """light 最小集齐全（A8原话+A1标题+A6紧急度+D8期望效果）、C/D 其余 11 项全空——换 logo 类微需求真实形态。"""
    value = {"title": "更换首页顶部logo", "demandTypeCode": "TECH",
             "content": "把首页顶部的logo换成新设计的蓝色版本", "urgency": "NORMAL",
             "elements": {"D": {"acceptanceCriteria": "首页顶部logo显示为新设计的蓝色版本，看着更正式"}}}
    value.update(overrides)
    return value


def test_light_minimal_set_passes_gate_but_standard_still_blocks():
    # 同一份表单：light 只拦最小集故放行；standard 仍拦 C/D 大片缺口
    assert schema_errors(get("TECH"), light_form(), required=True, required_keys=LIGHT_REQUIRED_KEYS) == []
    errors = schema_errors(get("TECH"), light_form(), required=True, active_zones={"A", "C", "D"})
    assert "目标用户角色未填写" in errors and "验收标准未填写" not in errors


def test_light_gate_still_blocks_missing_minimal_fields():
    # 最小集缺 D8 期望效果照样拦；techSubtype 等 A 区其余项不在 light 门槛内
    errors = schema_errors(get("TECH"), light_form(elements={}), required=True, required_keys=LIGHT_REQUIRED_KEYS)
    assert errors == ["验收标准未填写"]


def test_d8_quantization_relaxed_only_in_light_mode():
    value = tech(D__acceptanceCriteria="做完后首页顶部logo看着更正式")
    assert next(e for e in assess(get("TECH"), value) if e.key == "acceptanceCriteria").status == "VAGUE"
    assert next(e for e in assess(get("TECH"), value, light=True) if e.key == "acceptanceCriteria").status == "OK"
    # 放宽只针对 D8：其余要素的歧义词等软质量在 light 下照判
    mixed = tech(D__functionDescription="尽快优化一下")
    assert next(e for e in assess(get("TECH"), mixed, light=True) if e.key == "functionDescription").status == "VAGUE"


# ---- 2026-10-12 口径一A/二A：歧义词长句豁免 + 验收承认行为结果 ----

def test_vague_word_long_sentence_exempted():
    # 「体验/方便」在长句里多为正常结果陈述（「…导致客户经理阅读体验较差」），不得子串命中误伤
    value = tech(C__painPoint="客户经理通过企微或微信直接打开会提示非法网页无法直接打开必须复制网址到手机浏览器才能打开导致阅读体验较差")
    assert next(e for e in assess(get("TECH"), value) if e.key == "painPoint").status == "OK"


def test_vague_word_short_sentence_still_flagged():
    # 短句且以模糊词为主体（「方便一下」「尽快好用」）仍判模糊追问
    assert next(e for e in assess(get("TECH"), tech(C__useScenario="方便一下")) if e.key == "useScenario").status == "VAGUE"
    assert next(e for e in assess(get("TECH"), tech(C__painPoint="尽快好用")) if e.key == "painPoint").status == "VAGUE"


@pytest.mark.parametrize("scenario", [
    # 2026-10-26 修订：区间频率（每2~3天≠「每天」子串）与人名角色句式（作为…运营者）不再误判 VAGUE
    "张征作为自媒体账号交行小张的运营者，每2~3天制作并发布一期口播短视频",
    "运营专员每两周汇总渠道销量报表数据",
    "客户经理隔天同步一次渠道数据情况",
    "柜员两天一次核对库存并登记台账",
    # 事件触发与按需声明（2026-10-26 补充）：收到任务/通知、领导交办、按需使用均为合法时机描述
    "客户经理收到审批任务后3个工作日内处理完毕",
    "运营专员接到监管报送通知后整理当季度数据",
    "客户经理按需使用该平台制作口播短视频并发布",
])
def test_use_scenario_frequency_regex(scenario):
    assert next(e for e in assess(get("TECH"), tech(C__useScenario=scenario)) if e.key == "useScenario").status == "OK"


@pytest.mark.parametrize("criteria", [
    "客户经理在企微或微信中点击产品周报链接可直接打开，不再提示非法网页，无需复制到浏览器",
    "链接修复后可正常打开",
    "弹窗不再出现",
    "页面显示恢复正常",
])
def test_behavioral_acceptance_criteria_is_ok(criteria):
    # 行为结果类验收与数字指标地位平等：无数字但含可逐条核对的行为结果即合格
    item = next(e for e in assess(get("TECH"), tech(D__acceptanceCriteria=criteria)) if e.key == "acceptanceCriteria")
    assert item.status == "OK", item.note


def test_empty_talk_acceptance_criteria_still_vague():
    # 空话（无数字也无行为结果）仍判不可检验
    item = next(e for e in assess(get("TECH"), tech(D__acceptanceCriteria="希望改得好一些")) if e.key == "acceptanceCriteria")
    assert item.status == "VAGUE"


def test_demand_mode_reads_ext_with_standard_fallback():
    assert demand_mode({}) == "standard"  # 存量草稿无 mode：按常规
    assert demand_mode({"ext": {"mode": {"level": "light"}}}) == "light"
    assert demand_mode({"ext": {"mode": {"level": "standard"}}}) == "standard"
    assert demand_mode({"ext": {"mode": "light"}}) == "standard"  # 畸形值兜底常规，不得误入轻量口径
