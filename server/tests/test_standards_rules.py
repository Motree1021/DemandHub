import pytest

from app.standards.loader import get
from app.standards.rules import assess, filter_form, schema_errors


def tech(**overrides):
    """五区全要素 OK 的基准表单；用 区__要素=值 覆盖 elements 内字段，其余键覆盖顶层。"""
    form = {"title": "渠道持仓报表", "demandTypeCode": "TECH",
            "content": "客户经理每天需要查看完整渠道持仓并导出", "urgency": "NORMAL",
            "expectDeliveryAt": "2026-12-31",
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
                      "acceptanceCriteria": "8:30前可查且与核心系统对账误差为0"}}}
    for key, value in overrides.items():
        if "__" in key:
            zone, element = key.split("__", 1)
            form["elements"][zone][element] = value
        else:
            form[key] = value
    return form


def test_full_element_collection_and_positive_java_examples():
    result = assess(get("TECH"), tech())
    assert len(result) == 27  # 29 要素减去 A4/A5 两个 system 快照
    assert all(e.status == "OK" and e.attempts == 0 for e in result)


@pytest.mark.parametrize("zone,key,value,note", [("C", "useScenario", "方便一下", "含歧义词"), ("C", "useScenario", "全部内容经过说明之后确实完整但没有关键词", "看不出"), ("D", "acceptanceCriteria", "希望改得好", "缺可量化"), ("B", "businessValue", "也许很有意义", "缺量化"), ("A", "techSubtype", "UNKNOWN", "选项"), ("C", "useScenario", "", "未填写")])
def test_negative_java_examples(zone, key, value, note):
    item = next(e for e in assess(get("TECH"), tech(**{f"{zone}__{key}": value})) if e.key == key)
    assert item.status != "OK" and note in item.note


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


def test_quality_gap_is_distinct_from_required_schema():
    value = tech(D__acceptanceCriteria="尽快", D__dataRequirements="")
    assert not schema_errors(get("TECH"), value, required=True)
    assert any(e.status != "OK" for e in assess(get("TECH"), value))
    assert schema_errors(get("TECH"), {"title": "标题"}, required=True)
