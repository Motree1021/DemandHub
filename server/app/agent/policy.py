"""模型只能抽取判质；来源、目标、话术与完成标记由纯函数决定。"""
import re
from copy import deepcopy

from app.agent.schemas import ElementStatus, ModelOutput, TypeSignalsOutput
from app.standards import loader as standard_loader
from app.standards.rules import (
    assess,
    blank,
    business_confirmed,
    filter_form,
    get_value,
    schema_errors,
    set_value,
)
from app.standards.schema import Standard


def _numbers(text) -> set:
    """文本中的全部数字（含小数），用于 FR-08 量化事实溯源。"""
    return set(re.findall(r"\d+(?:\.\d+)?", text if isinstance(text, str) else ""))


def merge_structured(model_structured: dict, form: dict, field_sources: dict, standard: Standard | None = None, *, standards=None, grounded_text: str | None = None):
    result = deepcopy(form)
    sources = dict(field_sources)
    known = standards["TECH"] if standards else standard_loader.get("TECH")
    kinds = {f.field_path: f.kind for f in known.fields}
    for key, value in model_structured.items():
        if key == "ext":
            if not isinstance(value, dict):
                raise ValueError("模型 ext 必须为对象")
            # overview 是详情页"需求概述"四段式摘要（dict[str,str]），畸形输出整轮拒绝
            overview = value.get("overview")
            if overview is not None and (not isinstance(overview, dict) or any(not isinstance(v, str) for v in overview.values())):
                raise ValueError("模型 ext.overview 必须为字符串字典")
            items = [("ext." + k, v) for k, v in value.items()]
        elif key == "elements":
            if not isinstance(value, dict) or any(not isinstance(v, (dict, type(None))) for v in value.values()):
                raise ValueError("模型 elements 必须为按区嵌套的对象")
            items = []
            for zone, values in value.items():
                for k, v in (values or {}).items():
                    path = f"elements.{zone}.{k}"
                    # 模型常把 zone=A 而 field_path 在顶层的要素（urgency/expectDeliveryAt/title/content 等）
                    # 误嵌进 elements.A，此处归位到顶层；归位后来源保护与格式校验照常生效
                    if path not in kinds and "." not in k and k in kinds:
                        path = k
                    items.append((path, v))
        else:
            items = [(key, value)]
        for path, item in items:
            kind = kinds.get(path)
            # 非 list 要素输出数组/对象属畸形（空集合的新语义是"未输出"，仅 list 要素合法）
            if kind is not None and kind != "list" and isinstance(item, (list, dict)):
                raise ValueError(f"模型输出{path}类型错误")
            if sources.get(path) == "user" or blank(item):
                continue
            # FR-08 提炼约束：agent 文本中的数字必须可溯源到本轮消息或旧值，含新增数字视为编造事实，整值过滤
            if grounded_text is not None and kind == "text" and isinstance(item, str):
                grounded = _numbers(grounded_text) | _numbers(get_value(result, path))
                if not _numbers(item) <= grounded:
                    continue
            set_value(result, path, item)
            sources[path] = "agent"
    type_code = result.get("demandTypeCode")
    if not blank(type_code):
        from app.standards.rules import field_error
        type_field = next(f for f in known.elements if f.key == "demandTypeCode")
        error = field_error(type_field, type_code)
        if error:
            raise ValueError(error)
    selected = (standards[type_code] if standards else standard_loader.get(type_code)) if type_code else None
    normalization_standard = selected or known.model_copy(update={"elements": [e for e in known.elements if "." not in e.field_path], "optional_fields": [], "subtype_fields": {}})
    # BR-T11 实例切分建议：一期仅打标 ext.pendingSplits（list 才合法），用户确认后分路留 V2
    pending_splits = (result.get("ext") or {}).get("pendingSplits")
    old_pending = (form.get("ext") or {}).get("pendingSplits")
    # ext.overview 需求概述（四段式摘要）非五区要素，filter_form 会丢弃，需与 pendingSplits 同样保留
    overview = (result.get("ext") or {}).get("overview")
    old_overview = (form.get("ext") or {}).get("overview")
    # 容错模式：模型输出的单个非法值（如日期写"本周"）丢弃而非整轮报错；demandTypeCode 已在上方单独严控
    result = filter_form(normalization_standard, result, validate=False)
    if isinstance(pending_splits, list) and pending_splits:
        result.setdefault("ext", {})["pendingSplits"] = pending_splits
    if isinstance(overview, dict) and overview:
        result.setdefault("ext", {})["overview"] = overview
    allowed = {f.field_path for f in normalization_standard.fields}
    sources = {k: v for k, v in sources.items() if k in allowed}
    if "pendingSplits" in (result.get("ext") or {}):
        sources["ext.pendingSplits"] = field_sources.get("ext.pendingSplits") if pending_splits == old_pending else "agent"
    if "overview" in (result.get("ext") or {}):
        sources["ext.overview"] = field_sources.get("ext.overview") if overview == old_overview else "agent"
    return result, sources, selected


