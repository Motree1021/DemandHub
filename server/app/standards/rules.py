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


def field_error(field: Element, value: Any, *, today: date | None = None) -> str | None:
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
                return f"{field.label}请点日历选择，或写成「2026-11-20」这样的日期"
            parsed = date.fromisoformat(value)
            if parsed.year < 1000:
                return f"{field.label}请点日历选择，或写成「2026-11-20」这样的日期"
            # 期望交付时间语义：交付只能安排在今天或以后。模型曾把省略年份的"10/30"错补成
            # 2015-10-30（格式合法但明显错误），过去日期即便格式合法也判无效，促使追问/丢弃
            if field.key == "expectDeliveryAt" and parsed < (today or date.today()):
                return f"{field.label}不能早于今天"
        except ValueError:
            return f"{field.label}请点日历选择，或写成「2026-11-20」这样的日期"
    return None


def filter_form(standard: Standard | None, form: dict, *, validate: bool = True, today: date | None = None) -> dict:
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
        error = field_error(field, value, today=today)
        if error:
            if validate:
                raise ValueError(error)
            # 容错：模型输出的非法值（如期望交付时间写"本周"）丢弃该值，而不是让整轮对话报错
            value = None
        set_value(result, field.field_path, value)
    return result


def business_confirmed(recognition: dict | None) -> bool:
    """判型是否归为业务需求（2026-10-24 拍板层级倾斜 business>user>function + 档位对齐）：
    business 票 ≥0.7 即判业务需求——判线贴在主句级起点，从句级信号（封顶 0.6）天然不过线，
    不再要求严格占优；三票是「证据强度」而非互斥概率，归类按最高层级走；判型与 B 区解耦后仅作归类展示。
    用户确认/改判定稿优先于置信度。"""
    if not recognition:
        return False
    confirmed = recognition.get("confirmed")
    if confirmed is not None:
        return confirmed == "business"
    return float(recognition.get("business") or 0) >= 0.7


B1_BUSINESS_FLOOR = 0.7  # B1 落库翻转时 business 票的补足底值（= 业务判线，主句级起点，与 business_confirmed 同档）


def promote_business_on_b1(recognition: dict | None, before: dict, after: dict) -> dict | None:
    """B1 落库即判业务（2026-10-24 拍板）：B1 业务目标「从空变为有值」（用户亲口答出或手填组织理由）——
    硬证据优先于模型软分数，business 票补足到业务门槛 0.7，依据为空时回填 B1 原文。
    路径分流（2026-10-26 拍板）：补票升级打 b1Backfill 标记——带标记的业务需求为「升级型」，
    B2~B4 放行提交、受理侧兜底补录；不带标记的业务判型为「原生型」，B1~B4 动态必填。
    幂等：business 已 ≥0.7、B1 非「空→有」变化时原样返回；confirmed 人工定稿优先，定稿后不动。"""
    prev_b1 = ((before.get("elements") or {}).get("B") or {}).get("businessGoal")
    curr_b1 = ((after.get("elements") or {}).get("B") or {}).get("businessGoal")
    if str(prev_b1 or "").strip() or not str(curr_b1 or "").strip():
        return recognition
    if recognition is not None and recognition.get("confirmed") is not None:
        return recognition
    result = dict(recognition) if recognition else {}
    if float(result.get("business") or 0) >= B1_BUSINESS_FLOOR:
        return recognition
    result["business"] = B1_BUSINESS_FLOOR
    result["b1Backfill"] = True
    evidence = dict(result.get("evidence") or {})
    if not evidence.get("business"):
        evidence["business"] = str(curr_b1).strip()
    result["evidence"] = evidence
    return result


# 微需求快速通道（2026-10-11 方案②）：light 最小必填集 = A1 标题 + A6 紧急度 + 期望效果（写 D8），
# A2 需求类型为结构性默认值随行；C/D 其余要素不追问不标星不拦截。换 logo/调样式/文案微调这类需求
# 填不满 12 项模板（C 区用户故事、D 区输入输出/量化验收会语义性误伤），轻量口径只保受理最小信息。
# 2026-10-19 拍板：A8 原话底稿移出最小集——系统提取项（回填/兜底归系统），不作为用户提供项
LIGHT_REQUIRED_KEYS = {"title", "demandTypeCode", "urgency", "acceptanceCriteria"}


def demand_mode(form: dict) -> str:
    """ext.mode.level：light=轻量提报 / standard=常规（缺省 standard，兼容未判定的存量草稿）。"""
    mode = (form.get("ext") or {}).get("mode")
    return "light" if isinstance(mode, dict) and mode.get("level") == "light" else "standard"


# B 区必填路径分流（2026-10-26 拍板，修订 10-24「判型与必填全解耦」口径）：
# 原生业务需求（模型判型票自然涨过 0.7，或人工定稿 business）B1~B4 动态必填、缺了不能提交；
# 升级业务需求（B1 答出后规则补票过线，带 b1Backfill 标记）放行提交，B2~B4 由受理侧兜底补录。
# 判型只涨不跌 → 门槛只加不减，无反复；轻量（微需求）链路全程不启用 B 区。
B_ZONE_DYNAMIC_KEYS = frozenset({"businessGoal", "businessBackground", "businessValue", "stakeholders"})


