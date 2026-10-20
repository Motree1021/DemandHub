"""模型只能抽取判质；来源、目标、话术与完成标记由纯函数决定。"""
import re
from copy import deepcopy

from app.agent.schemas import ElementStatus, ModelOutput, ModeSignalOutput, TypeSignalsOutput
from app.standards import loader as standard_loader
from app.standards.rules import (
    LIGHT_REQUIRED_KEYS,
    assess,
    blank,
    business_confirmed,
    filter_form,
    get_value,
    schema_errors,
    set_value,
)
from app.standards.schema import Standard

# 闲聊引导话术（2026-10-20 拍板，单问题原则：一条回复最多一个问句）：
# 首轮（会话还没有任何一轮正式结果）只发简短引导、不追问——前端聊天气泡第一条已有完整静态开场白，
# 再发完整版会连着出现两遍相同文字，故首轮用简短变体；对话中期闲聊用短承接+重问当前问题（接续而非第二问）
CHITCHAT_GREET_FIRST = "你好！我在，直接说你的需求就行——一句话诉求、整段粘贴、语音转文字都可以。"
CHITCHAT_GUIDE = "我在，咱们继续把需求记清楚。"

# 无描述白话邀请（2026-10-19 拍板）：底稿（content）为空且未达提交门槛时的对话开场白——
# 一句话同时喂饱底稿回填、要素抽取与轻重判定；替代此前「请补充原始提报文本」的术语追问
DESC_INVITE = "请先用一句话描述一下你的需求，比如「报表想加个按机构导出」。"


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
            # 模型把质量状态词当值写进字段（真实链路已观测 elements.B.businessGoal="VAGUE"）属自相矛盾输出，按未输出过滤
            if isinstance(item, str) and item.strip().upper() in {"VAGUE", "MISSING"}:
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
    # ext.returnReason 打回原因（方案③）由管理员写入、系统管理，filter_form 会丢弃：从旧表单原样保留
    # （不读模型输出，防止模型伪造打回原因），否则对话一轮后 merged 里打回原因丢失、AI 无法引述
    old_return_reason = (form.get("ext") or {}).get("returnReason")
    # 容错模式：模型输出的单个非法值（如日期写"本周"）丢弃而非整轮报错；demandTypeCode 已在上方单独严控
    result = filter_form(normalization_standard, result, validate=False)
    if isinstance(pending_splits, list) and pending_splits:
        result.setdefault("ext", {})["pendingSplits"] = pending_splits
    if isinstance(overview, dict) and overview:
        result.setdefault("ext", {})["overview"] = overview
    if isinstance(old_return_reason, dict) and old_return_reason:
        result.setdefault("ext", {})["returnReason"] = old_return_reason
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


def merge_mode_signal(signal: ModeSignalOutput | None, form: dict) -> dict | None:
    """轻重判定票与既有 ext.mode 合并（2026-10-11 方案②）：standard 粘性——判定过 standard 后
    模型不得再降回 light（防止对话后期把已按常规口径追问的需求悄悄放宽）；未判定时缺省 standard。
    方案④（2026-10-11 口径改判）：origin=user 为提报人手动定过的口径，AI 双向粘性不得翻转。"""
    prev = (form.get("ext") or {}).get("mode") or {}
    prev_level = prev.get("level") if isinstance(prev, dict) else None
    if signal is None:
        # 本轮未输出轻重票：原样保留旧判定（含 origin 标记，丢了会导致下一轮 AI 不粘用户口径）
        return dict(prev) if prev_level else None
    if prev.get("origin") == "user" and prev_level:
        # 用户手动改判后 AI 不得翻转（对称归类 confirmed）：想换口径走「归类」弹层的口径项
        return {"level": prev_level, "evidence": prev.get("evidence", ""), "origin": "user"}
    if prev_level == "standard":
        return {"level": "standard", "evidence": prev.get("evidence") or signal.evidence}
    return {"level": signal.level, "evidence": signal.evidence}


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


def complete_elements(standard: Standard, form: dict, model_elements: list[ElementStatus], *, light: bool = False):
    allowed = {element.key for element in standard.elements}
    keys = [element.key for element in model_elements]
    if len(keys) != len(set(keys)) or not set(keys) <= allowed:
        raise ValueError("模型质量要素不属于当前标准或重复")
    model = {element.key: element for element in model_elements}
    result = []
    for rule in assess(standard, form, light=light):
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