def merge_type_signals(signals: TypeSignalsOutput | None, form: dict) -> dict | None:
    """模型判型票与既有 ext.typeRecognition 合并：置信度取历史最高，confirmed（用户定稿）不被模型覆盖。"""
    prev = (form.get("ext") or {}).get("typeRecognition") or {}
    if signals is None:
        return prev or None
    result = {"confirmed": prev.get("confirmed")}
    evidence = dict(prev.get("evidence") or {})
    for layer in ("business", "user", "function"):
        vote = getattr(signals, layer)
        result[layer] = round(max(float(prev.get(layer) or 0), vote.confidence), 4)
        if vote.evidence:
            evidence[layer] = vote.evidence
    result["evidence"] = evidence
    return result


def detect_granularity(standard: Standard, form: dict, message: str) -> dict | None:
    """BR-T13/FR-10 粒度治理：关键词命中且对应区未填时才提示；收敛标准统一为可验证/可追踪/可独立受理。"""
    granularity = standard.granularity
    if granularity is None:
        return None
    text = "。".join([message or "", str(form.get("title") or ""), str(form.get("content") or "")])
    c_filled = any(not blank(get_value(form, f"elements.C.{key}")) for key in ("userRole", "useScenario"))
    if any(keyword in text for keyword in granularity.too_narrow.keywords) and not c_filled:
        return {"level": "too_narrow", "hint": granularity.too_narrow.hint, "converge": granularity.converge}
    d_filled = any(not blank(get_value(form, f"elements.D.{key}")) for key in ("functionDescription", "inputOutput"))
    if any(keyword in text for keyword in granularity.too_broad.keywords) and not d_filled:
        return {"level": "too_broad", "hint": granularity.too_broad.hint, "converge": granularity.converge}
    return None


def impact_hints(previous_form: dict, merged: dict) -> list[str]:
    """FR-06 影响分析：已填的 B 区业务要素被修改时，提示 C/D 区可能需联动调整。"""
    for key in ("businessGoal", "businessBackground", "businessValue"):
        path = f"elements.B.{key}"
        old, new = get_value(previous_form, path), get_value(merged, path)
        if not blank(old) and old != new:
            return ["你前面说的目标/背景/价值有调整，后面「给谁用、做什么」这些内容可能也要跟着改，请确认一下。"]
    return []


def complete_elements(standard: Standard, form: dict, model_elements: list[ElementStatus]):
    allowed = {element.key for element in standard.elements}
    keys = [element.key for element in model_elements]
    if len(keys) != len(set(keys)) or not set(keys) <= allowed:
        raise ValueError("模型质量要素不属于当前标准或重复")
    model = {element.key: element for element in model_elements}
    result = []
    for rule in assess(standard, form):
        item = model.get(rule.key)
        # 状态以规则层为准：规则合格/缺失均不被模型票改写。模型对已有有效值报 MISSING/VAGUE 多为自相矛盾
        # （值往往就是模型自己 structured 写入的），一旦降级已填字段会被反复追问。
        # 仅当规则判 VAGUE（有值但质量存疑）且无硬性格式错误时，模型票生效：OK 抬升确认，VAGUE 补充质量 note。
        if item is None or item.status == "MISSING" or rule.status != "VAGUE":
            final = rule
        elif schema_errors_for_key(standard, form, rule.key):
            final = rule
        else:
            final = rule.model_copy(update={"status": item.status, "note": item.note})
        result.append(final)
    return result


