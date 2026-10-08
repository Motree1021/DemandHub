import pytest

from app.agent.policy import (
    complete_elements,
    inherit_and_count,
    merge_structured,
    pick_follow_up,
    process,
    user_said_skip,
)
from app.agent.schemas import ElementStatus, ModelOutput, parse_model_output
from app.standards.loader import get
from app.standards.rules import assess


def form():
    return {"title": "渠道报表", "demandTypeCode": "TECH", "content": "客户经理每天需要查渠道报表和导出", "urgency": "NORMAL", "elements": {"A": {"techSubtype": "DATA_RPT"}}}


@pytest.mark.parametrize("text,expected", [("跳过", True), ("后续补充。", True), ("请跳过", True), ("我选择后续补充", True), ("不要跳过这个问题", False), ("不是不知道，只是需要确认", False), ("用户说‘跳过’是指旧步骤", False), ("系统需要提供跳过按钮", False), ("不知道是否需要新报表", False)])
def test_skip_requires_explicit_affirmative_sentence(text, expected):
    assert user_said_skip(get("TECH"), text) is expected


@pytest.mark.parametrize("path,old,new", [("title", "手填标题", "模型标题"), ("title", "", "模型标题"), ("demandTypeCode", "TRAIN", "MATL"), ("elements.C.useScenario", "手写场景", "AI场景")])
def test_user_sources_protect_values_including_clears(path, old, new):
    before = {"demandTypeCode": "TECH", "elements": {}}
    patch = {"elements": {}}
    if path.startswith("elements."):
        _, zone, key = path.split(".")
        before["elements"].setdefault(zone, {})[key], patch["elements"].setdefault(zone, {})[key] = old, new
    else:
        before[path], patch[path] = old, new
    result, sources, _ = merge_structured(patch, before, {path: "user"})
    value = result["elements"].get(zone, {}).get(key) if path.startswith("elements.") else result[path]
    assert value == (old or None)
    assert sources[path] == "user"


def test_default_type_can_change_and_ext_is_filtered():
    result, sources, selected = merge_structured({"demandTypeCode": "MATL", "ext": {"quantity": 100, "materialSubtype": "宣传折页"}}, form(), {"demandTypeCode": "default"})
    assert selected.type == "MATL"
    assert "techSubtype" not in result["ext"]
    assert sources["demandTypeCode"] == "agent"
    assert result["ext"]["quantity"] == 100


@pytest.mark.parametrize("value", [3, "UNKNOWN"])
def test_invalid_type_shape_is_controlled(value):
    # 空集合（[]/{}）按新语义视为"未输出"被忽略；类型错误与枚举越界必须受控
    with pytest.raises(ValueError):
        merge_structured({"demandTypeCode": value}, form(), {})


def test_elements_deep_merge_keeps_existing_fields():
    result, _, _ = merge_structured({"elements": {"B": {"businessValue": "影响20人"}}}, form(), {})
    assert result["elements"]["A"]["techSubtype"] == "DATA_RPT" and result["elements"]["B"]["businessValue"] == "影响20人"


def test_overview_survives_merge_filter():
    # ext.overview 四段式需求概述非五区要素：filter_form 丢弃后须恢复，来源 agent
    overview = {"problem": "手工拼表每次40分钟易错｜现有统计方式低效", "goal": "每日8点前自动生成｜自动报表替代手工"}
    result, sources, _ = merge_structured({"ext": {"overview": overview}}, form(), {})
    assert result["ext"]["overview"] == overview and sources["ext.overview"] == "agent"


def test_overview_kept_when_model_omits_it():
    # 本轮未输出 overview 时旧值保留、来源不变
    before = form()
    before["ext"] = {"overview": {"problem": "旧概述｜旧概括"}}
    result, sources, _ = merge_structured({"title": "新标题"}, before, {"ext.overview": "agent"})
    assert result["ext"]["overview"] == {"problem": "旧概述｜旧概括"} and sources["ext.overview"] == "agent"


@pytest.mark.parametrize("overview", ["纯文本", {"problem": 42}, ["数组"]])
def test_overview_invalid_shape_rejected(overview):
    with pytest.raises(ValueError, match="overview"):
        merge_structured({"ext": {"overview": overview}}, form(), {})


def test_top_level_fields_nested_in_zone_a_are_relocated():
    # 模型把 zone=A 而 field_path 在顶层的要素误嵌 elements.A（真实链路已观测到 urgency/expectDeliveryAt），须归位落库
    result, sources, _ = merge_structured({"elements": {"A": {"urgency": "URGENT", "expectDeliveryAt": "2026-10-15"}}}, form(), {})
    assert result["urgency"] == "URGENT" and result["expectDeliveryAt"] == "2026-10-15"
    assert "urgency" not in result["elements"]["A"] and "expectDeliveryAt" not in result["elements"]["A"]
    assert sources["urgency"] == "agent" and sources["expectDeliveryAt"] == "agent"


def test_relocation_respects_user_source():
    # 归位后来源保护照常生效：用户已答的 urgency 不被模型嵌套输出覆盖
    result, sources, _ = merge_structured({"elements": {"A": {"urgency": "CRITICAL"}}}, form(), {"urgency": "user"})
    assert result["urgency"] == "NORMAL" and sources["urgency"] == "user"


