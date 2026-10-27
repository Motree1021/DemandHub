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


# 判型层级（2026-10-26 拍板派生制）：业务>用户>功能，「只涨不跌」取高时用
LEVEL_RANK = {"function": 1, "user": 2, "business": 3}


def effective_level(recognition: dict | None) -> str | None:
    """读取生效判型层级：人工定稿（confirmed 三选一）最高优先；新结构 level 直读；
    旧票数结构兼容折算（business/user ≥0.7 对应层级、有票即功能兜底，2026-10-24 档位对齐口径）。
    confirmed="none"（历史人工消除标记）按无判型处理，不折算旧票。"""
    if not isinstance(recognition, dict):
        return None
    confirmed = recognition.get("confirmed")
    if confirmed in LEVEL_RANK:
        return confirmed
    if confirmed == "none":
        return None
    level = recognition.get("level")
    if level in LEVEL_RANK:
        return level
    if float(recognition.get("business") or 0) >= 0.7:
        return "business"
    if float(recognition.get("user") or 0) >= 0.7:
        return "user"
    if any(float(recognition.get(key) or 0) > 0 for key in LEVEL_RANK):
        return "function"
    return None


def business_confirmed(recognition: dict | None) -> bool:
    """判型是否归为业务需求（2026-10-26 拍板派生制）：生效层级为 business 即算——
    来源可以是本轮素材派生、历史取高保留或人工定稿；判型仅作归类展示与 B 区必填闸门。"""
    return effective_level(recognition) == "business"


# C 区三件套：用户需求派生的充要素材（谁、什么场景、卡在哪）
C_TRIO_KEYS = ("userRole", "useScenario", "painPoint")


def derive_recognition(form: dict, field_sources: dict | None = None) -> dict | None:
    """判型派生（2026-10-26 拍板派生制；2026-10-27 拍板 evidence 机制修订，第二轮扩至 B2）：从表单素材
    直接推导层级，不再让模型打分——B1（业务目标）/B3（业务价值）/B2（业务背景）任一非空且出处为 user
    → 业务需求。「出处为 user」= 对话轮模型附原话证据（evidence）经规则层机械验真提升，或手改落库；
    AI 代拟（出处 agent）一律不参与派生，防「因为判业务所以代拟、因为代拟所以有值」循环自证；
    三项同标准（旧版 B1 有值即判业务属契约漏洞，#50 案例整句灌 B1 蒙对判型）。
    否则 C 区三件套（角色/场景/痛点）齐全 → 用户需求；已有实质素材但不满足以上两条 → 功能需求；
    表单仍空 → None（不出判型，H5 归类标签不渲染）。
    返回 {"level", "basis": {"field", "excerpt"}}，basis 留痕判定依据供受理侧追溯。"""
    sources = field_sources or {}
    elements = form.get("elements") or {}
    b_zone = elements.get("B") or {}
    c_zone = elements.get("C") or {}
    d_zone = elements.get("D") or {}

    def excerpt(value) -> str:
        text = str(value).replace("\n", " ").strip()
        return text[:30] + ("…" if len(text) > 30 else "")

    if not blank(b_zone.get("businessGoal")) and sources.get("elements.B.businessGoal") == "user":
        return {"level": "business", "basis": {"field": "businessGoal", "excerpt": excerpt(b_zone["businessGoal"])}}
    if not blank(b_zone.get("businessValue")) and sources.get("elements.B.businessValue") == "user":
        return {"level": "business", "basis": {"field": "businessValue", "excerpt": excerpt(b_zone["businessValue"])}}
    # B2 业务背景（2026-10-27 第二轮拍板）：用户亲口组织层面现状（evidence 验真或手改）同样触发判型；
    # 顺序追加在 B1/B3 之后，basis.field 留痕 businessBackground
    if not blank(b_zone.get("businessBackground")) and sources.get("elements.B.businessBackground") == "user":
        return {"level": "business", "basis": {"field": "businessBackground", "excerpt": excerpt(b_zone["businessBackground"])}}
    if all(not blank(c_zone.get(key)) for key in C_TRIO_KEYS):
        return {"level": "user", "basis": {"field": "useScenario", "excerpt": excerpt(c_zone.get("useScenario"))}}
    # 功能需求兜底：有任何实质素材（功能描述/场景片段/原文底稿）即判；空表单不判
    substantive = d_zone.get("functionDescription") or c_zone.get("useScenario") or form.get("content") or form.get("title")
    if not blank(substantive):
        return {"level": "function", "basis": {"field": "functionDescription", "excerpt": excerpt(substantive)}}
    return None


