from copy import deepcopy

import pytest

from app.agent.policy import (
    CHITCHAT_GREET_FIRST,
    CHITCHAT_GUIDE,
    DESC_INVITE,
    anchored_template,
    complete_elements,
    inherit_and_count,
    merge_mode_signal,
    merge_structured,
    pick_follow_up,
    process,
    reply_for,
    resume_follow_up,
    user_said_skip,
)
from app.agent.schemas import (
    ElementStatus,
    Intent,
    ModelOutput,
    ModeSignalOutput,
    parse_model_output,
)
from app.standards.loader import get
from app.standards.rules import assess, business_confirmed


def form():
    return {"title": "渠道报表", "demandTypeCode": "TECH", "content": "客户经理每天需要查渠道报表和导出", "urgency": "NORMAL", "elements": {"A": {"techSubtype": "DATA_RPT"}}}


def acd_filled_form():
    """A/C/D 共12项必填全部填好、B 区留空的表单。"""
    return {"title": "渠道报表", "demandTypeCode": "TECH", "content": "客户经理每天需要查渠道报表和导出发送给负责人", "urgency": "NORMAL",
            "elements": {
                "A": {"techSubtype": "DATA_RPT"},
                "C": {"userRole": "机构业务部客户经理", "userGoal": "每天晨会前快速查各机构持仓",
                      "useScenario": "客户经理每个交易日晨会前查各渠道持仓",
                      "painPoint": "手工汇总20个机构数据每次近1小时还容易错"},
                "D": {"functionDescription": "按渠道汇总前一交易日持仓并支持导出",
                      "inputOutput": "输入交易流水，输出按渠道汇总的持仓报表",
                      "acceptanceCriteria": "每个交易日8:30前可查且与核心系统对账误差为0"}}}


def b1_filled(form_value):
    """填入合格 B1 业务目标（2026-10-24 拍板 B1 白话一问治理前置）：
    让与 B1 无关的用例隔离「必问一次」追问，保持原断言聚焦自身语义。"""
    form_value["elements"]["B"] = {"businessGoal": "帮部门省下专职整理岗，释放一个人力"}
    return form_value


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
    result, sources, _ = merge_structured({"elements": {"A": {"urgency": "URGENT", "expectDeliveryAt": "2099-10-15"}}}, form(), {})
    assert result["urgency"] == "URGENT" and result["expectDeliveryAt"] == "2099-10-15"
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


def test_status_word_values_are_dropped():
    # 模型把质量状态词当值输出（真实链路已观测 elements.B.businessGoal="VAGUE"）属自相矛盾，按未输出过滤，
    # 否则判型升级后 B 区会被"VAGUE"字面量伪造成已填
    result, sources, _ = merge_structured({"elements": {"B": {"businessGoal": "VAGUE", "businessBackground": " missing "}}}, form(), {})
    assert not (result["elements"].get("B") or {})
    assert "elements.B.businessGoal" not in sources


def test_process_relocates_nested_urgency_and_moves_on():
    # 全链路：用户说"很紧急"模型输出 elements.A.urgency，归位后不再回头追问紧急程度；
    # 同轮抽出的交付日期一并落库——急单门控见日期已填不再追问时间，直接进入 C 区
    base = form()
    del base["urgency"]
    output = ModelOutput(structured={"elements": {"A": {"urgency": "URGENT", "expectDeliveryAt": "2099-10-20"}}}, elements=[])
    result = process(output, base, {}, [], None, {}, "很紧急，本周要上线")
    assert result["structured"]["urgency"] == "URGENT"
    assert result["structured"]["expectDeliveryAt"] == "2099-10-20"
    assert next(e for e in result["elements"] if e["key"] == "urgency")["status"] == "OK"
    # 无业务判型：A 区填完后先追问 C 区（目标用户），不追问 B 区业务目标
    assert result["askedTarget"] == "userRole" and "紧急" not in result["reply"]


def test_urgent_quick_reply_inserts_delivery_date_question():
    # 急单门控（2026-10-12）：AI 问紧急度 → 用户点选快捷项「紧急」（消息只有枚举标签、无时间信息可抽）
    # → 下一句立即追问期望交付时间，承接「紧急或特急请说明期望时间」的话术承诺
    base = form()
    del base["urgency"]
    result = process(ModelOutput(structured={"urgency": "URGENT"}, elements=[]), base, {}, [], "urgency", {}, "紧急")
    assert result["structured"]["urgency"] == "URGENT"
    assert result["askedTarget"] == "expectDeliveryAt"
    assert "期望什么时候交付" in result["reply"]


def test_urgent_delivery_gate_cases():
    standard = get("TECH")
    # B1 白话一问（2026-10-24 拍板）与急单门控无关：填 B1 隔离，专注急单门控语义
    elements = assess(standard, b1_filled(acd_filled_form()))
    # 普通：不问日期（话术已说普通按常规排期），A/C/D 齐即正常完成
    assert pick_follow_up(standard, elements, form=b1_filled(acd_filled_form())) is None
    # 紧急且日期空：插队最优先
    urgent = {**b1_filled(acd_filled_form()), "urgency": "URGENT"}
    assert pick_follow_up(standard, elements, form=urgent).key == "expectDeliveryAt"
    # 紧急但日期已填：不问
    filled = {**urgent, "expectDeliveryAt": "2099-10-31"}
    assert pick_follow_up(standard, assess(standard, filled), form=filled) is None
    # 问满两次仍无日期：放过不拦截（期望时间非必填）
    asked_twice = [e.model_copy(update={"attempts": 2}) if e.key == "expectDeliveryAt" else e for e in elements]
    assert pick_follow_up(standard, asked_twice, form=urgent) is None


def test_no_soft_quality_followup_once_submittable():
    # 口径一A（2026-10-12）：必填已齐（can_submit=True）后，有值但被判"不够量化"的非空必填项
    # 不再主动追问——完成话术承诺「不太完整不影响提交、以后能补」，继续追问即前后矛盾。
    # B1 白话一问（2026-10-24 拍板）属治理型必问（与急单门控同性质），不受「可提交即停问」限制：
    # B1 空时先问 B1；问过一次（attempts 用尽）后才回到软质量/无目标口径
    standard = get("TECH")
    # 必填齐全但验收标准被判 VAGUE（不够量化）的场景
    value = acd_filled_form()
    value["elements"]["D"]["acceptanceCriteria"] = "希望改得好一些"  # 空话 → VAGUE
    elements = assess(standard, value)
    assert next(e for e in elements if e.key == "acceptanceCriteria").status == "VAGUE"
    # B1 空：先问 B1 白话一问（不论是否已达门槛）
    assert pick_follow_up(standard, elements, form=value, can_submit=False).key == "businessGoal"
    asked_b1 = [e.model_copy(update={"attempts": 1}) if e.key == "businessGoal" else e for e in elements]
    # B1 问过后、未达可提交门槛（can_submit=False）时：VAGUE 必填项仍会追问（推动完善）
    assert pick_follow_up(standard, asked_b1, form=value, can_submit=False).key == "acceptanceCriteria"
    # 已达可提交门槛（can_submit=True）时：不再追问非空 VAGUE，交给表单卡片/打回兜底
    assert pick_follow_up(standard, asked_b1, form=value, can_submit=True) is None
    # MISSING（真空着）不受此限：必填缺口即使 can_submit 边界也仍应被追问/拦截
    value2 = acd_filled_form()
    del value2["elements"]["D"]["functionDescription"]
    elements2 = assess(standard, value2)
    assert next(e for e in elements2 if e.key == "functionDescription").status == "MISSING"
    # 注意：functionDescription MISSING 时 can_submit 本就为 False，此处验证 MISSING 仍被追问
    assert pick_follow_up(standard, elements2, form=value2, can_submit=False).key == "functionDescription"