def inherit_and_count(prev, curr, prev_target, said_skip, *, standard, previous_form, form, count_keys=None):
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
        elif count_keys and element.key in count_keys and changed and status != "OK":
            # 手改接续计数（2026-10-19 拍板）：本轮手改过的要素仍不达标记 1 次（没碰的不记），
            # 与对话路径「问满两次放过」同口径——消灭手改反复重问无终点的漏洞
            attempts = min(standard.max_attempts, attempts + 1)
        if status == "OK":
            attempts = 0
        output.append(element.model_copy(update={"status": status, "note": note, "attempts": attempts}))
    return output


def compute_missing(standard, form):
    # auto_fill（2026-10-20 拍板）：系统兜底提取项不算用户侧缺口——指令回复列缺项/缺失清单
    # 不把标题算进去（提交前系统重拟兜底，让用户补标题违背「系统提取」定位）
    return [e.key for e in standard.elements if e.required and not e.system and not e.auto_fill and blank(get_value(form, e.field_path))]


def pick_follow_up(standard, elements, *, business: bool = False, light: bool = False, form: dict | None = None, can_submit: bool = False):
    """选下一个追问目标。

    追问顺序：A/C/D 必填先问完（用户先补"给谁用、什么场景、痛点、验收"等具体信息），
    B 区业务要素次之；且 B 区仅在判型为业务需求（business=True）时才追问，
    日常功能需求完全不问 B 区（与提交门槛 active_zones 口径一致）。
    紧急程度沉底最后问（2026-10-15 拍板）：排期类信息待需求本体问齐后再确认；
    答"紧急/特急"时急单门控承接追问期望交付时间，恰好收尾。

    light 模式（2026-10-11 方案②）：只追问最小集 {期望效果(D8)→紧急度}，
    每项最多问一次（合计≤2轮，对齐拍板口径；紧急度 2026-10-15 起同步沉底），
    C/D 其余要素与 B 区一律不问；content 永不追问（A8 底稿由系统首条消息回填），
    title 2026-10-20 起同为系统提取项（auto_fill）退出追问序列。

    急单门控（2026-10-12 拍板；2026-10-20 起 light 同规）：紧急度为紧急/特急而期望交付时间
    还空着时，插队最优先追问日期——紧急度话术承诺「紧急或特急请说明期望时间」，但点选快捷项
    只发枚举标签（如「紧急」两个字），没有时间信息可抽，不插队追问承诺就落空；急单不分轻重，
    light 同样生效并遵守「每项最多问一次」上限；日期填上或问满（attempts 达上限）即自动恢复
    正常顺序。仅 TECH 生效（MATL/TRAIN 的期望时间在 common_fields、不在追问循环，无此场景）。

    可提交即停问软质量（2026-10-12 拍板）：一旦必填门槛达成（can_submit=True，AI 已说
    「可以提交」），除急单交付日期这种"承诺型追问"外，不再对"有值但被判不够量化/不够具体"
    的非空必填项主动发问——完成话术承诺了「不太完整的可选项不影响提交、以后能补」，继续
    追问即前后矛盾；完善提示留在表单卡片由用户/产品经理自愿补，质量兜底走打回机制。
    MISSING（真空着）不受此限：必填缺口仍需追问或拦提交。
    """
    by_key = {element.key: element for element in elements}
    field_of = {element.key: element for element in standard.elements}
    required = [e.key for e in standard.elements if e.required and not e.system]
    # light 追问顺序固定（2026-10-15 拍板紧急度同步沉底；2026-10-20 拍板标题转系统提取项退出序列）：
    # 期望效果先问并连带标题确认，紧急度最后
    light_order = ["acceptanceCriteria", "urgency"]

    def eligible(key):
        field = field_of.get(key)
        if field is None:
            return False
        # auto_fill（2026-10-20 拍板）：系统兜底提取项（标题）永不作为追问目标
        if field.auto_fill:
            return False
        if light:
            if key not in light_order:
                return False
            element = by_key.get(key)
            # 只问真空着的项（2026-10-15）：有值但笼统（VAGUE）不追问——light 承诺最少打扰，
            # 与"可提交即停问软质量"同口径；也避免用户已答过（哪怕笼统）又被反问的观感
            return element is not None and element.status == "MISSING" and element.attempts < 1
        if field.zone == "B" and not business:
            return False
        element = by_key.get(key)
        if element is None or element.status in {"OK", "SKIP"} or element.attempts >= standard.max_attempts:
            return False
        # 可提交后停问软质量：非空（VAGUE）的必填项不再主动追问；MISSING（真空着）仍追问
        if can_submit and element.status != "MISSING":
            return False
        return True

    # 急单门控插队最优先（light 同规，2026-10-20 拍板）：急单不分轻重，交付承诺不落空；
    # light 遵守「每项最多问一次」上限——比 standard 更严，问过一次就放过不纠缠
    if form is not None and get_value(form, "urgency") in {"URGENT", "CRITICAL"}:
        delivery = by_key.get("expectDeliveryAt")
        if delivery is not None and delivery.status not in {"OK", "SKIP"}:
            if delivery.attempts < (1 if light else standard.max_attempts):
                return delivery
    if light:
        for key in light_order:
            if eligible(key):
                return by_key[key]
        return None
    # 稳定排序：A/C/D 必填在前（保持 yaml 原顺序），B 区沉底，紧急程度最后（2026-10-15 拍板）
    ordered = sorted(required, key=lambda k: (k == "urgency", 1 if field_of[k].zone == "B" else 0))
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