def schema_errors_for_key(standard, form, key):
    from app.standards.rules import field_error
    element = next(f for f in standard.elements if f.key == key)
    return field_error(element, get_value(form, element.field_path))


def inherit_and_count(prev, curr, prev_target, said_skip, *, standard, previous_form, form):
    previous = {e.key: e for e in prev}
    fields = {e.key: e for e in standard.elements}
    output = []
    for element in curr:
        old = previous.get(element.key)
        changed = get_value(previous_form, fields[element.key].field_path) != get_value(form, fields[element.key].field_path)
        attempts = old.attempts if old else 0
        status, note = element.status, element.note
        if old and old.status == "SKIP" and not changed:
            status, note = "SKIP", "用户选择后续补充"
        elif said_skip and element.key == prev_target and not fields[element.key].required and status != "OK":
            status, note = "SKIP", "用户选择后续补充"
        elif element.key == prev_target and status != "OK":
            attempts = min(standard.max_attempts, attempts + 1)
        if status == "OK":
            attempts = 0
        output.append(element.model_copy(update={"status": status, "note": note, "attempts": attempts}))
    return output


def compute_missing(standard, form):
    return [e.key for e in standard.elements if e.required and not e.system and blank(get_value(form, e.field_path))]


def pick_follow_up(standard, elements, *, business: bool = False):
    """选下一个追问目标。

    追问顺序：A/C/D 必填先问完（用户先补"给谁用、什么场景、痛点、验收"等具体信息），
    B 区业务要素排最后；且 B 区仅在判型为业务需求（business=True）时才追问，
    日常功能需求完全不问 B 区（与提交门槛 active_zones 口径一致）。
    """
    by_key = {element.key: element for element in elements}
    field_of = {element.key: element for element in standard.elements}
    required = [e.key for e in standard.elements if e.required and not e.system]

    def eligible(key):
        field = field_of.get(key)
        if field is None:
            return False
        if field.zone == "B" and not business:
            return False
        element = by_key.get(key)
        return element is not None and element.status not in {"OK", "SKIP"} and element.attempts < standard.max_attempts

    # 稳定排序：B 区沉底，其余（A/C/D 及 MATL/TRAIN 无分区要素）保持 yaml 原顺序在前
    ordered = sorted(required, key=lambda k: 1 if field_of[k].zone == "B" else 0)
    for key in ordered + standard.follow_up_order:
        if eligible(key):
            return by_key[key]
    return None


def user_said_skip(standard, text):
    normalized = re.sub(r"[\s，。！？!?,；;]+", "", text).strip()
    # 跳过必须是整句肯定表达，否定/引用/包含业务内容不算意图。
    return any(normalized in {phrase, "我" + phrase, "请" + phrase, "这项" + phrase, "这个" + phrase, phrase + "吧", "我选择" + phrase} for phrase in standard.skip_phrases)


def quick_replies(standard, target):
    if target is None:
        return []
    field = next(e for e in standard.elements if e.key == target.key)
    result = list(field.options.values()) if field.kind == "enum" else []
    if target.attempts >= 1 and not field.required:
        result.append("后续补充")
    return result


def anchored_template(standard, field, form):
    """首次追问锚定（2026-10-10 用户拍板）：引用已填的关联要素组织问句——
    B1 业务目标←C2 用户目标（上下游因果）、B4 干系人←C1 目标用户（受益方可由使用者推导），
    关联要素为空或未配置时返回空串，回落到普通追问模板。"""
    if not field.ask_anchor or not field.anchor_key:
        return ""
    anchor_field = next((e for e in standard.elements if e.key == field.anchor_key), None)
    if anchor_field is None:
        return ""
    anchor_value = str(get_value(form, anchor_field.field_path) or "").strip()
    if not anchor_value:
        return ""
    snippet = anchor_value[:20] + ("…" if len(anchor_value) > 20 else "")
    return field.ask_anchor.replace("{anchor}", snippet)