def test_light_mode_urgent_gate_applies():
    # 急单门控 light 同规（2026-10-20 拍板）：轻量选了紧急同样插队追问交付日期——急单不分轻重，
    # 「请说明期望时间」承诺不落空；遵守 light「每项最多问一次」：问满 1 次即放过，恢复最小集顺序
    standard = get("TECH")
    base = {"title": "更换首页顶部logo", "demandTypeCode": "TECH", "content": "把首页顶部的logo换成新设计的蓝色版本", "urgency": "URGENT", "elements": {}}
    elements = assess(standard, base, light=True)
    assert pick_follow_up(standard, elements, light=True, form=base).key == "expectDeliveryAt"
    # 问满 1 次仍无日期：放过（light 上限比 standard 更严），回到最小集追问期望效果
    asked_once = [e.model_copy(update={"attempts": 1}) if e.key == "expectDeliveryAt" else e for e in elements]
    assert pick_follow_up(standard, asked_once, light=True, form=base).key == "acceptanceCriteria"


def test_matl_urgent_gate_not_applicable():
    # MATL/TRAIN 的期望时间在 common_fields、不在追问循环：急单门控仅 TECH 生效
    standard = get("MATL")
    form_value = {"demandTypeCode": "MATL", "urgency": "URGENT"}
    assert pick_follow_up(standard, assess(standard, form_value), form=form_value).key == "title"


def test_missing_collection_cannot_fake_quality_complete():
    result = process(ModelOutput(structured={}, elements=[]), form(), {}, [], None, {}, "报表")
    assert len(result["elements"]) == 26  # 30 要素减 A4/A5 system 快照，再减 D9 与 A3 子类不参与评估（2026-10-15）
    assert not result["canSubmit"] and not result["ready"]
    assert not result["qualityComplete"] and not result["guidanceComplete"]
    # 无业务判型：先追问 A/C/D，首个缺口是 C 区目标用户，不追问 B 区
    assert result["askedTarget"] == "userRole" and "给谁用" in result["reply"]


def test_business_recognition_follows_acd_before_zone_b():
    # A/C/D 未齐时仍先追 A/C/D（userRole），B1 白话一问沉底（2026-10-24 起与判型无关：重量级必问一次）
    value = form()
    value["ext"] = {"typeRecognition": {"business": 0.9, "confirmed": None}}
    result = process(ModelOutput(structured={"ext": {"typeRecognition": {"business": 0.9}}}, elements=[]), value, {}, [], None, {}, "报表")
    assert result["askedTarget"] == "userRole"


def test_b1_plain_ask_once_after_acd_complete_regardless_of_type():
    # B1 白话一问（2026-10-24 拍板，判型与 B 区解耦）：standard 需求 A/C/D 必填问完后必问一次
    # businessGoal——触发条件是重量级而非判型标签（无判型信号也问）；B 区不再拦提交（canSubmit=True）
    result = process(ModelOutput(structured={}, elements=[]), acd_filled_form(), {}, [], None, {}, "报表")
    assert result["askedTarget"] == "businessGoal"
    assert result["canSubmit"] is True
    assert "对部门或行里还有啥好处" in result["reply"] and "不清楚也没关系" in result["reply"]
    # 业务判型信号下同一问法（判型只影响归类展示，不影响追问与门槛）
    value = acd_filled_form()
    value["ext"] = {"typeRecognition": {"business": 0.9, "confirmed": None}}
    result_b = process(ModelOutput(structured={"ext": {"typeRecognition": {"business": 0.9}}}, elements=[]), value, {}, [], None, {}, "报表")
    assert result_b["askedTarget"] == "businessGoal" and result_b["canSubmit"] is True


def test_b1_unanswerable_releases_with_fixed_wording():
    # 答不出放行（2026-10-24 拍板）：B1 白话一问答「不清楚」→ 固定放行书 + SKIP 终结，
    # 不追问第二次、不标质量问题、不拦提交；放行书不承诺「后续找谁补」
    base = acd_filled_form()
    first = process(ModelOutput(structured={}, elements=[]), base, {}, [], None, {}, "报表")
    assert first["askedTarget"] == "businessGoal"
    prev = [ElementStatus.model_validate(e) for e in first["elements"]]
    second = process(ModelOutput(structured={}, elements=[]),
                     first["structured"], first["fieldSources"], prev, "businessGoal",
                     base, "不清楚")
    assert "没事，这个先空着，不耽误提交，后面的产品经理会一起考虑。" in second["reply"]
    assert "提报人" not in second["reply"] and "受理" not in second["reply"]  # 话术红线：禁用角色/流程术语
    b1 = next(e for e in second["elements"] if e["key"] == "businessGoal")
    assert b1["status"] == "SKIP" and b1["attempts"] == 0
    assert second["askedTarget"] is None and second["canSubmit"] is True
    # 下一轮：B1 已 SKIP，永久不再追问
    prev2 = [ElementStatus.model_validate(e) for e in second["elements"]]
    third = process(ModelOutput(structured={}, elements=[]),
                    second["structured"], second["fieldSources"], prev2, None,
                    second["structured"], "继续")
    assert third["askedTarget"] is None and third["canSubmit"] is True


def test_b1_answered_lands_and_not_reasked():
    # 答出组织理由 → 如实落 B1（口径放宽：「释放产能」类非量化表述也算合格）；问过一次即终结
    base = acd_filled_form()
    first = process(ModelOutput(structured={}, elements=[]), base, {}, [], None, {}, "报表")
    prev = [ElementStatus.model_validate(e) for e in first["elements"]]
    output = ModelOutput(structured={"elements": {"B": {"businessGoal": "帮部门省下专职整理岗，释放一个人力"}}}, elements=[])
    second = process(output, first["structured"], first["fieldSources"], prev, "businessGoal",
                     base, "能省下一个人力专门做整理")
    assert second["structured"]["elements"]["B"]["businessGoal"] == "帮部门省下专职整理岗，释放一个人力"
    b1 = next(e for e in second["elements"] if e["key"] == "businessGoal")
    assert b1["status"] == "OK"
    assert second["askedTarget"] is None and second["canSubmit"] is True


