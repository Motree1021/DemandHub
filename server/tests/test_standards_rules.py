import pytest

from app.standards.loader import get
from app.standards.rules import assess, filter_form, schema_errors


def tech(**ext):
    return {"title": "渠道持仓报表", "demandTypeCode": "TECH", "content": "客户经理每天需要查看完整渠道持仓并导出", "urgency": "NORMAL", "ext": {"techSubtype": "DATA_RPT", "businessScenario": "机构业务部客户经理每天晨会前需要查各机构持仓", "acceptanceCriteria": "8:30前可查且与核心系统对账误差为0", "valueImpact": "20名客户经理每人每天节省40分钟", **ext}}


def test_full_element_collection_and_positive_java_examples():
    result = assess(get("TECH"), tech())
    assert len(result) == 7
    assert all(e.status == "OK" and e.attempts == 0 for e in result)


@pytest.mark.parametrize("key,value,note", [("businessScenario", "方便一下", "含歧义词"), ("businessScenario", "全部内容经过说明之后确实完整但没有关键词", "看不出"), ("acceptanceCriteria", "希望改得好", "缺可量化"), ("valueImpact", "也许很有意义", "缺量化"), ("techSubtype", "UNKNOWN", "选项"), ("businessScenario", "", "未填写")])
def test_negative_java_examples(key, value, note):
    item = next(e for e in assess(get("TECH"), tech(**{key: value})) if e.key == key)
    assert item.status != "OK" and note in item.note


@pytest.mark.parametrize("patch", [{"expectDeliveryAt": "0001-01-01"}, {"expectDeliveryAt": "2026-02-30"}, {"expectDeliveryAt": "2026-9-1"}, {"urgency": "HIGH"}, {"title": "长" * 61}, {"ext": {"quantity": True}}, {"ext": {"quantity": float("nan")}}, {"ext": {"quantity": -1}}, {"ext": {"quantity": "12"}}])
def test_known_bad_values_cannot_enter_draft(patch):
    with pytest.raises(ValueError):
        filter_form(get("MATL"), patch)


def test_unknown_fields_removed_and_subtype_fields_preserved():
    value = filter_form(get("TECH"), {**tech(), "submitterId": 999, "quality": ["OK"], "ext": {"businessScenario": "角色和时机", "devFeatures": "导出", "quantity": 2, "intruder": "x"}})
    assert set(value["ext"]) == {"businessScenario", "devFeatures"}
    assert "submitterId" not in value and "quality" not in value


@pytest.mark.parametrize("field,value,expected", [("expectDeliveryAt", "  ", None), ("urgency", "  ", "NORMAL"), ("ext", {"quantity": "  "}, {"quantity": None})])
def test_optional_blank_values_are_normalized(field, value, expected):
    assert filter_form(get("MATL"), {field: value})[field] == expected


def test_quality_gap_is_distinct_from_required_schema():
    value = tech(acceptanceCriteria="尽快", valueImpact="")
    assert not schema_errors(get("TECH"), value, required=True)
    assert any(e.status != "OK" for e in assess(get("TECH"), value))
    assert schema_errors(get("TECH"), {"title": "标题"}, required=True)
