"""硬字段格式校验与软质量判定分开；所有渠道使用同一标准。"""
import math
import re
from datetime import date
from typing import Any

from app.standards.schema import Element, Standard


def blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def get_value(form: dict, path: str):
    if path.startswith("ext."):
        return (form.get("ext") or {}).get(path[4:])
    return form.get(path)


def set_value(form: dict, path: str, value: Any):
    if path.startswith("ext."):
        form.setdefault("ext", {})[path[4:]] = value
    else:
        form[path] = value


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
    """白名单过滤不接受身份/编号/状态/质量；允许显式清空。"""
    if not isinstance(form, dict) or ("ext" in form and not isinstance(form["ext"], (dict, type(None)))):
        raise ValueError("表单/ext必须为对象")
    if standard is None:
        from app.standards.loader import get
        known = get("TECH")
        fields = [f for f in known.fields if not f.field_path.startswith("ext.")]
    else:
        fields = standard.fields
    result = {}
    for field in fields:
        source = (form.get("ext") or {}) if field.field_path.startswith("ext.") else form
        key = field.field_path.split(".")[-1]
        if key not in source:
            continue
        value = source[key]
        if blank(value):
            value = field.default if field.default is not None else None
        error = field_error(field, value)
        if validate and error:
            raise ValueError(error)
        set_value(result, field.field_path, value)
    return result


def schema_errors(standard: Standard | None, form: dict, *, required: bool = False) -> list[str]:
    if standard is None:
        return ["需求类型未填写"] if required else []
    errors = []
    for field in standard.fields:
        value = get_value(form, field.field_path)
        if required and field.required and blank(value):
            errors.append(f"{field.label}未填写")
        error = field_error(field, value)
        if error:
            errors.append(error)
    return errors


def assess(standard: Standard, form: dict):
    from app.agent.schemas import ElementStatus
    result = []
    for field in standard.elements:
        value = get_value(form, field.field_path)
        status, note = "OK", ""
        if blank(value):
            status, note = "MISSING", "未填写"
        elif field_error(field, value):
            status, note = "VAGUE", field_error(field, value)
        elif field.kind == "text":
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