def test_b1_landing_promotes_business_recognition():
    # B1 落库即判业务（2026-10-24 拍板）：B1 从空答出落库 → business 票补足到 0.7 门槛（硬证据优先软分数，
    # 判线=主句级起点，档位对齐），层级判定下即翻转为业务需求——#27 草稿类场景（user 0.85 天花板翻不动）的根治
    base = acd_filled_form()
    base["ext"] = {"typeRecognition": {"business": 0.3, "user": 0.85, "function": 0.6, "confirmed": None,
                                       "evidence": {"user": "客户经理自己要用"}}}
    output = ModelOutput(structured={"elements": {"B": {"businessGoal": "帮部门省下专职整理岗，释放一个人力"}}}, elements=[])
    result = process(output, base, {}, [], "businessGoal", base, "能省下一个人力")
    recognition = result["structured"]["ext"]["typeRecognition"]
    assert recognition["business"] == 0.7 and business_confirmed(recognition)
    # 模型没给 business 依据时回填 B1 原文，其他票与 confirmed 原样保留
    assert recognition["evidence"]["business"] == "帮部门省下专职整理岗，释放一个人力"
    assert recognition["user"] == 0.85 and recognition["confirmed"] is None


def test_b1_landing_respects_user_confirmed():
    # 人工定稿优先（2026-10-24 拍板）：confirmed 非空时 B1 落库不翻转
    base = acd_filled_form()
    base["ext"] = {"typeRecognition": {"business": 0.3, "user": 0.85, "function": 0.6, "confirmed": "user"}}
    output = ModelOutput(structured={"elements": {"B": {"businessGoal": "帮部门省下专职整理岗，释放一个人力"}}}, elements=[])
    result = process(output, base, {}, [], "businessGoal", base, "能省下一个人力")
    recognition = result["structured"]["ext"]["typeRecognition"]
    assert recognition["business"] == 0.3 and not business_confirmed(recognition)


def test_b1_skip_or_reedit_does_not_promote():
    # 答不出（SKIP 不落库）不翻转；B1 已有值的修改（非「空→有」）不重复提升——幂等
    base = acd_filled_form()
    base["ext"] = {"typeRecognition": {"business": 0.3, "user": 0.85, "function": 0.6, "confirmed": None}}
    skipped = process(ModelOutput(structured={}, elements=[]), base, {}, [], "businessGoal", base, "不清楚")
    recognition = skipped["structured"]["ext"]["typeRecognition"]
    assert recognition["business"] == 0.3 and not business_confirmed(recognition)
    # B1 已有值 → 再改内容：非「空→有」，不提升
    base2 = b1_filled(acd_filled_form())
    base2["ext"] = {"typeRecognition": {"business": 0.3, "user": 0.85, "function": 0.6, "confirmed": None}}
    output = ModelOutput(structured={"elements": {"B": {"businessGoal": "改成另一个组织理由，覆盖旧值"}}}, elements=[])
    edited = process(output, base2, {}, [], None, base2, "改一下业务目标")
    assert edited["structured"]["ext"]["typeRecognition"]["business"] == 0.3


def test_anchor_falls_back_to_normal_ask_when_reference_empty():
    # 关联要素未填（如追问次数耗尽跳过）时回落普通追问模板，不引用空锚点
    standard = get("TECH")
    target = ElementStatus(key="stakeholders", status="MISSING", attempts=0)
    assert "谁是受益方" in reply_for(standard, target, {"elements": {"C": {}}})
    anchored = reply_for(standard, target, {"elements": {"C": {"userRole": "机构业务部客户经理"}}})
    assert "主要使用方" in anchored and "谁是受益方" not in anchored


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
    # 标题补齐后 A 区完整，无业务判型先追 C 区目标用户
    assert result["askedTarget"] == "userRole"
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
    # useScenario 追问达上限后跳过它；非业务需求不追 B 区，顺延到 C 区更靠前的目标用户
    nxt = pick_follow_up(standard, second)
    assert nxt.key != "useScenario" and nxt.key == "userRole"


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


# ---- 微需求快速通道（2026-10-11 方案②）：mode 判定与 light 编排 ----


def light_form(**overrides):
    """换 logo 微需求形态：A1 标题 + A8 原话已给，C/D 其余全空；紧急度/期望效果按测试覆盖。"""
    value = {"title": "更换首页顶部logo", "demandTypeCode": "TECH",
             "content": "把首页顶部的logo换成新设计的蓝色版本", "elements": {}}
    value.update(overrides)
    return value


@pytest.mark.parametrize("prev,signal,expected", [
    (None, ModeSignalOutput(level="light", evidence="换logo"), "light"),      # 首次判定 light
    (None, ModeSignalOutput(level="standard", evidence="新报表"), "standard"),  # 首次判定 standard
    ({"level": "light", "evidence": "换logo"}, None, "light"),                # 本轮未输出：保留旧判定
    (None, None, None),                                                        # 从未判定且未输出
    ({"level": "standard", "evidence": "新报表"}, ModeSignalOutput(level="light", evidence="x"), "standard"),  # standard 粘性不回退
    ({"level": "light", "evidence": "换logo"}, ModeSignalOutput(level="standard", evidence="改登录鉴权"), "standard"),  # light 可升级
])
def test_merge_mode_signal_sticky_standard(prev, signal, expected):
    form_value = {"ext": {"mode": prev}} if prev is not None else {}
    merged = merge_mode_signal(signal, form_value)
    assert (merged or {}).get("level") == expected


def test_light_follow_up_limited_to_minimal_set_once_each():
    standard = get("TECH")
    base = light_form()
    elements = assess(standard, base, light=True)
    # light 首问期望效果（2026-10-15 紧急度沉底：期望效果→标题兜底→紧急度）；standard 口径
    # 紧急度同步沉底，A3 子类已退出追问，按 yaml 必填顺序首个缺口是 C1 目标用户
    assert pick_follow_up(standard, elements, light=True).key == "acceptanceCriteria"
    assert pick_follow_up(standard, elements).key == "userRole"
    once = inherit_and_count(elements, elements, "acceptanceCriteria", False, standard=standard, previous_form=base, form=base)
    assert pick_follow_up(standard, once, light=True).key == "urgency"
    twice = inherit_and_count(once, elements, "urgency", False, standard=standard, previous_form=base, form=base)
    # 每项只问一次：两轮后即使紧急度仍缺也不再追问，C 区缺口更不问（合计≤2轮）
    assert pick_follow_up(standard, twice, light=True) is None


def test_light_d8_first_ask_confirms_ai_title_with_plain_effect_question():
    standard = get("TECH")
    target = ElementStatus(key="acceptanceCriteria", status="MISSING", attempts=0)
    with_title = reply_for(standard, target, {"title": "更换首页顶部logo"}, light=True)
    assert "标题我先记为「更换首页顶部logo」" in with_title
    assert "期望的效果" in with_title
    without_title = reply_for(standard, target, {}, light=True)
    assert "标题我先记为" not in without_title and "期望的效果" in without_title
    # standard 口径仍是「可检查的标准」量化验收话术，不引用白话效果问法
    assert "可检查的标准" in reply_for(standard, target, {"title": "x"})


def test_light_reply_completion_follows_minimal_gate():
    standard = get("TECH")
    complete = light_form(urgency="NORMAL", elements={"D": {"acceptanceCriteria": "首页顶部logo显示为新设计的蓝色版本"}})
    assert "可以提交" in reply_for(standard, None, complete, light=True)
    # 最小集有缺口但追问额度用完：指引到表单补齐
    incomplete = light_form()
    elements = [e.model_copy(update={"attempts": 1}) if e.key in ("urgency", "acceptanceCriteria") else e
                for e in assess(standard, incomplete, light=True)]
    assert pick_follow_up(standard, elements, light=True) is None
    assert "下方表单里补齐" in reply_for(standard, None, incomplete, light=True)