def _anchor_snippet(standard, form, key):
    """取锚定要素的当前值并截断为引述片段；要素不存在或值为空时返回空串。"""
    anchor_field = next((e for e in standard.elements if e.key == key), None)
    if anchor_field is None:
        return ""
    value = str(get_value(form, anchor_field.field_path) or "").strip()
    if not value:
        return ""
    return value[:20] + ("…" if len(value) > 20 else "")


def anchored_template(standard, field, form):
    """首次追问锚定（2026-10-10 用户拍板）：引用已填的关联要素组织问句——
    B1 业务目标←C2 用户目标（上下游因果）、B4 干系人←C1 目标用户（受益方可由使用者推导），
    关联要素为空或未配置时返回空串，回落到普通追问模板。
    双锚定（2026-10-15 拍板，C3 使用场景←C1 角色+C2 任务）：anchor_key2 配置且两个锚值
    都已填时优先用 ask_anchor2——话术把两段已识别信息都引述出来请用户确认/纠正，
    再问模板未覆盖的缺口（如时机/频率）；仅主锚有值时仍用 ask_anchor。"""
    snippet = _anchor_snippet(standard, form, field.anchor_key) if field.anchor_key else ""
    if not snippet:
        return ""
    if field.anchor_key2 and field.ask_anchor2:
        snippet2 = _anchor_snippet(standard, form, field.anchor_key2)
        if snippet2:
            return field.ask_anchor2.replace("{anchor}", snippet).replace("{anchor2}", snippet2)
    if not field.ask_anchor:
        return ""
    return field.ask_anchor.replace("{anchor}", snippet)


def _return_reason_of(form: dict) -> str | None:
    return ((form.get("ext") or {}).get("returnReason") or {}).get("reason")


# 完成话术按触发场景区分（2026-10-20 拍板）：打回补充单要素本就齐全，
# 不再播「可选项以后能补、产品经理调研后可补」的新手引导长话术；附件/手改/进页面各自给简短行动指引
RETURN_QUOTE_PREFIX = "这条需求之前被打回过，打回原因是「{reason}」。按这个说明改好后就能重新提交。"
_RETURN_DONE = {
    "attachment": "可以点「确认提交」重新提交。",
    "manual": "修改已记录好，可以点「确认提交」重新提交。",
    "enter": "可以点「确认提交」重新提交。",
    "event": "可以点「确认提交」重新提交。",
    "dialog": "补充的内容已记录好，点下方「确认提交」即可重新提交。",
}
_RETURN_INCOMPLETE = {
    "attachment": "还有几项必填信息没填齐，请在下方表单里补齐后重新提交。",
    "manual": "修改已记录好。还有几项必填信息没填齐，请在下方表单里补齐后重新提交。",
}
_DRAFT_DONE = {
    "attachment": "可以点「确认提交」提交。",
    "manual": "修改已记录好，可以点「确认提交」提交。",
    "enter": "该填的都齐了，可以提交。",
    "event": "该填的都齐了，可以提交。",
}
_DRAFT_INCOMPLETE_ATTACHMENT = "还有几项必填信息没填齐，请在下方表单里补齐后提交。"
# 打回原因引述前缀的固定开头：用于历史消息判定「本补充会话是否已引述过」（只引述一次）
RETURN_QUOTE_MARK = "这条需求之前被打回过，打回原因是"