def native_business(form: dict) -> bool:
    """原生业务需求判定：判型归业务需求（含人工定稿）且非 B1 补票升级路径。"""
    recognition = (form.get("ext") or {}).get("typeRecognition")
    if not isinstance(recognition, dict) or recognition.get("b1Backfill"):
        return False
    return business_confirmed(recognition)


def dynamic_required_keys(standard: Standard | None, form: dict) -> frozenset:
    """动态必填 key 集：原生业务需求且非轻量时 B1~B4 启用（yaml 仍 required:false，启用归代码层）。"""
    if standard is None or demand_mode(form) == "light" or not native_business(form):
        return frozenset()
    return frozenset(f.key for f in standard.elements if f.key in B_ZONE_DYNAMIC_KEYS)


def schema_errors(standard: Standard | None, form: dict, *, required: bool = False, active_zones: set[str] | None = None, required_keys: set[str] | None = None) -> list[str]:
    """required=True 时按必填门槛校验；active_zones 限定必填生效的区（None=全部区生效，用于 B 区判型条件必填）；
    required_keys 直接限定必填生效的要素 key（light 最小集口径），优先于 active_zones。
    动态必填（2026-10-26 拍板路径分流）：原生业务需求的 B1~B4 与 A/C/D 必填同权校验——
    与区域/最小集口径正交，always 追加生效；升级型（b1Backfill）与轻量链路天然不命中。"""
    if standard is None:
        return ["需求类型未填写"] if required else []
    dyn = dynamic_required_keys(standard, form) if required else frozenset()
    errors = []
    for field in standard.fields:
        if field.system:
            continue
        value = get_value(form, field.field_path)
        # auto_fill（2026-10-20 拍板）：系统兜底提取项不占必填门槛——标题/底稿由系统提取，
        # 空值不拦「可以提交」，提交前由 submit 兜底链保证非空；格式校验（如 60 字上限）照常生效
        if required and (field.required or field.key in dyn) and not field.auto_fill and blank(value):
            gate = True
            if field.key in dyn:
                gate = True
            elif required_keys is not None:
                gate = field.key in required_keys
            elif active_zones is not None and field.zone is not None:
                gate = field.zone in active_zones
            if gate:
                errors.append(f"{field.label}未填写")
        error = field_error(field, value)
        if error:
            errors.append(error)
    return errors


def assess(standard: Standard, form: dict, *, light: bool = False):
    from app.agent.schemas import ElementStatus
    result = []
    for field in standard.elements:
        if field.system or not field.assessed:
            continue
        value = get_value(form, field.field_path)
        status, note = "OK", ""
        if blank(value):
            status, note = "MISSING", "未填写"
        elif field_error(field, value):
            status, note = "VAGUE", field_error(field, value)
        elif field.kind == "text" and field.key != "content":
            # content（原始提报文本）是系统原样保留的用户原话底稿（FR-02/D6），只在首条消息时
            # 原样回填、之后不再改写。因此：非空即 OK，不做歧义词/长度/可量化等任何软质量降级。
            # 2026-10-19 拍板：content 已从必填移除（系统提取项），空值仍判 MISSING 仅作质量清单
            # 标记，不追问、不拦提交；信息是否充分由可继续更新的场景/痛点/验收等要素承载。
            text = value.strip()
            rule = field.rule
            # 歧义词长句豁免（2026-10-12 拍板）：模糊表态只在"短句且以模糊词为主体"时才追问
            # （如「尽快好用」「方便一下」）；长句（≥18字）里的「方便/体验」多为正常结果陈述
            # （如「…导致客户经理阅读体验较差」），不得因子串命中误伤整个合格描述
            if len(text) < 18 and any(word in text for word in standard.vague_words):
                status, note = "VAGUE", "含歧义词"
            elif rule.min_len is not None and len(text) < rule.min_len:
                status, note = "VAGUE", field.vague_hint
            elif rule.max_len is not None and len(text) > rule.max_len:
                status, note = "VAGUE", field.vague_hint
            # light 模式下 D8（期望效果）放宽数字/量化词校验（2026-10-11 方案②）：
            # 换 logo/调样式这类需求的"做完后看着更正式"是合格答案，不得因缺数字被判 VAGUE 反复追问
            elif light and field.key == "acceptanceCriteria":
                pass
            elif rule.any_of and not any(word in text for word in rule.any_of):
                status, note = "VAGUE", field.vague_hint
            elif rule.any_of_regex and not any(re.search(pattern, text) for pattern in rule.any_of_regex):
                status, note = "VAGUE", field.vague_hint
        result.append(ElementStatus(key=field.key, label=field.label, status=status, note=note or ""))
    return result