def test_completion_reply_ignores_b_zone_gap():
    # 判型与 B 区解耦（2026-10-24 拍板）：B 区要素全部非必填，完成话术不再按判型区分——
    # B 区空缺的 A/C/D 齐表单直接给「可以提交」（原 business=True 时 B 区缺口报「必填没填」的门槛已拆除）
    standard = get("TECH")
    reply = reply_for(standard, None, acd_filled_form())
    assert "可以提交" in reply and "把标红星※的必填项补齐" not in reply


def test_return_reason_is_quoted_in_reply():
    # 打回闭环（方案③ + 2026-10-20 拍板）：补充会话首次对话前置白话引述打回原因，重提清除后引述自然消失；
    # 完成话术是打回补充口径（「确认提交」重新提交），不再播新草稿的选填项长说明；
    # 填 B1 隔离「必问一次」治理型追问（2026-10-24 拍板），专注打回引述语义
    base = b1_filled(acd_filled_form())
    base["ext"] = {"returnReason": {"reason": "缺少使用场景说明，请补充后重新提交"}}
    result = process(ModelOutput(structured={}, elements=[]), base, {}, [], None, {}, "我来看看还需要补充什么")
    assert result["reply"].startswith("这条需求之前被打回过")
    assert "打回原因是「缺少使用场景说明，请补充后重新提交」" in result["reply"]
    assert "重新提交" in result["reply"] and "以后能补" not in result["reply"]
    # return_quoted=False（本补充会话已引述过）：只给简短确认，不重复引述
    again = process(ModelOutput(structured={}, elements=[]), base, {}, [], None, {}, "附件传好了",
                    return_quoted=False)
    assert not again["reply"].startswith("这条需求之前被打回过")
    assert "确认提交" in again["reply"]


def test_resume_follow_up_quotes_return_reason():
    """规则接续（resume_follow_up，2026-10-20 拍板）：
    returnReason 留存且首次时 reply 前置白话引述打回原因；有缺口选中追问，无缺口给重提话术；
    return_quoted=False 不再引述（补充会话只引述一次）。"""
    standard = get("TECH")
    base = acd_filled_form()
    base["ext"] = {"returnReason": {"reason": "缺少使用场景说明，请补充后重新提交"}}
    base["elements"]["C"]["userRole"] = ""  # 制造缺口：规则接续应选中追问
    result = resume_follow_up(standard, base, None, trigger="enter")
    assert result["reply"].startswith("这条需求之前被打回过")
    assert "打回原因是「缺少使用场景说明，请补充后重新提交」" in result["reply"]
    assert result["canSubmit"] is False and result["askedTarget"] == "userRole"
    # 无缺口（打回原因与要素无关）：引述仍在，canSubmit=True → 重进即见「确认提交」；
    # 填 B1 隔离「必问一次」治理型追问（2026-10-24 拍板）
    full = b1_filled(acd_filled_form())
    full["ext"] = {"returnReason": {"reason": "请把标题改得更准确些"}}
    done = resume_follow_up(standard, full, None, trigger="attachment")
    assert done["reply"].startswith("这条需求之前被打回过")
    assert "确认提交" in done["reply"] and "以后能补" not in done["reply"]
    assert done["canSubmit"] is True and done["askedTarget"] is None
    # 已引述过：附件动作不再引述，话术只给行动指引
    later = resume_follow_up(standard, full, None, trigger="attachment", return_quoted=False)
    assert not later["reply"].startswith("这条需求之前被打回过")
    assert "确认提交" in later["reply"]


def test_light_mode_minimal_set_can_submit_without_acd():
    base = light_form(urgency="NORMAL")
    output = ModelOutput(structured={"elements": {"D": {"acceptanceCriteria": "首页顶部logo显示为新设计的蓝色版本"}}},
                         elements=[], mode_signal=ModeSignalOutput(level="light", evidence="换logo属于小改动"))
    result = process(output, base, {}, [], None, {}, "把首页顶部logo换成新设计的蓝色版本")
    assert result["mode"] == {"level": "light", "evidence": "换logo属于小改动"}
    assert result["structured"]["ext"]["mode"]["level"] == "light"
    assert result["fieldSources"]["ext.mode"] == "agent"
    # C/D 12 项大片缺失（目标用户/功能描述等全空）不追问不拦截，最小集齐即可提交
    assert result["askedTarget"] is None and result["canSubmit"] is True
    assert next(e for e in result["elements"] if e["key"] == "userRole")["status"] == "MISSING"
    # 方案④首判轻量播报：此前判轻量一声不吭，用户不知道为何只问 4 项；现当轮回复前置白话说明
    assert result["reply"].startswith("这个需求听起来是个小改动，我按轻量提报帮你登记")
    assert "都记好了" in result["reply"]


def test_light_first_judgment_announcement_once_only():
    """首判播报只在第一次判轻量时出现：次轮再判 light 不重复、用户手动定过口径不播。"""
    output = ModelOutput(structured={}, elements=[], mode_signal=ModeSignalOutput(level="light", evidence="换logo"))
    # 次轮（prev 已是 light）：不播
    prev = light_form(urgency="NORMAL")
    prev["ext"] = {"mode": {"level": "light", "evidence": "换logo"}}
    again = process(output, prev, {}, [], None, {}, "还是换logo，别的没补充")
    assert "我按轻量提报帮你登记" not in again["reply"]
    # 用户手动定过口径（origin=user）：AI 不翻转也不播
    manual = light_form(urgency="NORMAL")
    manual["ext"] = {"mode": {"level": "light", "evidence": "提报人手动调整提报口径", "origin": "user"}}
    result = process(ModelOutput(structured={}, elements=[], mode_signal=ModeSignalOutput(level="standard", evidence="模型又觉得不小")),
                     manual, {}, [], None, {}, "就换个logo，别的都不用动")
    assert result["mode"]["level"] == "light" and result["mode"]["origin"] == "user"
    assert "我按轻量提报帮你登记" not in result["reply"]


def test_light_mode_asks_effect_before_urgency():
    """light 模式紧急度沉底（2026-10-15 拍板）：首问期望效果（连带确认 AI 代拟标题），紧急度最后问。"""
    output = ModelOutput(structured={}, elements=[], mode_signal=ModeSignalOutput(level="light", evidence="换logo"))
    result = process(output, light_form(), {}, [], None, {}, "把首页顶部logo换成新设计的蓝色版本")
    assert result["askedTarget"] == "acceptanceCriteria" and not result["canSubmit"]
    assert "期望的效果" in result["reply"] and "给谁用" not in result["reply"]
    assert "有多紧急" not in result["reply"]


