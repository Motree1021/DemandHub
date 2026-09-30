"""模型只能抽取判质；来源、目标、话术与完成标记由纯函数决定。"""
import re
from copy import deepcopy

from app.agent.schemas import ElementStatus, ModelOutput
from app.standards import loader as standard_loader
from app.standards.rules import assess, blank, filter_form, get_value, schema_errors, set_value
from app.standards.schema import Standard


def merge_structured(model_structured: dict, form: dict, field_sources: dict, standard: Standard | None = None, *, standards=None):
    result = deepcopy(form)
    sources = dict(field_sources)
    for key, value in model_structured.items():
        if key == "ext":
            if not isinstance(value, dict):
                raise ValueError("模型 ext 必须为对象")
            items = [("ext." + k, v) for k, v in value.items()]
        else:
            items = [(key, value)]
        for path, item in items:
            if sources.get(path) == "user" or blank(item):
                continue
            set_value(result, path, item)
            sources[path] = "agent"
    known = standards["TECH"] if standards else standard_loader.get("TECH")
    type_code = result.get("demandTypeCode")
    if not blank(type_code):
        from app.standards.rules import field_error
        type_field = next(f for f in known.elements if f.key == "demandTypeCode")
        error = field_error(type_field, type_code)
        if error:
            raise ValueError(error)
    selected = (standards[type_code] if standards else standard_loader.get(type_code)) if type_code else None
    normalization_standard = selected or known.model_copy(update={"elements": [e for e in known.elements if not e.field_path.startswith("ext.")], "optional_fields": [], "subtype_fields": {}})
    result = filter_form(normalization_standard, result)
    allowed = {f.field_path for f in normalization_standard.fields}
    sources = {k: v for k, v in sources.items() if k in allowed}
    return result, sources, selected


def complete_elements(standard: Standard, form: dict, model_elements: list[ElementStatus]):
    allowed = {element.key for element in standard.elements}
    keys = [element.key for element in model_elements]
    if len(keys) != len(set(keys)) or not set(keys) <= allowed:
        raise ValueError("模型质量要素不属于当前标准或重复")
    model = {element.key: element for element in model_elements}
    result = []
    for rule in assess(standard, form):
        item = model.get(rule.key)
        if item is None or rule.status == "MISSING":
            final = rule
        elif item.status == "MISSING":
            final = rule.model_copy(update={"status": "VAGUE", "note": "已填写，需进一步确认"})
        elif rule.status == "VAGUE" and schema_errors_for_key(standard, form, rule.key):
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
    return [e.key for e in standard.elements if e.required and blank(get_value(form, e.field_path))]


def pick_follow_up(standard, elements):
    by_key = {element.key: element for element in elements}
    required = [e.key for e in standard.elements if e.required]
    for key in required + standard.follow_up_order:
        element = by_key[key]
        if element.status not in {"OK", "SKIP"} and element.attempts < standard.max_attempts:
            return element
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


def reply_for(standard, target, form):
    if target is None:
        return "已记下当前需求，请核对表单。可以提交，质量缺口仍会保留在记录中。" if not schema_errors(standard, form, required=True) else "当前引导已结束，请在表单中补齐必填内容后提交。"
    field = next(e for e in standard.elements if e.key == target.key)
    value = str(get_value(form, field.field_path) or "")
    snippet = value[:20] + ("…" if len(value) > 20 else "")
    if target.attempts >= 1:
        template = field.ask_l2 or field.ask_l1 or field.ask_missing
    elif target.status == "MISSING":
        template = field.ask_missing or field.ask_l1
    else:
        template = field.ask_l1 or field.ask_missing
    template = template or f"请补充{field.label}，以便把需求记录清楚。"
    reply = template.replace("{snippet}", snippet)
    if target.attempts >= 1 and not field.required:
        reply += " 也可以说“后续补充”。"
    return reply


def process(output: ModelOutput, form: dict, sources: dict, prev: list[ElementStatus], prev_target: str | None, previous_form: dict, text: str, *, standards=None):
    merged, field_sources, selected = merge_structured(output.structured, form, sources, standards=standards)
    # 未定类型仍使用共用三个质量字段，不暴露 TECH 扩展要素。
    standard = selected or (standards["MATL"] if standards else standard_loader.get("MATL"))
    curr = complete_elements(standard, merged, output.elements)
    curr = inherit_and_count(prev, curr, prev_target, user_said_skip(standard, text), standard=standard, previous_form=previous_form, form=merged)
    target = pick_follow_up(standard, curr)
    can_submit = selected is not None and not schema_errors(selected, merged, required=True)
    return {
        "structured": merged, "fieldSources": field_sources,
        "missing": compute_missing(standard, merged), "elements": [e.model_dump(by_alias=True) for e in curr],
        "askedTarget": target.key if target else None, "canSubmit": can_submit, "ready": can_submit,
        "guidanceComplete": target is None, "qualityComplete": all(e.status == "OK" for e in curr),
        "quickReplies": quick_replies(standard, target), "reply": reply_for(standard, target, merged),
    }
