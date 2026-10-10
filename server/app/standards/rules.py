"""硬字段格式校验与软质量判定分开；所有渠道使用同一标准。"""
import math
import re
from datetime import date
from typing import Any

from app.standards.schema import Element, Standard


def blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, dict)):
        return not value
    return False


def _container(form: dict, path: str) -> tuple[dict, str]:
    """把 ext.key / elements.区.key 解析到直接父容器与末段 key；顶层路径原样返回。"""
    parts = path.split(".")
    source = form
    for part in parts[:-1]:
        if not isinstance(source, dict):
            return {}, parts[-1]
        source = source.get(part)
    return (source if isinstance(source, dict) else {}), parts[-1]


def get_value(form: dict, path: str):
    source, key = _container(form, path)
    return source.get(key)


def set_value(form: dict, path: str, value: Any):
    parts = path.split(".")
    source = form
    for part in parts[:-1]:
        child = source.get(part)
        if not isinstance(child, dict):
            child = {}
            source[part] = child
        source = child
    source[parts[-1]] = value


def field_error(field: Element, value: Any) -> str | None:
    if blank(value):
        return None
    if field.kind in {"text", "enum", "date"} and not isinstance(value, str):
        return f"{field.label}必须为文本"
    if field.kind == "text":
        limit = field.rule.max_len or (60 if field.key == "title" else 20000)
        if len(value) > limit:
            return f"{field.label}不得超过{limit}字"
    if field.kind == "enum" and value not in field.options:
        return f"{field.label}取值不在选项内"
    if field.kind == "number" and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 1 or value > 99999):
        return f"{field.label}必须为1至99999的有效数值"
    if field.kind == "list" and not isinstance(value, list):
        return f"{field.label}必须为列表"
    if field.kind == "list" and any(not isinstance(item, (str, int, float)) or isinstance(item, bool) for item in value):
        return f"{field.label}列表项必须为文本或数值"
    if field.kind == "date":
        try:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                raise ValueError
            parsed = date.fromisoformat(value)
            if parsed.year < 1000:
                raise ValueError
        except ValueError:
            return f"{field.label}日期必须为YYYY-MM-DD"
    return None


def filter_form(standard: Standard | None, form: dict, *, validate: bool = True) -> dict:
    """白名单过滤不接受身份/编号/状态/质量；允许显式清空。system 快照要素不接受表单输入。"""
    if not isinstance(form, dict) or ("ext" in form and not isinstance(form["ext"], (dict, type(None)))):
        raise ValueError("表单/ext必须为对象")
    if "elements" in form and not isinstance(form["elements"], (dict, type(None))):
        raise ValueError("表单/elements必须为对象")
    if standard is None:
        from app.standards.loader import get
        known = get("TECH")
        fields = [f for f in known.fields if "." not in f.field_path]
    else:
        fields = standard.fields
    result = {}
    for field in fields:
        if field.system:
            continue
        source, key = _container(form, field.field_path)
        if key not in source:
            continue
        value = source[key]
        if blank(value):
            value = field.default if field.default is not None else None
        # 枚举容错：模型/前端可能回传中文选项名（用户点选快捷回复后模型未映射 code），按选项标签归一为 code
        if field.kind == "enum" and isinstance(value, str) and value not in field.options:
            value = next((code for code, label in field.options.items() if label == value), value)
        error = field_error(field, value)
        if error:
            if validate:
                raise ValueError(error)
            # 容错：模型输出的非法值（如期望交付时间写"本周"）丢弃该值，而不是让整轮对话报错
            value = None
        set_value(result, field.field_path, value)
    return result


def business_confirmed(recognition: dict | None) -> bool:
    """判型结果是否按业务需求门槛生效（PRD §4.3；2026-10-10 口径：业务占优才激活）。
    business 须 ≥0.5 且高于 user/function 两档——防止「辅助管理层决策」类收益表述把
    function 为主的日常功能需求误触发 B 区四件套追问；用户确认/改判定稿优先于置信度。"""
    if not recognition:
        return False
    confirmed = recognition.get("confirmed")
    if confirmed is not None:
        return confirmed == "business"
    business = float(recognition.get("business") or 0)
    if business < 0.5:
        return False
    return business > max(float(recognition.get(layer) or 0) for layer in ("user", "function"))


def schema_errors(standard: Standard | None, form: dict, *, required: bool = False, active_zones: set[str] | None = None) -> list[str]:
    """required=True 时按必填门槛校验；active_zones 限定必填生效的区（None=全部区生效，用于 B 区判型条件必填）。"""
    if standard is None:
        return ["需求类型未填写"] if required else []
    errors = []
    for field in standard.fields:
        if field.system:
            continue
        value = get_value(form, field.field_path)
        if required and field.required and blank(value):
            if active_zones is None or field.zone is None or field.zone in active_zones:
                errors.append(f"{field.label}未填写")
        error = field_error(field, value)
        if error:
            errors.append(error)
    return errors


def assess(standard: Standard, form: dict):
    from app.agent.schemas import ElementStatus
    result = []
    for field in standard.elements:
        if field.system:
            continue
        value = get_value(form, field.field_path)
        status, note = "OK", ""
        if blank(value):
            status, note = "MISSING", "未填写"
        elif field_error(field, value):
            status, note = "VAGUE", field_error(field, value)
        elif field.kind == "text" and field.key != "content":
            # content（原始提报文本）是系统原样保留的用户原话底稿（FR-02/D6），只在首条消息时
            # 原样回填、之后不再改写。因此：非空即 OK，不做歧义词/长度/可量化等任何软质量降级，
            # 也永不作为追问目标——否则原话含「方便/尽快」等正常口语、或首句较短时，会冒出
            # "请补充原始提报文本"这类用户无法回答、且后续补充也改不了原话的死循环追问。
            # 信息是否充分由可继续更新的场景/痛点/验收等要素承载；空值仍判 MISSING（提交必填拦截）。
            text = value.strip()
            rule = field.rule
            if any(word in text for word in standard.vague_words):
                status, note = "VAGUE", "含歧义词"
            elif rule.min_len is not None and len(text) < rule.min_len:
                status, note = "VAGUE", field.vague_hint
            elif rule.max_len is not None and len(text) > rule.max_len:
                status, note = "VAGUE", field.vague_hint
            elif rule.any_of and not any(word in text for word in rule.any_of):
                status, note = "VAGUE", field.vague_hint
            elif rule.any_of_regex and not any(re.search(pattern, text) for pattern in rule.any_of_regex):
                status, note = "VAGUE", field.vague_hint
        result.append(ElementStatus(key=field.key, label=field.label, status=status, note=note or ""))
    return result