def test_scenario_anchor_quotes_known_role_and_task():
    """C3 双锚定（2026-10-15 拍板）：角色/任务已识别时场景追问引述已知信息请用户确认或纠正，
    只问未覆盖的缺口（双锚→时机/频率），不再重复问「谁（角色）」。"""
    standard = get("TECH")
    field = next(e for e in standard.elements if e.key == "useScenario")
    # 双锚（角色+任务都已知）：引述两者，只问时机/频率
    both = anchored_template(standard, field, {"elements": {"C": {"userRole": "吉林交行产品经理张铮", "userGoal": "制作口播数字人短视频"}}})
    assert "「吉林交行产品经理张铮」" in both and "「制作口播数字人短视频」" in both
    assert "谁（角色）" not in both and "纠正" in both and "什么时间" in both
    # 单锚（仅角色已知）：引述角色，问时机/频率+做什么
    single = anchored_template(standard, field, {"elements": {"C": {"userRole": "吉林交行产品经理张铮"}}})
    assert "「吉林交行产品经理张铮」" in single and "谁（角色）" not in single and "纠正" in single
    # 角色未知：返回空串，回落 ask_missing 原话术（照旧问谁/什么时间/做什么）
    assert anchored_template(standard, field, {"elements": {"C": {"userGoal": "制作口播数字人短视频"}}}) == ""


def test_mode_standard_is_sticky_in_conversation():
    prev = light_form(urgency="NORMAL")
    prev["ext"] = {"mode": {"level": "standard", "evidence": "自动生成销量报表属于新功能"}}
    output = ModelOutput(structured={}, elements=[], mode_signal=ModeSignalOutput(level="light", evidence="其实只想改个logo"))
    result = process(output, prev, {}, [], None, {}, "其实只想改个logo")
    assert result["mode"]["level"] == "standard"
    # 常规口径追问恢复：A3 子类已退出追问（2026-10-15），恢复后按必填顺序问首个 C 区缺口
    assert result["askedTarget"] == "userRole"


def test_mode_upgrade_to_standard_announces_and_reapplies_full_gate():
    prev = light_form(urgency="NORMAL", elements={"D": {"acceptanceCriteria": "首页顶部logo显示为新设计的蓝色版本"}})
    prev["ext"] = {"mode": {"level": "light", "evidence": "换logo"}}
    output = ModelOutput(structured={}, elements=[], mode_signal=ModeSignalOutput(level="standard", evidence="顺带要改登录鉴权，影响面大"))
    result = process(output, prev, {}, [], None, {}, "顺便把登录鉴权也改了吧")
    assert result["mode"]["level"] == "standard"
    assert result["reply"].startswith("这个需求听起来改动面不小，我按常规需求帮你把基本信息问齐。")
    assert not result["canSubmit"]  # 常规门槛重新生效：C/D 缺口再次拦截提交


# ---- D9 建议方案（2026-10-12 拍板）：提报人设想的候选方案/实现路径的承载与播报 ----
# 背景：coze 迁移/备案样本里用户给的「两个方案二选一」此前被五区白名单静默丢弃，AI 还回「都记好了」构成误导。

COZE_SOLUTION = "方案1：将系统从coze平台迁移到公司自己的H5服务器，用fenhang这个备案号的域名；方案2：在火山上为coze申请企业专用域名并备案。两个方案2选1"


def test_proposed_solution_first_extraction_announced():
    """coze 样本：候选方案如实落 D9（保留二选一关系），回复后置引述式「已记入建议方案·供评估」话术
    （2026-10-15 调整：引述原文片段+置于追问之后，误归类时用户能认出并纠正），且不追问 D9。"""
    output = ModelOutput(structured={"elements": {"D": {"proposedSolution": COZE_SOLUTION}}},
                         elements=[], mode_signal=ModeSignalOutput(level="standard", evidence="平台迁移+域名备案，实现路径有分量"))
    result = process(output, form(), {}, [], None, {}, "期望的解决方案：1.迁移到公司H5服务器用fenhang域名；2.在火山为coze申请企业域名并备案。2选1")
    assert result["structured"]["elements"]["D"]["proposedSolution"] == COZE_SOLUTION
    # 引述式：话术中含 proposedSolution 原文片段（超长截 30 字加省略号）；
    # 多段拼接排版（2026-10-23 拍板）：播报去尾精简、置于追问之前空行成段，行动项（追问）沉底
    assert "你说的「方案1：将系统从coze平台迁移到公司自己的H5服务器" in result["reply"]
    notice = "我先记到「建议方案」里，随需求给受理方参考。"
    assert notice in result["reply"]
    paragraphs = result["reply"].split("\n\n")
    assert notice in paragraphs[0] and paragraphs[-1].startswith("这个需求主要给谁用")
    assert result["askedTarget"] != "proposedSolution"


def test_proposed_solution_announcement_once_only():
    """播报只在首次落值时发一次：D9 已有值时本轮再输出新内容不重播（更新值但不重复告知）。"""
    base = form()
    base["elements"]["D"] = {"proposedSolution": COZE_SOLUTION}
    output = ModelOutput(structured={"elements": {"D": {"proposedSolution": "补充：团队倾向方案1，先迁移再备案"}}}, elements=[])
    result = process(output, base, {}, [], None, {}, "补充一下，我们团队倾向方案1")
    assert result["structured"]["elements"]["D"]["proposedSolution"] == "补充：团队倾向方案1，先迁移再备案"
    assert "记到「建议方案」" not in result["reply"]


def test_proposed_solution_not_in_gates_or_follow_ups():
    """D9 定位是"设想供评估"：不入 follow_up_order、不进必填集合，空值不拦提交、永不作为追问目标。"""
    standard = get("TECH")
    assert "proposedSolution" not in standard.follow_up_order
    assert not any(e.key == "proposedSolution" and e.required for e in standard.elements)
    # A/C/D 12 项必填齐全、D9 为空：照常可提交；填 B1 隔离「必问一次」治理型追问（2026-10-24 拍板）
    result = process(ModelOutput(structured={}, elements=[]), b1_filled(acd_filled_form()), {}, [], None, {}, "报表")
    assert result["canSubmit"] is True and result["askedTarget"] is None


def test_tech_subtype_never_asked_and_not_blocking():
    """A3 子类改 AI 自动归类（2026-10-15 拍板）：选填、不入 follow_up_order，空值不追问、不拦提交。"""
    standard = get("TECH")
    assert "techSubtype" not in standard.follow_up_order
    assert not any(e.key == "techSubtype" and e.required for e in standard.elements)
    # A/C/D 必填齐全、A3 为空：照常可提交，且不会把 A3 选为追问目标
    form_no_subtype = acd_filled_form()
    del form_no_subtype["elements"]["A"]["techSubtype"]
    result = process(ModelOutput(structured={}, elements=[]), form_no_subtype, {}, [], None, {}, "报表")
    assert result["canSubmit"] is True and result["askedTarget"] != "techSubtype"


# ---- 意图分流（2026-10-19 拍板）：模型判断「用户在做什么」，计数/话术/接续由纯函数决定 ----


