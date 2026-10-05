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
    return {"title": "渠道报表", "demandTypeCode": "TECH", "content": "客户经理每天需要查渠道报表和导出", "urgency": "NORMAL", "ext": {"techSubtype": "DATA_RPT"}}


@pytest.mark.parametrize("text,expected", [("跳过", True), ("后续补充。", True), ("请跳过", True), ("我选择后续补充", True), ("不要跳过这个问题", False), ("不是不知道，只是需要确认", False), ("用户说‘跳过’是指旧步骤", False), ("系统需要提供跳过按钮", False), ("不知道是否需要新报表", False)])
def test_skip_requires_explicit_affirmative_sentence(text, expected):
    assert user_said_skip(get("TECH"), text) is expected


@pytest.mark.parametrize("path,old,new", [("title", "手填标题", "模型标题"), ("title", "", "模型标题"), ("demandTypeCode", "TRAIN", "MATL"), ("ext.businessScenario", "手写场景", "AI场景")])
def test_user_sources_protect_values_including_clears(path, old, new):
    before = {"demandTypeCode": "TECH", "ext": {}}
    patch = {"ext": {}}
    if path.startswith("ext."):
        before["ext"][path[4:]], patch["ext"][path[4:]] = old, new
    else:
        before[path], patch[path] = old, new
    result, sources, _ = merge_structured(patch, before, {path: "user"})
    assert (result["ext"][path[4:]] if path.startswith("ext.") else result[path]) == (old or None)
    assert sources[path] == "user"


def test_default_type_can_change_and_ext_is_filtered():
    result, sources, selected = merge_structured({"demandTypeCode": "MATL", "ext": {"quantity": 100, "materialSubtype": "宣传折页"}}, form(), {"demandTypeCode": "default"})
    assert selected.type == "MATL"
    assert "techSubtype" not in result["ext"]
    assert sources["demandTypeCode"] == "agent"
    assert result["ext"]["quantity"] == 100


@pytest.mark.parametrize("value", [[], {}, 3, "UNKNOWN"])
def test_invalid_type_shape_is_controlled(value):
    with pytest.raises(ValueError):
        merge_structured({"demandTypeCode": value}, form(), {})


def test_ext_deep_merge_keeps_existing_fields():
    result, _, _ = merge_structured({"ext": {"valueImpact": "影响20人"}}, form(), {})
    assert result["ext"]["techSubtype"] == "DATA_RPT" and result["ext"]["valueImpact"] == "影响20人"


def test_missing_collection_cannot_fake_quality_complete():
    result = process(ModelOutput(structured={}, elements=[]), form(), {}, [], None, {}, "报表")
    assert len(result["elements"]) == 7
    assert result["canSubmit"] and result["ready"]
    assert not result["qualityComplete"] and not result["guidanceComplete"]
    assert result["askedTarget"] == "businessScenario" and "使用场景" in result["reply"]


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
    result = complete_elements(get("TECH"), form(), [ElementStatus(key="businessScenario", status="OK"), ElementStatus(key="title", status="MISSING")])
    assert next(e for e in result if e.key == "businessScenario").status == "MISSING"
    assert next(e for e in result if e.key == "title").status == "VAGUE"


def test_only_actual_asked_target_counts_and_stop_at_two():
    standard = get("TECH")
    current = assess(standard, form())
    first = inherit_and_count(current, current, "businessScenario", False, standard=standard, previous_form=form(), form=form())
    assert next(e for e in first if e.key == "businessScenario").attempts == 1
    assert next(e for e in first if e.key == "acceptanceCriteria").attempts == 0
    second = inherit_and_count(first, current, "businessScenario", False, standard=standard, previous_form=form(), form=form())
    assert pick_follow_up(standard, second).key == "acceptanceCriteria"
    third = inherit_and_count(second, current, "acceptanceCriteria", False, standard=standard, previous_form=form(), form=form())
    assert next(e for e in third if e.key == "businessScenario").attempts == 2


def test_skip_sticky_only_until_field_has_new_value():
    standard = get("TECH")
    current = assess(standard, form())
    skipped = inherit_and_count(current, current, "businessScenario", True, standard=standard, previous_form=form(), form=form())
    assert next(e for e in skipped if e.key == "businessScenario").status == "SKIP"
    unchanged = inherit_and_count(skipped, current, "acceptanceCriteria", False, standard=standard, previous_form=form(), form=form())
    assert next(e for e in unchanged if e.key == "businessScenario").status == "SKIP"
    filled = form()
    filled["ext"]["businessScenario"] = "机构业务部客户经理每天晨会前需要查询渠道持仓"
    fresh = inherit_and_count(unchanged, assess(standard, filled), "acceptanceCriteria", False, standard=standard, previous_form=form(), form=filled)
    assert next(e for e in fresh if e.key == "businessScenario").status == "OK"


def test_required_values_never_skipped_and_flags_distinct():
    result = process(ModelOutput(), {"demandTypeCode": "MATL"}, {}, [], "title", {}, "跳过")
    assert not result["canSubmit"] and not result["qualityComplete"]
    assert next(e for e in result["elements"] if e["key"] == "title")["status"] == "MISSING"