def _incomplete_reply(*, light: bool, trigger: str, return_reason: str | None) -> str:
    """无追问目标但必填仍缺（追问次数用尽放过）时的兜底指引。"""
    if return_reason:
        return _RETURN_INCOMPLETE.get(trigger, "还有几项必填信息没填齐，请在下方表单里补齐后重新提交。")
    if trigger == "attachment":
        return _DRAFT_INCOMPLETE_ATTACHMENT
    return ("我这边问得差不多了。还差的几项请在下方表单里补齐后提交。" if light
            else "我这边问得差不多了。请在下方表单里把标红星※的必填项补齐后提交。")


def _prefix_return_quote(reply: str, form: dict, *, return_quoted: bool) -> str:
    """打回原因引述（2026-10-20 拍板）：补充会话只引述一次，由调用方按历史消息判定是否首次。"""
    if not return_quoted:
        return reply
    reason = _return_reason_of(form)
    if not reason:
        return reply
    return RETURN_QUOTE_PREFIX.format(reason=reason) + reply


def return_quote_seen(texts) -> bool:
    """历史助理消息里是否已引述过打回原因（2026-10-20 拍板）：补充会话只引述一次。
    打回当刻的完整通知措辞为「这条需求被产品经理打回了」，不含本标记，不会误判。"""
    return any(RETURN_QUOTE_MARK in (text or "") for text in texts)


def reply_for(standard, target, form, *, light: bool = False, business: bool = False, trigger: str = "dialog"):
    if target is None:
        active_zones = {"A", "C", "D"} | ({"B"} if business else set())
        return_reason = _return_reason_of(form)
        if light:
            complete = not schema_errors(standard, form, required=True, required_keys=LIGHT_REQUIRED_KEYS)
        else:
            complete = not schema_errors(standard, form, required=True, active_zones=active_zones)
        if complete:
            if return_reason:
                return _RETURN_DONE.get(trigger, _RETURN_DONE["dialog"])
            if trigger == "dialog":
                return ("都记好了，请核对一下表单。该填的都齐了，可以提交。" if light
                        else "都记好了，请核对一下表单。该填的都齐了，可以提交。没填或不太完整的可选项会在表单里标出来，不影响提交，以后能补；产品经理调研后也可以补。")
            if trigger == "attachment":
                return _DRAFT_DONE["attachment"]
            if trigger == "manual":
                return _DRAFT_DONE["manual"]
            return _DRAFT_DONE["event"]
        return _incomplete_reply(light=light, trigger=trigger, return_reason=return_reason)
    field = next(e for e in standard.elements if e.key == target.key)
    value = str(get_value(form, field.field_path) or "")
    snippet = value[:20] + ("…" if len(value) > 20 else "")
    # light 模式 D8 用白话问「期望效果」并顺带确认 AI 代拟标题（拍板：紧急度→标题+效果一次确认）；
    # 不复用 yaml 的量化验收话术，避免"给个可检查的标准"把换 logo 这类轻量需求问成考试题
    if light and field.key == "acceptanceCriteria" and target.attempts == 0:
        title = str(get_value(form, "title") or "").strip()
        if title:
            return f"标题我先记为「{title}」，不合适直接告诉我改什么。这个需求期望的效果是什么？做完后能看见什么变化？比如「首页顶部 logo 换成新设计的蓝色版本」。"
        return "这个需求期望的效果是什么？做完后能看见什么变化？比如「首页顶部 logo 换成新设计的蓝色版本」。"
    if target.attempts >= 1:
        template = field.ask_l2 or field.ask_l1 or field.ask_missing
    else:
        template = anchored_template(standard, field, form) or (field.ask_missing or field.ask_l1 if target.status == "MISSING" else field.ask_l1 or field.ask_missing)
    template = template or f"请补充{field.label}，以便把需求记录清楚。"
    reply = template.replace("{snippet}", snippet)
    if target.attempts >= 1 and not field.required:
        reply += " 也可以说“后续补充”。"
    return reply


def _quoted_reask(standard: Standard, target: ElementStatus, form: dict) -> str:
    """手改后仍不达标的引述式重问（2026-10-19 拍板）：引述用户刚填的原话+说明差距+追问模板，
    避免「我不是填了吗」的观感；手填值本身是用户权威，只提示不擅改。"""
    field = next(e for e in standard.elements if e.key == target.key)
    value = str(get_value(form, field.field_path) or "").replace("\n", " ").strip()
    snippet = value[:20] + ("…" if len(value) > 20 else "")
    template = field.ask_l2 or field.ask_l1 or field.ask_missing or f"请补充{field.label}，以便把需求记录清楚。"
    hint = target.note or field.vague_hint or "还不够具体"
    return f"你填的「{field.label}」『{snippet}』我记下了，不过{hint}——" + template


