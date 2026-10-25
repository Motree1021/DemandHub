"""五区标准（PRD v1.3 §4）结构校验：要素数量、必填集合、enum 选项、B 区条件必填、判型信号与粒度配置。"""
from app.standards.loader import get
from app.standards.rules import filter_form, schema_errors


def test_five_zone_element_count_and_codes():
    standard = get("TECH")
    assert len(standard.elements) == 30  # A8 + B7 + C6 + D9（2026-10-12 新增 D9 建议方案选填）
    by_zone = {}
    for element in standard.elements:
        by_zone.setdefault(element.zone, []).append(element.code)
    assert sorted(by_zone["A"]) == [f"A{i}" for i in range(1, 9)]
    assert sorted(by_zone["B"]) == [f"B{i}" for i in range(1, 8)]
    assert sorted(by_zone["C"]) == [f"C{i}" for i in range(1, 7)]
    assert sorted(by_zone["D"]) == [f"D{i}" for i in range(1, 10)]


def test_required_set_and_system_snapshot():
    standard = get("TECH")
    interactive_required = {e.key for e in standard.elements if e.required and not e.system}
    # 2026-10-19 拍板：content（A8原话底稿）改为系统提取项，移出必填集；
    # 2026-10-24 拍板判型与 B 区解耦：B 区四件套（businessGoal/Background/Value/stakeholders）全量非必填
    assert interactive_required == {"title", "demandTypeCode", "urgency",
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


def test_zone_b_no_longer_required():
    # 判型与 B 区解耦（2026-10-24 拍板）：B 区要素全量非必填——active_zones 即便含 B，
    # B 区空缺也不再产生必填缺口报错（B1 改走提报侧白话一问 + 受理侧 accept 强校验兜底）
    standard = get("TECH")
    form = _base_form()
    assert not schema_errors(standard, form, required=True, active_zones={"A", "C", "D"})
    assert not schema_errors(standard, form, required=True, active_zones={"A", "B", "C", "D"})


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