def merge_recognition(prev_recognition: dict | None, merged: dict, field_sources: dict) -> dict | None:
    """判型合并（2026-10-26 拍板派生制）：本轮按表单素材派生层级（derive_recognition），
    与历史生效层级取高（只涨不跌：业务>用户>功能——组织理由一旦确认就不该消失）；
    人工定稿 confirmed 最高优先、不被派生覆盖；新结构 {level, basis:{field, excerpt}, confirmed}，
    basis 留痕判定依据（触发字段+原文摘录）；旧票数结构仅在读取端折算（effective_level），
    写入一律新结构。prev_recognition 传调用方已合并人工 confirmed 的判型字典。"""
    prev = prev_recognition or {}
    prev_level = effective_level(prev)
    derived = derive_recognition(merged, field_sources)
    new_level = derived["level"] if derived else None
    candidates = [level for level in (prev_level, new_level) if level]
    level = max(candidates, key=lambda item: LEVEL_RANK[item]) if candidates else None
    confirmed = prev.get("confirmed")
    if level is None:
        return {"confirmed": confirmed} if confirmed is not None else None
    result = {"level": level}
    if derived and derived["level"] == level:
        result["basis"] = derived["basis"]
    elif isinstance(prev.get("basis"), dict):
        result["basis"] = prev["basis"]
    elif prev_level == "business" and isinstance(prev.get("evidence"), dict) and prev["evidence"].get("business"):
        # 旧票数结构折算展示：evidence.business 转为 basis 摘录
        result["basis"] = {"field": "", "excerpt": prev["evidence"]["business"]}
    if confirmed is not None:
        result["confirmed"] = confirmed
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


# B 区统一必填（2026-10-26 拍板，撤销同日早些时候的「原生/升级路径分流」）：判型归业务需求
# （business 票≥0.7 或人工定稿 business，含 B1 补票升级）且非轻量 → B1~B4 动态必填、缺了不能提交；
# 不分原生/升级、不看票来源。判型只涨不跌 → 门槛只加不减，无反复；轻量（微需求）链路全程不启用 B 区。
B_ZONE_DYNAMIC_KEYS = frozenset({"businessGoal", "businessBackground", "businessValue", "stakeholders"})


def dynamic_required_keys(standard: Standard | None, form: dict) -> frozenset:
    """动态必填 key 集：判型归业务需求且非轻量时 B1~B4 启用（yaml 仍 required:false，启用归代码层）。"""
    if standard is None or demand_mode(form) == "light":
        return frozenset()
    recognition = (form.get("ext") or {}).get("typeRecognition")
    if not business_confirmed(recognition if isinstance(recognition, dict) else None):
        return frozenset()
    return frozenset(f.key for f in standard.elements if f.key in B_ZONE_DYNAMIC_KEYS)


def schema_errors(standard: Standard | None, form: dict, *, required: bool = False, active_zones: set[str] | None = None, required_keys: set[str] | None = None) -> list[str]:
    """required=True 时按必填门槛校验；active_zones 限定必填生效的区（None=全部区生效，用于 B 区判型条件必填）；
    required_keys 直接限定必填生效的要素 key（light 最小集口径），优先于 active_zones。
    动态必填（2026-10-26 拍板统一必填）：判型归业务需求的 B1~B4 与 A/C/D 必填同权校验——
    与区域/最小集口径正交，always 追加生效；非业务判型与轻量链路天然不命中。"""
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