def test_supplement_updates_and_returns_to_pending_question():
    """问题①：用户没答当前问题、补充了之前要素——补充照常落库并引述确认，
    当前问题不按「答错」计 attempts，话术桥接回到当前问题节点而非跳到下一问。"""
    standard = get("TECH")
    base = form()
    prev = assess(standard, base)
    # 第一轮：AI 问目标用户，用户答得不合格 → attempts=1
    first = inherit_and_count(prev, prev, "userRole", False, standard=standard, previous_form=base, form=base)
    # 第二轮：用户没答，转而补充了使用场景
    output = ModelOutput(structured={"elements": {"C": {"useScenario": "客户经理每天晨会前查各渠道持仓"}}},
                         elements=[], intent=Intent(kind="supplement", target_key="useScenario"))
    result = process(output, base, {}, first, "userRole", base, "补充一下场景：客户经理每天晨会前查持仓")
    assert result["structured"]["elements"]["C"]["useScenario"] == "客户经理每天晨会前查各渠道持仓"
    # 当前问题未被作答：attempts 不增加（补充不算答错），状态仍 MISSING
    urs = next(e for e in result["elements"] if e["key"] == "userRole")
    assert urs["attempts"] == 1 and urs["status"] == "MISSING"
    # 回到当前问题节点，而非顺推到下一个缺口
    assert result["askedTarget"] == "userRole"
    # 引述式确认（引新值片段请用户当场纠错）+ 桥接回当前问题
    assert "「使用场景」已更新：客户经理每天晨会前查各渠道持仓" in result["reply"]
    assert "回到刚才的问题" in result["reply"]


def test_supplement_many_changes_merged_into_summary():
    """播报瘦身（2026-10-25 拍板）：改名类机械联动波及 ≥3 个字段时不再逐条引述截断长文，
    合并为一句汇总（列字段名、不带值预览，细节看表单卡）；列表值不以 ['…'] 内部格式外泄。"""
    standard = get("TECH")
    base = form()
    prev = assess(standard, base)
    first = inherit_and_count(prev, prev, "urgency", False, standard=standard, previous_form=base, form=base)
    output = ModelOutput(
        structured={"elements": {
            "B": {"businessBackground": "张铮一个人运营自媒体账号", "stakeholders": ["张铮（产品经理）"]},
            "C": {"userRole": "产品经理张铮", "useScenario": "张铮运营自媒体账号"}},
        },
        elements=[], intent=Intent(kind="supplement", target_key="stakeholders"))
    result = process(output, base, {}, first, "urgency", base, "名字不是张征，而是张铮")
    reply = result["reply"]
    assert "好的，已按你说的同步更新了 4 处：业务背景、干系人、目标用户角色、使用场景。" in reply
    assert "已更新：" not in reply and "['" not in reply


def test_supplement_without_changes_acknowledges():
    """补充意图但模型没抽出可落库的新值：温和确认，不编造引述。"""
    base = form()
    output = ModelOutput(structured={}, elements=[], intent=Intent(kind="supplement"))
    result = process(output, base, {}, [], "userRole", base, "我再想想，刚才说的场景不变")
    assert result["reply"].startswith("好的，补充的我记下了。")


def test_chitchat_first_turn_cleans_backfilled_content():
    """问题③+单问题原则（2026-10-20 拍板）：首句「您好」被 prepare 误回填为 A8 底稿——闲聊分流清理；
    首轮（prev 为空=还没有正式结果）只发简短引导、不追问、askedTarget 记空——
    此前连发引导+标题确认两个问题，用户不知答哪个。"""
    polluted = {**form(), "content": "您好"}
    output = ModelOutput(structured={}, elements=[], intent=Intent(kind="chitchat"))
    result = process(output, polluted, {"content": "user"}, [], None, polluted, "您好")
    # 误回填的底稿与来源一并清理，脏数据不留草稿
    assert not result["structured"].get("content") and "content" not in result["fieldSources"]
    assert result["typeRecognition"] is None and result["mode"] is None
    assert result["reply"] == CHITCHAT_GREET_FIRST
    assert result["askedTarget"] is None and result["quickReplies"] == []
    assert result["intent"] == "chitchat"


def test_chitchat_mid_conversation_keeps_draft_and_resumes_without_penalty():
    """对话中期闲聊：A8 已有真实底稿（≠本轮消息）不误伤；重问当前问题且 attempts 不计数。"""
    standard = get("TECH")
    base = form()  # content 为真实需求描述
    prev = assess(standard, base)
    first = inherit_and_count(prev, prev, "userRole", False, standard=standard, previous_form=base, form=base)
    output = ModelOutput(structured={}, elements=[], intent=Intent(kind="chitchat"))
    result = process(output, base, {}, first, "userRole", base, "谢谢")
    assert result["structured"]["content"] == "客户经理每天需要查渠道报表和导出"
    # 引导话术 + 重问当前问题（attempts=1 用 L2 示例话术）
    assert result["reply"].startswith(CHITCHAT_GUIDE) and "可以这样写" in result["reply"]
    assert result["askedTarget"] == "userRole"
    assert next(e for e in result["elements"] if e["key"] == "userRole")["attempts"] == 1


def test_question_explains_current_field_once_without_penalty():
    """提问意图：用户问某要素是什么——给要素级解释（复用该要素提问话术），不按答错计数；
    解释的正是当前问题时，解释话术本身即追问，不重复问两遍。"""
    base = form()
    output = ModelOutput(structured={}, elements=[], intent=Intent(kind="question", target_key="userRole"))
    result = process(output, base, {}, [], "userRole", base, "目标用户是指什么？")
    assert result["askedTarget"] == "userRole"
    assert next(e for e in result["elements"] if e["key"] == "userRole")["attempts"] == 0
    assert result["reply"].startswith("「目标用户角色」") and result["reply"].count("给谁用") == 1
    assert "回到刚才的问题" not in result["reply"]


def test_question_about_other_field_bridges_back():
    """问的不是当前问题要素：先解释所问要素，再桥接回当前问题。"""
    base = form()
    output = ModelOutput(structured={}, elements=[], intent=Intent(kind="question", target_key="acceptanceCriteria"))
    result = process(output, base, {}, [], "userRole", base, "验收标准是什么意思？")
    assert result["reply"].startswith("「验收标准」") and "可检查的标准" in result["reply"]
    assert "回到刚才的问题" in result["reply"] and result["askedTarget"] == "userRole"


def test_question_without_target_falls_back():
    """模型没给出相关要素（与表单无关的问题）：兜底话术引导用户按自己理解说，AI 帮整理。"""
    base = form()
    output = ModelOutput(structured={}, elements=[], intent=Intent(kind="question"))
    result = process(output, base, {}, [], "userRole", base, "这个系统是谁开发的？")
    assert "我主要帮你把需求记清楚" in result["reply"]
    assert "回到刚才的问题" in result["reply"] and result["askedTarget"] == "userRole"


def test_question_cleans_echo_backfill():
    """问题②（2026-10-20 拍板）：纯提问「什么是需求标题？」被 prepare 误回填为 A8 底稿——
    提问分流与闲聊同口径清理，提问原文不作需求底稿留草稿随单提交。"""
    base = {**form(), "content": "什么是需求标题？"}
    output = ModelOutput(structured={}, elements=[], intent=Intent(kind="question"))
    result = process(output, base, {"content": "user"}, [], "userRole", form(), "什么是需求标题？")
    assert not result["structured"].get("content") and "content" not in result["fieldSources"]
    assert result["intent"] == "question"


def test_command_cleans_echo_backfill():
    """问题②推广：流程指令「提交吧」同理不作需求底稿；清理不影响提交门槛判定。"""
    base = {**acd_filled_form(), "content": "提交吧"}
    output = ModelOutput(structured={}, elements=[], intent=Intent(kind="command"))
    result = process(output, base, {"content": "user"}, [], None, acd_filled_form(), "提交吧")
    assert not result["structured"].get("content") and "content" not in result["fieldSources"]
    assert result["canSubmit"] is True and result["intent"] == "command"