def _supplement_confirm(standard: Standard, previous_form: dict, merged: dict, prev_target: str | None, *, skip_keys=None) -> str:
    """补充/纠正的引述式确认（2026-10-19 拍板）：列出本轮值发生变化的非当前问题要素并引述
    新值片段请用户确认——与 C3 双锚定话术同风格，AI 听错/抽错时用户能当场发现并纠正。
    系统字段/底稿/标题/类型不做确认（content 为首轮回填、title/类型由系统判定）；
    skip_keys（手改场景=用户手填的要素）已由手改播报告知，不再重复确认。"""
    parts = []
    for field in standard.elements:
        if field.system or field.key in ("title", "demandTypeCode", "content") or field.key == prev_target or (skip_keys and field.key in skip_keys):
            continue
        new_v = get_value(merged, field.field_path)
        old_v = get_value(previous_form, field.field_path)
        if not blank(new_v) and old_v != new_v:
            text = str(new_v).replace("\n", " ").strip()
            snippet = text if len(text) <= 20 else text[:20] + "…"
            parts.append(f"「{field.label}」已按你补充的更新：{snippet}")
    if not parts:
        return "好的，补充的我记下了。"
    return "；".join(parts) + "。"


def _clear_echo_backfill(merged: dict, field_sources: dict, text: str) -> None:
    """非抽取意图（闲聊/提问/指令）的误回填清理（2026-10-20 拍板，问题②推广）：
    prepare 会把本轮消息原文预填为 A8 底稿，但纯寒暄/提问/指令并非需求内容——
    底稿==本轮消息原文时判定为误回填，连来源标记一起清掉，防脏数据留草稿随单提交。"""
    if text.strip() and (merged.get("content") or "") == text:
        merged.pop("content", None)
        field_sources.pop("content", None)


def _process_chitchat(form: dict, sources: dict, prev: list[ElementStatus], previous_form: dict, text: str, *, standards=None) -> dict:
    """纯闲聊分流（2026-10-19 拍板，问题③）：不抽取、不判型/轻重、不计 attempts。
    单问题原则（2026-10-20 拍板）：首轮（prev 为空=还没有任何一轮正式结果）只发简短引导、
    不追问、askedTarget 记空（避免下一轮把答非所问按答错计数）；对话中期短承接+重问当前问题。"""
    merged = deepcopy(form)
    field_sources = dict(sources)
    _clear_echo_backfill(merged, field_sources, text)
    type_code = merged.get("demandTypeCode")
    selected = (standards[type_code] if standards else standard_loader.get(type_code)) if type_code else None
    standard = selected or (standards["MATL"] if standards else standard_loader.get("MATL"))
    recognition = (merged.get("ext") or {}).get("typeRecognition")
    mode = (merged.get("ext") or {}).get("mode")
    light = (mode or {}).get("level") == "light"
    curr = [e for e in assess(standard, merged, light=light)]
    # prev_target 传 None：attempts/SKIP 只继承不计数——用户没作答当前问题，不能按答错惩罚
    curr = inherit_and_count(prev, curr, None, False, standard=standard, previous_form=previous_form, form=merged)
    is_business = business_confirmed(recognition)
    if light:
        can_submit = selected is not None and not schema_errors(selected, merged, required=True, required_keys=LIGHT_REQUIRED_KEYS)
    else:
        active_zones = {"A", "C", "D"} | ({"B"} if is_business else set())
        can_submit = selected is not None and not schema_errors(selected, merged, required=True, active_zones=active_zones)
    if not prev:
        # 首轮闲聊：只引导不追问（单问题原则）——此前连发引导+标题确认两个问题，用户不知答哪个
        target = None
        reply = CHITCHAT_GREET_FIRST
    else:
        target = pick_follow_up(standard, curr, business=is_business, light=light, form=merged, can_submit=can_submit)
        reply = CHITCHAT_GUIDE
        if target is not None:
            reply += " " + reply_for(standard, target, merged, light=light, business=is_business)
    return {
        "structured": merged, "fieldSources": field_sources,
        "missing": compute_missing(standard, merged), "elements": [e.model_dump(by_alias=True) for e in curr],
        "askedTarget": target.key if target else None, "canSubmit": can_submit, "ready": can_submit,
        "guidanceComplete": target is None, "qualityComplete": all(e.status == "OK" for e in curr),
        "quickReplies": quick_replies(standard, target), "reply": reply,
        "typeRecognition": recognition, "mode": mode, "granularityHint": None, "impactHints": [],
        "intent": "chitchat",
    }