def reply_for(standard, target, form):
    if target is None:
        # 必填已齐、引导结束：选填项的 VAGUE/MISSING 状态会留在要素记录里供审核参考，用白话告知而非"质量缺口"术语
        return "都记好了，请核对一下表单。该填的都齐了，可以提交。没填或不太完整的可选项会在表单里标出来，不影响提交，以后能补；产品经理调研后也可以补。" if not schema_errors(standard, form, required=True) else "我这边问得差不多了。请在下方表单里把标红星※的必填项补齐后提交。"
    field = next(e for e in standard.elements if e.key == target.key)
    value = str(get_value(form, field.field_path) or "")
    snippet = value[:20] + ("…" if len(value) > 20 else "")
    if target.attempts >= 1:
        template = field.ask_l2 or field.ask_l1 or field.ask_missing
    else:
        template = anchored_template(standard, field, form) or (field.ask_missing or field.ask_l1 if target.status == "MISSING" else field.ask_l1 or field.ask_missing)
    template = template or f"请补充{field.label}，以便把需求记录清楚。"
    reply = template.replace("{snippet}", snippet)
    if target.attempts >= 1 and not field.required:
        reply += " 也可以说“后续补充”。"
    return reply


def process(output: ModelOutput, form: dict, sources: dict, prev: list[ElementStatus], prev_target: str | None, previous_form: dict, text: str, *, standards=None):
    merged, field_sources, selected = merge_structured(output.structured, form, sources, standards=standards, grounded_text=text)
    # 未定类型仍使用共用三个质量字段，不暴露 TECH 扩展要素。
    standard = selected or (standards["MATL"] if standards else standard_loader.get("MATL"))
    # FR-01/FR-03 判型合并：confirmed（用户定稿）不被模型覆盖，模型票只更新置信度与依据
    recognition = merge_type_signals(output.type_signals, form)
    if recognition:
        merged.setdefault("ext", {})["typeRecognition"] = recognition
        prev_confirmed = ((form.get("ext") or {}).get("typeRecognition") or {}).get("confirmed")
        field_sources["ext.typeRecognition"] = "user" if prev_confirmed is not None else "agent"
    curr = complete_elements(standard, merged, output.elements)
    curr = inherit_and_count(prev, curr, prev_target, user_said_skip(standard, text), standard=standard, previous_form=previous_form, form=merged)
    # B 区必填按判型门槛生效（PRD §4.3、FR-03 分支）：业务需求全量四区，否则 A/C/D
    is_business = business_confirmed(recognition)
    # 追问顺序与提交门槛共用同一判型口径：业务需求才追问 B 区，且 A/C/D 先问完再问 B
    target = pick_follow_up(standard, curr, business=is_business)
    active_zones = {"A", "C", "D"} | ({"B"} if is_business else set())
    can_submit = selected is not None and not schema_errors(selected, merged, required=True, active_zones=active_zones)
    granularity = detect_granularity(standard, merged, text)
    impacts = impact_hints(previous_form, merged)
    reply = reply_for(standard, target, merged)
    if impacts:
        reply = " ".join(impacts) + " " + reply
    if granularity:
        reply = granularity["hint"] + " " + reply
    return {
        "structured": merged, "fieldSources": field_sources,
        "missing": compute_missing(standard, merged), "elements": [e.model_dump(by_alias=True) for e in curr],
        "askedTarget": target.key if target else None, "canSubmit": can_submit, "ready": can_submit,
        "guidanceComplete": target is None, "qualityComplete": all(e.status == "OK" for e in curr),
        "quickReplies": quick_replies(standard, target), "reply": reply,
        "typeRecognition": recognition, "granularityHint": granularity, "impactHints": impacts,
    }