def test_invalid_model_value_dropped_not_fatal():
    # 容错：模型写"本周"这类非法日期，丢弃该值而不是整轮对话报错
    result, _, _ = merge_structured({"elements": {"A": {"expectDeliveryAt": "本周"}}}, form(), {})
    assert result["expectDeliveryAt"] is None


def test_process_relocates_nested_urgency_and_moves_on():
    # 全链路：用户说"很紧急"模型输出 elements.A.urgency，归位后不再回头追问紧急程度
    base = form()
    del base["urgency"]
    output = ModelOutput(structured={"elements": {"A": {"urgency": "URGENT"}}}, elements=[])
    result = process(output, base, {}, [], None, {}, "很紧急，本周要上线")
    assert result["structured"]["urgency"] == "URGENT"
    assert next(e for e in result["elements"] if e["key"] == "urgency")["status"] == "OK"
    assert result["askedTarget"] == "businessGoal" and "紧急" not in result["reply"]


def test_missing_collection_cannot_fake_quality_complete():
    result = process(ModelOutput(structured={}, elements=[]), form(), {}, [], None, {}, "报表")
    assert len(result["elements"]) == 27  # 29 要素减去 A4/A5 两个 system 快照
    assert not result["canSubmit"] and not result["ready"]
    assert not result["qualityComplete"] and not result["guidanceComplete"]
    assert result["askedTarget"] == "businessGoal" and "业务目标" in result["reply"]


@pytest.mark.parametrize("key", ["intruder", "otherType"])
def test_unknown_elements_rejected(key):
    with pytest.raises(ValueError):
        complete_elements(get("TECH"), form(), [ElementStatus(key=key, status="OK")])


def test_duplicate_elements_rejected_and_model_state_ignored():
    with pytest.raises(ValueError):
        parse_model_output('{"structured":{},"elements":[{"key":"title","status":"OK"},{"key":"title","status":"OK"}]}')
    result = parse_model_output('{"structured":{},"elements":[{"key":"title","status":"SKIP","attempts":99}],"ready":true}')
    assert result.elements[0].status == "VAGUE" and result.elements[0].attempts == 0


def test_empty_value_cannot_be_model_ok_and_nonempty_cannot_be_missing():
    result = complete_elements(get("TECH"), form(), [ElementStatus(key="useScenario", status="OK"), ElementStatus(key="title", status="MISSING")])
    assert next(e for e in result if e.key == "useScenario").status == "MISSING"
    # 已有有效值时模型声称缺失不降级（规则层是状态唯一权威）
    assert next(e for e in result if e.key == "title").status == "OK"


@pytest.mark.parametrize("claimed", ["MISSING", "VAGUE"])
def test_model_filled_then_claimed_missing_is_not_reasked(claimed):
    # 回归：模型 structured 写入标题却在 elements 报 MISSING/VAGUE，不得反过来追问标题
    base = form()
    del base["title"]
    output = ModelOutput(structured={"title": "海报生成智能体"}, elements=[ElementStatus(key="title", status=claimed)])
    result = process(output, base, {}, [], None, {}, "我要做个海报生成智能体")
    assert result["structured"]["title"] == "海报生成智能体"
    assert next(e for e in result["elements"] if e["key"] == "title").get("status") == "OK"
    assert result["askedTarget"] == "businessGoal"
    assert "请补充需求标题" not in result["reply"]


def test_model_ok_can_upgrade_rule_vague():
    # 规则判 VAGUE（无数字不达 ok_when 之外的软质量）时，模型 OK 票可抬升确认
    base = form()
    base["title"] = "报表"
    result = complete_elements(get("TECH"), base, [ElementStatus(key="title", status="OK", note="语义完整")])
    assert next(e for e in result if e.key == "title").status == "OK"


def test_only_actual_asked_target_counts_and_stop_at_two():
    standard = get("TECH")
    current = assess(standard, form())
    first = inherit_and_count(current, current, "useScenario", False, standard=standard, previous_form=form(), form=form())
    assert next(e for e in first if e.key == "useScenario").attempts == 1
    assert next(e for e in first if e.key == "acceptanceCriteria").attempts == 0
    second = inherit_and_count(first, current, "useScenario", False, standard=standard, previous_form=form(), form=form())
    assert next(e for e in second if e.key == "useScenario").attempts == 2
    assert pick_follow_up(standard, second).key == "businessGoal"


def test_skip_sticky_only_until_field_has_new_value():
    standard = get("TECH")
    current = assess(standard, form())
    skipped = inherit_and_count(current, current, "useFrequency", True, standard=standard, previous_form=form(), form=form())
    assert next(e for e in skipped if e.key == "useFrequency").status == "SKIP"
    unchanged = inherit_and_count(skipped, current, "acceptanceCriteria", False, standard=standard, previous_form=form(), form=form())
    assert next(e for e in unchanged if e.key == "useFrequency").status == "SKIP"
    filled = form()
    filled["elements"].setdefault("C", {})["useFrequency"] = "每天"
    fresh = inherit_and_count(unchanged, assess(standard, filled), "acceptanceCriteria", False, standard=standard, previous_form=form(), form=filled)
    assert next(e for e in fresh if e.key == "useFrequency").status == "OK"


def test_required_values_never_skipped_and_flags_distinct():
    result = process(ModelOutput(), {"demandTypeCode": "MATL"}, {}, [], "title", {}, "跳过")
    assert not result["canSubmit"] and not result["qualityComplete"]
    assert next(e for e in result["elements"] if e["key"] == "title")["status"] == "MISSING"
