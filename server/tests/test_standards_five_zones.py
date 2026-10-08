"""五区标准（PRD v1.3 §4）结构校验：要素数量、必填集合、enum 选项、B 区条件必填、判型信号与粒度配置。"""
from app.standards.loader import get
from app.standards.rules import filter_form, schema_errors


def test_five_zone_element_count_and_codes():
    standard = get("TECH")
    assert len(standard.elements) == 29  # A8 + B7 + C6 + D8（PRD v1.3 撤预算后 B 区 7 个）
    by_zone = {}
    for element in standard.elements:
        by_zone.setdefault(element.zone, []).append(element.code)
    assert sorted(by_zone["A"]) == [f"A{i}" for i in range(1, 9)]
    assert sorted(by_zone["B"]) == [f"B{i}" for i in range(1, 8)]
    assert sorted(by_zone["C"]) == [f"C{i}" for i in range(1, 7)]
    assert sorted(by_zone["D"]) == [f"D{i}" for i in range(1, 9)]


def test_required_set_and_system_snapshot():
    standard = get("TECH")
    interactive_required = {e.key for e in standard.elements if e.required and not e.system}
    assert interactive_required == {"title", "demandTypeCode", "techSubtype", "urgency", "content",
                                    "businessGoal", "businessBackground", "businessValue", "stakeholders",
                                    "userRole", "userGoal", "useScenario", "painPoint",
                                    "functionDescription", "inputOutput", "acceptanceCriteria"}
    system = {e.key for e in standard.elements if e.system}
    assert system == {"requester", "dept"}
    # system 快照要素不参与表单校验与判质
    assert not any(e.system and e.zone != "A" for e in standard.elements)


def test_enum_options():
    standard = get("TECH")
    by_key = {e.key: e for e in standard.elements}
    assert set(by_key["demandTypeCode"].options) == {"TECH", "MATL", "TRAIN"}
    assert set(by_key["techSubtype"].options) == {"SYS_DEV", "DATA_RPT", "SYS_INT", "OPS_OPT", "OTHER"}
    assert set(by_key["urgency"].options) == {"NORMAL", "URGENT", "CRITICAL"}
    # 紧急程度不再有默认值，须经追问与用户确认
    assert by_key["urgency"].default is None
    assert by_key["urgency"].ask_missing


def test_enum_label_maps_to_code():
    # 用户点选快捷回复后模型可能回传中文选项名，filter_form 归一为 code
    assert filter_form(get("TECH"), {"demandTypeCode": "TECH", "urgency": "普通"})["urgency"] == "NORMAL"
    assert filter_form(get("TECH"), {"demandTypeCode": "TECH", "urgency": "特急"})["urgency"] == "CRITICAL"
    assert filter_form(get("TECH"), {"demandTypeCode": "TECH", "urgency": "URGENT"})["urgency"] == "URGENT"


def _base_form():
    return {"title": "渠道持仓报表", "demandTypeCode": "TECH", "urgency": "NORMAL",
            "content": "客户经理每天需要查看完整渠道持仓并导出",
            "elements": {"A": {"techSubtype": "DATA_RPT"},
                         "C": {"userRole": "客户经理", "userGoal": "晨会前查持仓汇总",
                               "useScenario": "机构业务部客户经理每天晨会前需要查各机构持仓",
                               "painPoint": "手工汇总每人每天约40分钟"},
                         "D": {"functionDescription": "按机构汇总前一交易日持仓并支持导出",
                               "inputOutput": "输入交易流水，输出机构持仓报表",
                               "acceptanceCriteria": "8:30前可查且对账误差为0"}}}


def test_zone_b_conditional_required():
    standard = get("TECH")
    form = _base_form()
    # B 区未激活：A/C/D 必填满足即可提交（P1 阶段判型未上线）
    assert not schema_errors(standard, form, required=True, active_zones={"A", "C", "D"})
    # B 区激活（判型为业务需求）：B 区必填缺口全部报出
    errors = schema_errors(standard, form, required=True, active_zones={"A", "B", "C", "D"})
    assert {"业务目标未填写", "业务背景未填写", "业务价值未填写", "干系人未填写"} <= set(errors)
    # B 区可空要素不强制
    assert "业务规则/合规约束未填写" not in errors and "所属战略目标未填写" not in errors and "关联需求未填写" not in errors


def test_type_signals_and_granularity_configured():
    standard = get("TECH")
    assert standard.type_signals.business and standard.type_signals.business.keywords
    assert standard.type_signals.user and standard.type_signals.user.keywords
    assert standard.type_signals.function and standard.type_signals.function.keywords
    assert standard.granularity.converge
    assert standard.granularity.too_broad.keywords and standard.granularity.too_broad.hint
    assert standard.granularity.too_narrow.keywords and standard.granularity.too_narrow.hint


def test_list_kind_elements():
    standard = get("TECH")
    by_key = {e.key: e for e in standard.elements}
    assert by_key["stakeholders"].kind == "list"
    assert by_key["relatedDemands"].kind == "list"
    assert by_key["nfrRequirements"].kind == "list"
    form = _base_form()
    form["elements"].setdefault("B", {})["stakeholders"] = "机构业务部"
    assert "干系人必须为列表" in schema_errors(standard, form, required=True, active_zones={"A", "B", "C", "D"})