def test_title_gap_skipped_to_next_real_gap():
    """标题转系统提取项（2026-10-20 拍板）：标题空缺时追问目标跳过标题，落在下一真实缺口（用户角色）。"""
    base = {key: value for key, value in form().items() if key != "title"}
    output = ModelOutput(structured={}, elements=[])
    result = process(output, base, {}, [], None, base, "继续")
    assert result["askedTarget"] == "userRole"


def test_title_blank_does_not_block_can_submit():
    """标题不占提交门槛（auto_fill，2026-10-20 拍板）：其余必填齐、标题空时仍可提交——
    提交前由 submit 整理链重拟/兜底，对话不再为标题发问。"""
    base = {key: value for key, value in b1_filled(acd_filled_form()).items() if key != "title"}
    output = ModelOutput(structured={}, elements=[])
    result = process(output, base, {}, [], None, base, "继续")
    assert result["canSubmit"] is True and result["askedTarget"] is None


def test_light_mode_title_exits_follow_up_sequence():
    """light 追问序列移除标题兜底位（2026-10-20 拍板）：期望效果已答后，标题空缺不追问，落紧急度。"""
    base = {"demandTypeCode": "TECH",
            "ext": {"mode": {"level": "light", "evidence": "小改动"}},
            "elements": {"D": {"acceptanceCriteria": "首页 logo 换成公司新版"}}}
    output = ModelOutput(structured={}, elements=[])
    result = process(output, base, {}, [], None, base, "继续")
    assert result["askedTarget"] == "urgency"


def test_command_ready_points_to_submit_button():
    """指令意图·必填已齐：指引点提交按钮，不叠加模式播报等任何前缀（「提交吧」配「改动面不小」文不对题）。"""
    output = ModelOutput(structured={}, elements=[], intent=Intent(kind="command"),
                         mode_signal=ModeSignalOutput(level="light", evidence="看着是小改动"))
    result = process(output, acd_filled_form(), {}, [], None, {}, "提交吧")
    assert result["canSubmit"] is True
    assert result["reply"] == "好的，信息都齐了，点下方「提交」按钮就能提报。"


def test_command_blocked_lists_missing_labels_and_continues():
    """指令意图·必填未齐：白话列出缺哪几项，并接续追问当前缺口。"""
    base = form()
    output = ModelOutput(structured={}, elements=[], intent=Intent(kind="command"))
    result = process(output, base, {}, [], "userRole", base, "提交吧")
    assert not result["canSubmit"]
    assert result["reply"].startswith("还差几项必填信息才能提交：")
    assert "「目标用户角色」" in result["reply"] and "「验收标准」" in result["reply"]
    assert result["askedTarget"] == "userRole" and "给谁用" in result["reply"]


def test_answer_is_default_and_counts_when_intent_absent():
    """向后兼容：模型未输出 intent 按 answer 处理——prev_target 被作答但未合格时照常计 attempts。"""
    base = form()
    prev = assess(get("TECH"), base)
    result = process(ModelOutput(structured={}, elements=[]), base, {}, prev, "userRole", base, "不知道")
    assert next(e for e in result["elements"] if e["key"] == "userRole")["attempts"] == 1


@pytest.mark.parametrize("raw,expected_kind,expected_target", [
    ('{"structured":{},"elements":[],"intent":{"kind":"supplement","targetKey":"useScenario"}}', "supplement", "useScenario"),
    ('{"structured":{},"elements":[],"intent":{"kind":"chitchat"}}', "chitchat", None),
    ('{"structured":{},"elements":[]}', "answer", None),                       # 未输出：按 answer
    ('{"structured":{},"elements":[],"intent":{"kind":"greeting"}}', "answer", None),  # 非法 kind：宽容按未输出
    ('{"structured":{},"elements":[],"intent":"chitchat"}', "answer", None),   # 结构畸形：宽容按未输出
    ('{"structured":{},"elements":[],"intent":{"kind":"question","targetKey":42}}', "question", None),  # targetKey 非字符串置空
])
def test_parse_intent_tolerant(raw, expected_kind, expected_target):
    output = parse_model_output(raw)
    assert (output.intent.kind if output.intent else "answer") == expected_kind
    assert (output.intent.target_key if output.intent else None) == expected_target


# ---- 对话外事件后的流程接续（2026-10-19 拍板问题②）：手改要素/附件回执后 resume_follow_up ----


def test_resume_follow_up_asks_next_gap():
    """手改后必填仍有缺口：追问下一项缺口（已填项不问），payload 结构对齐对话结果消息。"""
    standard = get("TECH")
    value = acd_filled_form()
    del value["elements"]["C"]["userRole"]
    follow = resume_follow_up(standard, value, None)
    assert follow["askedTarget"] == "userRole" and "给谁用" in follow["reply"]
    assert not follow["canSubmit"] and not follow["guidanceComplete"]
    assert follow["elements"] and follow["quickReplies"] == []


def test_resume_follow_up_all_filled_says_submittable():
    """手改把最后缺口补齐：给完成话术告知可以提交，不再追问。
    （填 B1 隔离「必问一次」治理型追问，2026-10-24 拍板）"""
    follow = resume_follow_up(get("TECH"), b1_filled(acd_filled_form()), None)
    assert follow["askedTarget"] is None
    assert follow["canSubmit"] and follow["guidanceComplete"]
    assert "可以提交" in follow["reply"]


def test_resume_follow_up_cleared_required_is_reasked():
    """手改清空必填项：规则层判 MISSING 自然被重问，不需要特殊分支。"""
    standard = get("TECH")
    value = acd_filled_form()
    value["elements"]["C"]["useScenario"] = ""
    follow = resume_follow_up(standard, value, None)
    assert follow["askedTarget"] == "useScenario"
    assert next(e for e in follow["elements"] if e["key"] == "useScenario")["status"] == "MISSING"


def test_resume_follow_up_inherits_attempts_without_counting():
    """attempts/SKIP 从上一轮对话快照继承但不 +1（prev_target=None）：手改不算「答错当前问题」。"""
    standard = get("TECH")
    value = acd_filled_form()
    del value["elements"]["C"]["userRole"]
    asked_once = inherit_and_count(assess(standard, value), assess(standard, value), "userRole", False,
                                   standard=standard, previous_form=value, form=value)
    previous = {"structured": acd_filled_form(), "elements": [e.model_dump(by_alias=True) for e in asked_once]}
    follow = resume_follow_up(standard, value, previous)
    assert next(e for e in follow["elements"] if e["key"] == "userRole")["attempts"] == 1
    # 追问额度照常生效：快照中 attempts 已满的问题不再被选为目标
    exhausted = [e.model_copy(update={"attempts": 2}) if e.key == "userRole" else e for e in asked_once]
    previous2 = {"structured": acd_filled_form(), "elements": [e.model_dump(by_alias=True) for e in exhausted]}
    assert resume_follow_up(standard, value, previous2)["askedTarget"] != "userRole"