def process(output: ModelOutput, form: dict, sources: dict, prev: list[ElementStatus], prev_target: str | None, previous_form: dict, text: str, *, standards=None, manual_keys=None,
            trigger: str = "dialog", return_quoted: bool = True):
    # 意图分流（2026-10-19 拍板）：模型判定本轮在做什么；纯闲聊走独立分支（不抽取不判定），
    # 补充/提问/指令照常合并抽取，但不按"答错当前问题"惩罚（attempts 不计数）。
    # manual_keys（手改抽取链路，2026-10-19 拍板）：本轮用户手填的要素 key——
    # ①引述确认跳过（播报已告知）②仍不达标按手改口径计数 ③被重问时用引述式话术
    kind = output.intent.kind if output.intent else "answer"
    if kind == "chitchat":
        return _process_chitchat(form, sources, prev, previous_form, text, standards=standards)
    merged, field_sources, selected = merge_structured(output.structured, form, sources, standards=standards, grounded_text=text)
    # 误回填清理推广（2026-10-20 拍板，问题②）：提问/指令与闲聊同口径——纯提问（「什么是需求标题？」）
    # 或流程指令（「提交吧」）并非需求内容，prepare 预填的底稿连来源一起清掉
    if kind in ("question", "command"):
        _clear_echo_backfill(merged, field_sources, text)
    # 未定类型仍使用共用三个质量字段，不暴露 TECH 扩展要素。
    standard = selected or (standards["MATL"] if standards else standard_loader.get("MATL"))
    # FR-01/FR-03 判型合并：confirmed（用户定稿）不被模型覆盖，模型票只更新置信度与依据
    recognition = merge_type_signals(output.type_signals, form)
    if recognition:
        merged.setdefault("ext", {})["typeRecognition"] = recognition
        prev_confirmed = ((form.get("ext") or {}).get("typeRecognition") or {}).get("confirmed")
        field_sources["ext.typeRecognition"] = "user" if prev_confirmed is not None else "agent"
    # 微需求快速通道（2026-10-11 方案②）：轻重判定合并入 ext.mode，standard 粘性不回退
    prev_mode = (form.get("ext") or {}).get("mode")
    prev_mode_level = prev_mode.get("level") if isinstance(prev_mode, dict) else None
    mode = merge_mode_signal(output.mode_signal, form)
    if mode:
        merged.setdefault("ext", {})["mode"] = mode
        field_sources["ext.mode"] = "agent"
    light = (mode or {}).get("level") == "light"
    # light→standard 升级当轮播报：告知口径变化，避免用户困惑为何突然多问几项
    mode_upgraded = prev_mode_level == "light" and not light
    # 首判轻量当轮播报（方案④口径显性化）：与升级播报对称——此前判轻量一声不吭，
    # 用户不知道为何只问 4 项、也不知道 AI 做过"小改动"判断；用户手动定过口径（origin=user）不播
    mode_first_light = prev_mode_level is None and light
    curr = complete_elements(standard, merged, output.elements, light=light)
    # 仅 answer 才把 prev_target 按"答了没答好"计数；supplement/question/command 传 None——
    # 用户没回答当前问题（在补充别的/提问/发指令），不计 attempts，SKIP 状态照常继承
    counting = kind == "answer"
    curr = inherit_and_count(prev, curr, prev_target if counting else None,
                             user_said_skip(standard, text) if counting else False,
                             standard=standard, previous_form=previous_form, form=merged,
                             count_keys=manual_keys)
    # B 区必填按判型门槛生效（PRD §4.3、FR-03 分支）：业务需求全量四区，否则 A/C/D
    is_business = business_confirmed(recognition)
    # 先算提交门槛，再据"可提交即停问软质量"选追问目标：必填已齐便不再对不够量化的非空必填项发问
    if light:
        can_submit = selected is not None and not schema_errors(selected, merged, required=True, required_keys=LIGHT_REQUIRED_KEYS)
    else:
        active_zones = {"A", "C", "D"} | ({"B"} if is_business else set())
        can_submit = selected is not None and not schema_errors(selected, merged, required=True, active_zones=active_zones)
    # 追问顺序与提交门槛共用同一判型口径：业务需求才追问 B 区，且 A/C/D 先问完再问 B；
    # light 模式只按最小集追问（每项一次）并按最小集放行提交
    target = pick_follow_up(standard, curr, business=is_business, light=light, form=merged, can_submit=can_submit)
    granularity = detect_granularity(standard, merged, text)
    impacts = impact_hints(previous_form, merged)
    # D9 建议方案首次抽取播报（2026-10-12 拍板）：用户设想的候选方案/实现路径此前被五区白名单
    # 静默丢弃，AI 还回「都记好了」构成误导；现在落库后由模板层告知"已记入、供评估、非定案"（模型自述不可靠）。
    # 2026-10-15 调整：播报改引述式（截取原文片段，误归类时用户能认出是哪句、可纠正），并后置到追问之后——
    # 此前抽象概括+前置，用户不知哪句被归为"设想做法"、先听方案再被追问，观感莫名其妙。仅 TECH 标准有 D9，MATL/TRAIN 跳过
    solution_notice = ""
    solution_field = next((f for f in standard.elements if f.key == "proposedSolution"), None)
    if solution_field is not None and blank(get_value(form, solution_field.field_path)) and not blank(get_value(merged, solution_field.field_path)):
        solution_text = get_value(merged, solution_field.field_path).replace("\n", " ").strip()
        snippet = solution_text if len(solution_text) <= 30 else solution_text[:30] + "…"
        solution_notice = f"你说的「{snippet}」我先记到「建议方案」里了，会随需求一起给受理方参考——最终做法由产品和技术评估后再定。"
    # command（流程指令，2026-10-19 拍板）：回复聚焦指令本身，不叠加模式播报/方案播报等前缀——
    # 用户说「提交吧」时播「这个需求听起来改动面不小」完全文不对题
    if kind == "command":
        is_return = bool(_return_reason_of(merged))
        if can_submit:
            reply = ("好的，信息都齐了，点下方「确认提交」就能重新提交。" if is_return
                     else "好的，信息都齐了，点下方「提交」按钮就能提报。")
        else:
            missing_labels = [f.label for f in standard.elements if f.key in compute_missing(standard, merged)]
            reply = "还差几项必填信息才能提交：" + "、".join(f"「{label}」" for label in missing_labels) + "。"
            if target is not None:
                reply += " " + reply_for(standard, target, merged, light=light, business=is_business, trigger=trigger)
            else:
                reply += " 请在下方表单里补齐后提交。"
    else:
        # 手改要素仍不达标被选中重问时换引述式话术（2026-10-19 拍板）：引原话+说差距，避免「我不是填了吗」
        if target is not None and manual_keys and target.key in manual_keys and target.status == "VAGUE":
            reply = _quoted_reask(standard, target, merged)
        else:
            reply = reply_for(standard, target, merged, light=light, business=is_business, trigger=trigger)
        # 意图前缀（2026-10-19 拍板）：补充引述确认/提问要素级解释后桥接回当前问题——
        # 当前问题未被作答、仍是缺口首位时加「回到刚才的问题」衔接，观感接续而非各说各的
        bridge = " 回到刚才的问题——" if target is not None and prev_target and target.key == prev_target else " "
        if kind == "supplement":
            reply = _supplement_confirm(standard, previous_form, merged, prev_target, skip_keys=manual_keys) + bridge + reply
        elif kind == "question":
            qkey = output.intent.target_key if output.intent else None
            qfield = next((f for f in standard.elements if f.key == qkey), None)
            if qfield is not None:
                explain = f"「{qfield.label}」{qfield.ask_missing or qfield.ask_l1 or f'是要说明{qfield.label}的具体情况。'}"
                # 解释的正是当前问题要素时，解释话术本身已是追问，不重复问
                reply = explain if target is not None and target.key == qkey else explain + bridge + reply
            else:
                reply = "我主要帮你把需求记清楚，这个问题我说不好；你按自己的理解大概说说，我帮你整理。" + bridge + reply
        if mode_upgraded:
            reply = "这个需求听起来改动面不小，我按常规需求帮你把基本信息问齐。" + reply
        if mode_first_light:
            reply = "这个需求听起来是个小改动，我按轻量提报帮你登记，只确认几项关键信息就行。" + reply
        if solution_notice:
            reply = reply + " " + solution_notice
        if impacts:
            reply = " ".join(impacts) + " " + reply
        if granularity:
            reply = granularity["hint"] + " " + reply
        # 打回原因引述（2026-10-20 拍板）：补充会话只引述一次——调用方按历史消息判定是否首次；
        # 打回当刻另有完整通知，重提清除 returnReason 后引述自然消失；模型自述不可靠，引述由模板层保证。
        # command 意图不叠加（「点确认提交重新提交」与引述尾巴语义重复）
        reply = _prefix_return_quote(reply, merged, return_quoted=return_quoted)
    return {
        "structured": merged, "fieldSources": field_sources,
        "missing": compute_missing(standard, merged), "elements": [e.model_dump(by_alias=True) for e in curr],
        "askedTarget": target.key if target else None, "canSubmit": can_submit, "ready": can_submit,
        "guidanceComplete": target is None, "qualityComplete": all(e.status == "OK" for e in curr),
        "quickReplies": quick_replies(standard, target), "reply": reply,
        "typeRecognition": recognition, "mode": mode, "granularityHint": granularity, "impactHints": impacts,
        # intent 落库（2026-10-20 拍板）：随 ASSISTANT 消息 payload 存档，提交时按 request_id 配对
        # 识别并排除闲聊/提问/指令轮的用户消息，保证底稿只拼接有效对话
        "intent": kind,
    }