def test_resume_follow_up_light_mode_minimal_gate():
    """light 模式接续同口径：只按最小集追问/放行，C/D 大片缺失不拦。"""
    standard = get("TECH")
    value = light_form(urgency="NORMAL")
    value["ext"] = {"mode": {"level": "light", "evidence": "换logo"}}
    follow = resume_follow_up(standard, value, None)
    assert follow["askedTarget"] == "acceptanceCriteria" and not follow["canSubmit"]
    complete = light_form(urgency="NORMAL", elements={"D": {"acceptanceCriteria": "首页顶部logo显示为新设计的蓝色版本"}})
    complete["ext"] = {"mode": {"level": "light", "evidence": "换logo"}}
    done = resume_follow_up(standard, complete, None)
    assert done["askedTarget"] is None and done["canSubmit"] and "可以提交" in done["reply"]


def test_resume_invites_plain_description_when_draft_blank():
    """无描述白话邀请（2026-10-19 拍板）：底稿空且未达门槛 → 一句话邀请，
    替代「请补充原始提报文本」的术语追问（截图案例：只手填了标题的场景）。"""
    standard = get("TECH")
    value = {"title": "修改系统名称", "demandTypeCode": "TECH", "urgency": "NORMAL", "elements": {}}
    follow = resume_follow_up(standard, value, None)
    assert follow["reply"] == DESC_INVITE
    assert follow["askedTarget"] == "content" and follow["quickReplies"] == []
    assert not follow["canSubmit"] and not follow["guidanceComplete"]


def test_resume_invite_skipped_when_submittable():
    """底稿空但必填已齐 → 不发邀请，直接完成话术（底稿由提交兜底回填，不打断用户）。"""
    standard = get("TECH")
    value = {**b1_filled(acd_filled_form()), "content": None}  # 填 B1 隔离必问一次（2026-10-24 拍板）
    follow = resume_follow_up(standard, value, None)
    assert follow["askedTarget"] is None and follow["canSubmit"] and "可以提交" in follow["reply"]


def test_resume_matl_content_still_required_and_asked():
    """MATL/TRAIN 维持现状：content 仍必填、空时走原追问（待独立助手重建），不发白话邀请。"""
    standard = get("MATL")
    follow = resume_follow_up(standard, {"demandTypeCode": "MATL"}, None)
    assert follow["reply"] != DESC_INVITE and follow["askedTarget"] is not None


def test_missing_required_beats_vague_quality():
    """先补"没有"再修"不好"（2026-10-23 拍板）：D 区验收有值但笼统（VAGUE）时，
    真空着（MISSING）的必填整体优先被问——图片解析/大段粘贴一次性填满 D 区长文本曾让
    验收质检抢在 4 个空必填前面；组内顺序不变：B 区沉底、紧急程度最后。"""
    standard = get("TECH")
    value = acd_filled_form()
    value["elements"]["D"]["acceptanceCriteria"] = "好用就行"  # VAGUE
    value["urgency"] = None  # MISSING
    # 非业务：紧急程度（MISSING）优先于验收质检（VAGUE），哪怕它排序沉底
    follow = resume_follow_up(standard, value, None)
    assert follow["askedTarget"] == "urgency"
    # B1 白话一问（2026-10-24 拍板，判型解耦）：B1 空缺的 MISSING 也优先于 D 区 VAGUE（不问判型直接问）
    business_value = acd_filled_form()
    business_value["ext"] = {"typeRecognition": {"business": 0.9, "user": 0.2, "function": 0.3}}
    business_value["elements"]["D"]["acceptanceCriteria"] = "好用就行"
    business_value["urgency"] = "NORMAL"
    follow_b = resume_follow_up(standard, business_value, None)
    assert follow_b["askedTarget"] == "businessGoal"
    # 全部 MISSING 问满放过（attempts 达上限）后才轮到 VAGUE 质检追问；
    # B1 治理型一问同样问过一次（attempts=1）即终结
    exhausted = [{"key": "urgency", "status": "MISSING", "attempts": standard.max_attempts},
                 {"key": "businessGoal", "status": "MISSING", "attempts": 1}]
    follow_v = resume_follow_up(standard, value, {"structured": value, "elements": exhausted})
    assert follow_v["askedTarget"] == "acceptanceCriteria"


def test_resume_counts_manual_attempts_and_quotes_reask():
    """手改计数+引述重问（2026-10-19 拍板）：手填的验收标准仍笼统——引原话+说差距地再问一次，
    记 1 次；再改仍不达标记满 2 次放过（不再选中），没碰的要素不记。
    2026-10-23 优先级拍板后：VAGUE 想被选中须 MISSING 先问满放过（先补"没有"再修"不好"）。"""
    standard = get("TECH")
    value = acd_filled_form()
    value["elements"]["D"]["acceptanceCriteria"] = "好用就行"
    value["urgency"] = None
    # 紧急度（MISSING）问满 2 次仍空着才轮到验收质检：构造 attempts 达上限的历史快照
    # （B1 治理型一问同样须已问过，2026-10-24 拍板：MISSING 整体优先于 VAGUE）；
    # 计数认"值有变化"——历史快照里的验收还是旧值（原合格文本），本轮手改成"好用就行"才记 1 次
    exhausted = [{"key": "urgency", "status": "MISSING", "attempts": standard.max_attempts},
                 {"key": "businessGoal", "status": "MISSING", "attempts": 1}]
    first = resume_follow_up(standard, value, {"structured": acd_filled_form(), "elements": exhausted},
                             changed_keys={"acceptanceCriteria"})
    assert first["askedTarget"] == "acceptanceCriteria"
    assert first["reply"].startswith("你填的「验收标准」『好用就行』我记下了，不过")
    assert next(e for e in first["elements"] if e["key"] == "acceptanceCriteria")["attempts"] == 1
    # 第二次手改仍不达标：记满 2 次放过；紧急度与验收均问满，无目标可问（不纠缠）
    previous_form = deepcopy(value)
    value["elements"]["D"]["acceptanceCriteria"] = "好用"
    previous = {"structured": previous_form, "elements": first["elements"]}
    second = resume_follow_up(standard, value, previous, changed_keys={"acceptanceCriteria"})
    assert next(e for e in second["elements"] if e["key"] == "acceptanceCriteria")["attempts"] == 2
    assert second["askedTarget"] is None


def test_resume_untouched_fields_not_counted():
    """手改计数只针对本轮碰过的要素：改了别的字段，笼统的验收标准不记次数。"""
    standard = get("TECH")
    value = acd_filled_form()
    value["elements"]["D"]["acceptanceCriteria"] = "好用就行"
    follow = resume_follow_up(standard, value, None, changed_keys={"userRole"})
    assert next(e for e in follow["elements"] if e["key"] == "acceptanceCriteria")["attempts"] == 0


def test_light_gate_not_blocked_by_missing_content():
    """light 最小集移出 content（2026-10-19 拍板）：底稿空不拦提交门槛。"""
    standard = get("TECH")
    value = light_form(urgency="NORMAL", content=None,
                       elements={"D": {"acceptanceCriteria": "首页顶部logo显示为新设计的蓝色版本"}})
    value["ext"] = {"mode": {"level": "light", "evidence": "换logo"}}
    follow = resume_follow_up(standard, value, None)
    assert follow["canSubmit"] and follow["guidanceComplete"]