def resume_follow_up(standard: Standard, form: dict, previous: dict | None, *, changed_keys=None,
                     trigger: str = "event", return_quoted: bool = True) -> dict:
    """对话外事件（手改要素/附件回执，2026-10-19 拍板问题②）后的流程接续，不调模型：
    规则层重算要素状态、从上一轮对话快照继承 attempts/SKIP（prev_target=None 不按对话答错计数；
    changed_keys=本轮手改的要素，值有变化仍不达标按手改口径记 1 次、满 2 次放过），
    选下一追问目标并生成话术；必填已齐时按触发动作给简短完成话术（2026-10-20 拍板）。
    手改清空的必填项按 MISSING 自然被重问，手改仍不达标（VAGUE）被重问时用引述式话术。
    trigger: attachment/manual/enter/event——决定完成话术口径；
    return_quoted: 打回原因是否在本轮引述（补充会话只引述一次，由调用方按历史消息判定）。
    返回 {reply, askedTarget, elements, canSubmit, guidanceComplete, quickReplies}，
    payload 结构对齐对话结果消息，供前端质量清单回放与下一轮 previous 快照。"""
    ext = form.get("ext") or {}
    mode = ext.get("mode") or {}
    light = (mode.get("level") if isinstance(mode, dict) else None) == "light"
    recognition = ext.get("typeRecognition") or {}
    is_business = business_confirmed(recognition if isinstance(recognition, dict) else {})
    curr = list(assess(standard, form, light=light))
    prev_elements = [ElementStatus.model_validate(e) for e in ((previous or {}).get("elements") or [])]
    curr = inherit_and_count(prev_elements, curr, None, False, standard=standard,
                             previous_form=(previous or {}).get("structured") or {}, form=form,
                             count_keys=changed_keys)
    if light:
        can_submit = not schema_errors(standard, form, required=True, required_keys=LIGHT_REQUIRED_KEYS)
    else:
        active_zones = {"A", "C", "D"} | ({"B"} if is_business else set())
        can_submit = not schema_errors(standard, form, required=True, active_zones=active_zones)
    # 无描述白话邀请（2026-10-19 拍板）：底稿为空且未达门槛时，先请用户一句话描述需求——
    # 一句话同时喂饱底稿回填、要素抽取与轻重判定。仅非必填 content（科技标准）适用；
    # MATL/TRAIN 的 content 仍必填，维持原追问（待独立助手重建）
    content_field = next((f for f in standard.elements if f.key == "content"), None)
    if content_field is not None and not content_field.required and blank(get_value(form, "content")) and not can_submit:
        content_status = next((e for e in curr if e.key == "content"), None)
        return {
            "reply": _prefix_return_quote(DESC_INVITE, form, return_quoted=return_quoted),
            "askedTarget": "content",
            "elements": [e.model_dump(by_alias=True) for e in curr],
            "canSubmit": can_submit, "guidanceComplete": False,
            "quickReplies": quick_replies(standard, content_status),
        }
    target = pick_follow_up(standard, curr, business=is_business, light=light, form=form, can_submit=can_submit)
    if target is not None and changed_keys and target.key in changed_keys and target.status == "VAGUE":
        reply = _quoted_reask(standard, target, form)
    else:
        reply = reply_for(standard, target, form, light=light, business=is_business, trigger=trigger)
    # 打回原因引述（2026-10-20 拍板）：补充会话只引述一次，由调用方按历史消息判定 return_quoted
    reply = _prefix_return_quote(reply, form, return_quoted=return_quoted)
    return {
        "reply": reply,
        "askedTarget": target.key if target else None,
        "elements": [e.model_dump(by_alias=True) for e in curr],
        "canSubmit": can_submit, "guidanceComplete": target is None,
        "quickReplies": quick_replies(standard, target),
    }
