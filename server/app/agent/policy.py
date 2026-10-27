"""模型只能抽取判质；来源、目标、话术与完成标记由纯函数决定。"""
import re
from copy import deepcopy

from app.agent.schemas import ElementStatus, ModelOutput, ModeSignalOutput
from app.db.models import now
from app.standards import loader as standard_loader
from app.standards.rules import (
    LIGHT_REQUIRED_KEYS,
    assess,
    blank,
    dynamic_required_keys,
    filter_form,
    get_value,
    merge_recognition,
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

# B1 答不出放行书（2026-10-24 拍板）：B1 白话一问答「不清楚/说不好」类时的固定回应——
# 不追问第二次、不标质量问题、不拦提交；绝不承诺「后续找谁补」（组织级目标是受理方分析产物，
# 不是向某用户追来的答案）。话术红线：禁用「提报人/受理」等角色流程术语，受理侧统一称「产品经理」
B1_RELEASE = "没事，这个先空着，不耽误提交，后面的产品经理会一起考虑。"

# B1 硬堵改判引导（2026-10-26 拍板统一必填）：判型归业务需求时 B1 转必填、答不出不放行——
# 给用户白话出口：说不上组织好处就点归类标签改判为用户需求，改判后 B 区不再必填（用户拍板：不设轻量出口）。
# 2026-10-27 第四轮拍板：解释句与改判出口后置——只在用户答「不清楚/说不好」时出现，首问不携带
B1_RECLASSIFY_GUIDE = "这个需求归类为业务需求，「对组织的好处」这项得填了才能提交。实在说不上来的话，可以点表单上方「归类：业务需求」那里改判为用户需求，这项就不用填了。"

# 原话证据字段（2026-10-27 拍板 evidence 机制；2026-10-27 第二轮扩至 B2；第三轮出处三档化）：仅 B1（业务目标）/B2（业务背景）/B3（业务价值）
# 允许模型以 {"value": 字段值, "evidence": 用户消息原文连续片段} 对象输出；evidence 只登记待验真，不落库不进表单。
# 验真通过出处升 user_evidence（视同用户亲口、参与判型派生，但模型可随用户后续作答修订——修订须附新证据重验）；
# 手改落库才是 user（硬保护、模型禁改）。其余字段仍只收原始值，输出对象即类型错误走整轮修复
EVIDENCE_PATHS = {"elements.B.businessGoal", "elements.B.businessBackground", "elements.B.businessValue"}

# 提报侧白话标签（2026-10-27 第三轮拍板，话术红线从提示词扩到系统模板层）：B 区四要素术语在面向提报人的
# 系统硬编码话术里一律换白话；受理侧 PC 与表单字段标签仍用术语。H5 表单副标题用同口径（前端本地副本同步维护）
FIELD_LABEL_PLAIN = {
    "businessGoal": "对组织的好处",
    "businessBackground": "现状和起因",
    "businessValue": "做成后的好处",
    "stakeholders": "相关的人和部门",
}


def _plain_label(field) -> str:
    """面向提报人的要素称呼：B 区四要素用白话，其余沿用表单标签。"""
    return FIELD_LABEL_PLAIN.get(field.key, field.label)


def _numbers(text) -> set:
    """文本中的全部数字（含小数），用于 FR-08 量化事实溯源。"""
    return set(re.findall(r"\d+(?:\.\d+)?", text if isinstance(text, str) else ""))


def merge_structured(model_structured: dict, form: dict, field_sources: dict, standard: Standard | None = None, *, standards=None, grounded_text: str | None = None):
    """合并模型增量到表单。返回 (合并后表单, 字段出处, 选中标准, 原话证据)——evidences 仅含本轮
    B1/B2/B3 以 {"value","evidence"} 对象输出的 evidence 原文（待 process 验真，此处只解析不判断）。"""
    result = deepcopy(form)
    sources = dict(field_sources)
    evidences: dict[str, str] = {}
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
                    # 原话证据解包（2026-10-27 拍板 evidence 机制，第二轮扩至 B2）：B1/B2/B3 允许
                    # {"value","evidence"} 对象——value 照常走合并/校验/数字溯源，evidence 登记后由 process 机械验真决定出处是否升 user_evidence
                    if path in EVIDENCE_PATHS and isinstance(v, dict) and set(v) <= {"value", "evidence"}:
                        evidence = v.get("evidence")
                        if isinstance(evidence, str) and evidence.strip():
                            evidences[path] = evidence
                        v = v.get("value")
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
    # ext.qualityBatchDone 合并一问记账（2026-10-25 三段防线②）由系统写入，filter_form 同样会丢弃：
    # 从旧表单原样保留，否则下一轮守卫读不到标记，「全程只一次」会被破（每轮都再问一遍）
    old_batch_done = (form.get("ext") or {}).get("qualityBatchDone")
    # 容错模式：模型输出的单个非法值（如日期写"本周"）丢弃而非整轮报错；demandTypeCode 已在上方单独严控
    result = filter_form(normalization_standard, result, validate=False)
    if isinstance(pending_splits, list) and pending_splits:
        result.setdefault("ext", {})["pendingSplits"] = pending_splits
    if isinstance(overview, dict) and overview:
        result.setdefault("ext", {})["overview"] = overview
    if isinstance(old_return_reason, dict) and old_return_reason:
        result.setdefault("ext", {})["returnReason"] = old_return_reason
    if old_batch_done:
        result.setdefault("ext", {})["qualityBatchDone"] = old_batch_done
    allowed = {f.field_path for f in normalization_standard.fields}
    sources = {k: v for k, v in sources.items() if k in allowed}
    if "pendingSplits" in (result.get("ext") or {}):
        sources["ext.pendingSplits"] = field_sources.get("ext.pendingSplits") if pending_splits == old_pending else "agent"
    if "overview" in (result.get("ext") or {}):
        sources["ext.overview"] = field_sources.get("ext.overview") if overview == old_overview else "agent"
    return result, sources, selected, evidences


def _evidence_user_voiced(evidence, text: str) -> bool:
    """原话证据验真（2026-10-27 拍板 evidence 机制，取代旧 _user_voiced 整值/分句模糊匹配）：
    归一化（去空白/标点）后 evidence 须为本轮用户消息原文的连续子串、且不少于 4 字——
    纯机械子串校验，不做语义判断（语义归槽是模型的职责，规则层只认「用户是否亲口说过」）。
    短于 4 字的泛词片段（如「可以」「提升」）在原文偶然命中不足为证，一律驳回。
    未附 evidence 或验真失败 → 出处保持 agent，保守判型（宁漏判业务需求不错判），受理侧人工兜底。"""
    def normalize(s) -> str:
        return re.sub(r"[\s，。；、：！？,.;:!?\"'「」『』()（）\-—…·]+", "", str(s or ""))
    needle = normalize(evidence)
    return len(needle) >= 4 and needle in normalize(text)


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
    # 动态必填（2026-10-26 拍板统一必填）：判型归业务需求的 B1~B4 与 A/C/D 必填同权——
    # 「答不出 SKIP 放行」只适用于真选填项，动态必填项答不出按未答好计数，不破提交门槛
    dyn = dynamic_required_keys(standard, form)
    output = []
    for element in curr:
        old = previous.get(element.key)
        changed = get_value(previous_form, fields[element.key].field_path) != get_value(form, fields[element.key].field_path)
        attempts = old.attempts if old else 0
        status, note = element.status, element.note
        if old and old.status == "SKIP" and not changed:
            status, note = "SKIP", "用户选择后续补充"
        elif said_skip and element.key == prev_target and not fields[element.key].required and element.key not in dyn and status != "OK":
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
    # 动态必填（2026-10-26 拍板统一必填）：判型归业务需求的 B1~B4 缺口同样算缺失
    dyn = dynamic_required_keys(standard, form)
    return [e.key for e in standard.elements if (e.required or e.key in dyn) and not e.system and not e.auto_fill and blank(get_value(form, e.field_path))]


def pick_follow_up(standard, elements, *, light: bool = False, form: dict | None = None, can_submit: bool = False,
                   previous_form: dict | None = None):
    """选下一个追问目标。

    追问顺序：A/C/D 必填先问完（用户先补"给谁用、什么场景、痛点、验收"等具体信息），
    然后必问一次 B1 白话问题（2026-10-24 拍板，判型与 B 区解耦）：重量级（standard）需求
    必然涉及组织投入产出，C/D 必填问完后必问一次 businessGoal——触发条件是重量级而非判型标签；
    答不出（不清楚/说不好）SKIP 放行不追问第二次，答出组织理由落库且判型票自然翻转。
    B 区其余要素（背景/价值/干系人）退出追问序列，由受理方分析补齐。
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
    「可以提交」），除急单交付日期这种"承诺型追问"与 B1 白话一问这种"治理型追问"外，不再对
    "有值但被判不够量化/不够具体"的非空必填项主动发问——完成话术承诺了「不太完整的可选项不影响
    提交、由产品经理调研后补」，继续追问即前后矛盾；完善提示留在表单卡片由产品经理自愿补，质量兜底
    走打回机制。MISSING（真空着）不受此限：必填缺口仍需追问或拦提交。

    先补"没有"再修"不好"（2026-10-23 拍板）：追问目标选取拆两遍扫描——第一遍只在 MISSING
    （真空着）必填里按既有顺序选，全部问完才轮到 VAGUE（有值但质检不达标）的质检追问。
    图片解析/大段粘贴会一次性把 D 区验收等填成长文本，原排序下 D 区 VAGUE 质检抢在 B 区与
    紧急程度的空必填前面，AI 先纠结"填得不好"而把"还没填"晾一边；轻重口径不变（light 本就
    只问 MISSING），急单门控插队仍最优先，组内顺序仍按 A/C/D→B1 白话一问→紧急程度最后。

    趁热打铁（2026-10-25 拍板，质量治理三段防线①）：本轮刚答的必填项被判笼统（VAGUE）时
    当轮白话追一次，豁免上面的「可提交即停问」闸门——答案还热乎，当场补一句成本最低，
    且发生在「可以提交」说出口之前，不违背承诺。只认「恰有 1 个必填交互要素值变化」的轮次
    （粘贴/图片解析/模型联动改写等多字段同变时不算，不当场挑刺，遗留项交合并一问兜底）；
    占 attempts 计数，问满（max_attempts 次）放过；只覆盖必填交互项。

    B 区统一必填（2026-10-26 拍板，撤销同日「路径分流」口径）：判型归业务需求（自然过线、
    B1 补票升级或人工定稿）的 B1~B4 转为动态必填——进追问序列（仍按 B 区沉底排序）、占提交门槛、
    趁热打铁/合并一问同权覆盖，B1 不再走「只问一次」白话通道（答不出不放行、话术引导改判用户需求）；
    非业务判型维持 10-24 口径：仅 B1 白话一问，B2~B4 不问。
    """
    by_key = {element.key: element for element in elements}
    field_of = {element.key: element for element in standard.elements}
    dyn = dynamic_required_keys(standard, form or {})
    required = [e.key for e in standard.elements if (e.required or e.key in dyn) and not e.system]
    # 趁热打铁：与上一轮表单快照对比，恰有 1 个必填交互要素（非系统/非自动提取/非底稿）值变化时
    # 视为「本轮刚答」；多字段同变（粘贴/图片解析/联动改写）不算，不当场挑刺
    fresh_key = None
    if previous_form is not None and form is not None:
        changed = [e.key for e in standard.elements
                   if (e.required or e.key in dyn) and not e.system and not e.auto_fill and e.key != "content"
                   and get_value(previous_form, e.field_path) != get_value(form, e.field_path)]
        if len(changed) == 1:
            fresh_key = changed[0]
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
        # B1 白话一问（2026-10-24 拍板）：businessGoal 是唯一保留在追问序列的 B 区要素——
        # 仅真空着（MISSING）且从未问过才选中，问一次即终结（答出落库 / 答不出 SKIP 放行）；
        # 非必填不占提交门槛，can_submit 后仍必问这一次（治理型追问，与急单门控同性质）。
        # 统一必填（2026-10-26 拍板）：判型归业务需求时 B1 已转动态必填（在 dyn 内），
        # 不再走「只问一次」通道，落到下方常规必填逻辑（答不出不放行、计次同 A/C/D）
        if key == "businessGoal" and key not in dyn:
            element = by_key.get(key)
            return element is not None and element.status == "MISSING" and element.attempts < 1
        element = by_key.get(key)
        if element is None or element.status in {"OK", "SKIP"} or element.attempts >= standard.max_attempts:
            return False
        # 可提交后停问软质量：非空（VAGUE）的必填项不再主动追问；MISSING（真空着）仍追问。
        # 豁免（趁热打铁）：本轮刚答的必填项被判笼统时仍当轮追一次，问满已由上方 max_attempts 拦截
        if can_submit and element.status != "MISSING" and not (key == fresh_key and element.status == "VAGUE"):
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
    sequence = ordered + standard.follow_up_order
    # 先补"没有"再修"不好"（2026-10-23 拍板）：第一遍只扫 MISSING（真空着），全部问完才轮到 VAGUE 质检
    for key in sequence:
        if eligible(key) and by_key[key].status == "MISSING":
            return by_key[key]
    for key in sequence:
        if eligible(key):
            return by_key[key]
    return None


# 合并一问（2026-10-25 拍板，质量治理三段防线②）：必填补齐、确认提交弹出前，对遗留的笼统必填项
# 合并白话问一次。与趁热打铁分工：①追「本轮刚答的」单项（答案热乎、逐轮当场），②兜「粘贴/图片解析
# 一次性填入、从没被问过的」遗留项——attempts==0 才点名（被①追过或此前问过的不再点名，避免重复纠缠）。
# 四条硬约束：全程只一次（ext.qualityBatchDone 记账）；最多点名 2 项；明说「不补也能提交」并给
# 「不清楚」出口——是质量提醒而非提交闸门；light 口径不问（承诺最少打扰）。
# 打回补充场景不触发：质量指引由打回说明承担（防线③受理兜底预填），不叠加追问噪音。
def vague_batch_fields(standard: Standard, elements: list, form: dict, *, light: bool, can_submit: bool):
    """返回合并一问要点名的要素定义列表（无需合并时返回 None）。"""
    if light or not can_submit:
        return None
    ext = form.get("ext") or {}
    if ext.get("qualityBatchDone") or _return_reason_of(form):
        return None
    by_key = {element.key: element for element in elements}
    # 动态必填（2026-10-26 拍板统一必填）：判型归业务需求的 B1~B4 与 A/C/D 必填同权参与合并一问
    dyn = dynamic_required_keys(standard, form)
    hits = [field for field in standard.elements
            if (field.required or field.key in dyn) and not field.system and not field.auto_fill and field.key != "content"
            and (element := by_key.get(field.key)) is not None and element.status == "VAGUE" and element.attempts == 0]
    return hits or None


def _vague_batch_reply(fields, form, elements) -> str:
    """合并一问话术（2026-10-25 拍板修订）：按要素生成针对性内容，不再用"能补一句就补一句"万能句——
    1 处：套用该要素 ask_l1 完整模板（自带具体问题 + {snippet} 原文引述 + 「不清楚」出口），
         开头直点名不加"比如"（"比如"是举例用词，只有 1 处时语义错误）；
    2 处：每项一行「原文引述 + 实际缺陷」，末尾统一一个问句（保「每条消息最多一个问句」红线）；
    3 处起：详列前 2 处，其余只点标签名，避免消息过长。
    缺陷说明取当次质检 note、兜底要素 vague_hint（均为白话，与手改重问话术同源）。"""
    by_key = {element.key: element for element in elements}

    def snippet_of(field) -> str:
        value = str(get_value(form, field.field_path) or "").replace("\n", " ").strip()
        return value[:20] + ("…" if len(value) > 20 else "")

    if len(fields) == 1:
        field = fields[0]
        template = field.ask_l1 or field.ask_missing or f"请补充{field.label}，以便把需求记录清楚。"
        return f"还有 1 处写得比较笼统——「{_plain_label(field)}」：{template.replace('{snippet}', snippet_of(field))}不补也能提交。"
    items = []
    for field in fields[:2]:
        element = by_key.get(field.key)
        gap = (element.note if element and element.note else "") or field.vague_hint or "还不够具体"
        items.append(f"「{_plain_label(field)}」：你写的是『{snippet_of(field)}』，{gap}")
    body = "；\n".join(items) + "。"
    if len(fields) > 2:
        rest = "、".join(f"「{_plain_label(field)}」" for field in fields[2:])
        body += f"\n另还有{rest}也偏笼统。"
    return (f"还有 {len(fields)} 处写得比较笼统：\n{body}\n"
            "能各补一句吗？不补也能提交；不好具象化的话，回复「不清楚」就行。")


def user_said_skip(standard, text):
    normalized = re.sub(r"[\s，。！？!?,；;]+", "", text).strip()
    # 跳过必须是整句肯定表达，否定/引用/包含业务内容不算意图。
    return any(normalized in {phrase, "我" + phrase, "请" + phrase, "这项" + phrase, "这个" + phrase, phrase + "吧", "我选择" + phrase} for phrase in standard.skip_phrases)


def quick_replies(standard, target, form: dict | None = None):
    if target is None:
        return []
    field = next(e for e in standard.elements if e.key == target.key)
    result = list(field.options.values()) if field.kind == "enum" else []
    # 动态必填项（2026-10-26 拍板统一必填）与真必填同权：不提供「后续补充」逃逸出口
    if target.attempts >= 1 and not field.required and target.key not in dynamic_required_keys(standard, form or {}):
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
# 不再播「可选项不影响提交、产品经理调研后补」的新手引导长话术；附件/手改/进页面各自给简短行动指引
RETURN_QUOTE_PREFIX = "这条需求之前被打回过，打回原因是「{reason}」。按这个说明改好后就能重新提交。"
_RETURN_DONE = {
    "attachment": "可以点「确认提交」重新提交。",
    "manual": "修改已记录好，可以点「确认提交」重新提交。",
    "enter": "可以点「确认提交」重新提交。",
    "event": "可以点「确认提交」重新提交。",
    "vision": "可以点「确认提交」重新提交。",
    "dialog": "补充的内容已记录好，点下方「确认提交」即可重新提交。",
}
_RETURN_INCOMPLETE = {
    "attachment": "还有几项必填信息没填齐，请在下方表单里补齐后重新提交。",
    "manual": "修改已记录好。还有几项必填信息没填齐，请在下方表单里补齐后重新提交。",
    "vision": "还有几项必填信息没填齐，请在下方表单里补齐后重新提交。",
}
_DRAFT_DONE = {
    "attachment": "可以点「确认提交」提交。",
    "manual": "修改已记录好，可以点「确认提交」提交。",
    "enter": "该填的都齐了，可以提交。",
    "event": "该填的都齐了，可以提交。",
    "vision": "可以点「确认提交」提交。",
}
_DRAFT_INCOMPLETE_ATTACHMENT = "还有几项必填信息没填齐，请在下方表单里补齐后提交。"
# vision 触发前缀（2026-10-22 拍板）：图片来自「让 AI 读懂图片」入口，视觉模型已把图转写为文本
# 走正常抽取整理；前缀告知内容来自图片，误识别可在后续追问中自然纠正（不做单独确认环节）
VISION_PREFIX = "我从图片里读到了内容，先帮你整理了一下。"
# 打回原因引述前缀的固定开头：用于历史消息判定「本补充会话是否已引述过」（只引述一次）
RETURN_QUOTE_MARK = "这条需求之前被打回过，打回原因是"


def _incomplete_reply(*, light: bool, trigger: str, return_reason: str | None) -> str:
    """无追问目标但必填仍缺（追问次数用尽放过）时的兜底指引。"""
    if return_reason:
        return _RETURN_INCOMPLETE.get(trigger, "还有几项必填信息没填齐，请在下方表单里补齐后重新提交。")
    if trigger in ("attachment", "vision"):
        return _DRAFT_INCOMPLETE_ATTACHMENT
    return ("我这边问得差不多了。还差的几项请在下方表单里补齐后提交。" if light
            else "我这边问得差不多了。请在下方表单里把标红星※的必填项补齐后提交。")


def _prefix_return_quote(reply: str, form: dict, *, return_quoted: bool) -> str:
    """打回原因引述（2026-10-20 拍板）：补充会话只引述一次，由调用方按历史消息判定是否首次。
    多段拼接排版（2026-10-23 拍板）：引述段与后文空行分段，不再密不透风一句到底。"""
    if not return_quoted:
        return reply
    reason = _return_reason_of(form)
    if not reason:
        return reply
    return RETURN_QUOTE_PREFIX.format(reason=reason) + "\n\n" + reply


def return_quote_seen(texts) -> bool:
    """历史助理消息里是否已引述过打回原因（2026-10-20 拍板）：补充会话只引述一次。
    打回当刻的完整通知措辞为「这条需求被产品经理打回了」，不含本标记，不会误判。"""
    return any(RETURN_QUOTE_MARK in (text or "") for text in texts)


def _b1_beneficiary(form: dict) -> str:
    """B1 白话一问的受益主语（2026-10-27 测评修订）：C1 已抽出用户角色时用角色名——
    代提场景（提报人替他人提需求）问「除了你自己省事」对象错位读不通；未抽出角色时维持「你自己」。"""
    role = str(get_value(form, "elements.C.userRole") or "").strip()
    return f"{role}自己" if role else "你自己"


def reply_for(standard, target, form, *, light: bool = False, trigger: str = "dialog"):
    if target is None:
        # B 区统一必填（2026-10-26 拍板）：完成判定 = A/C/D 必填 + 判型归业务需求的 B1~B4
        # 动态必填（schema_errors 内自动加码）；非业务判型维持 A/C/D 门槛
        active_zones = {"A", "C", "D"}
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
                        else "都记好了，请核对一下表单。该填的都齐了，可以提交。没填或不太完整的可选项会在表单里标出来，不影响提交，后续产品经理调研后可以补。")
            return _DRAFT_DONE.get(trigger, _DRAFT_DONE["event"])
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
    # B1 统一必填（2026-10-26 拍板）：判型归业务需求时 B1 是硬门槛——问句不带「不清楚也没关系」
    # 放行尾巴（答不出由系统接续改判引导 B1_RECLASSIFY_GUIDE），避免问句承诺与拦截自相矛盾。
    # 2026-10-27 第四轮拍板：首问瘦身——只留问题本体，解释句与改判出口移到答不出时才出现
    if field.key == "businessGoal" and field.key in dynamic_required_keys(standard, form):
        return f"它做出来，除了{_b1_beneficiary(form)}省事，对组织还有啥好处不？"
    if target.attempts >= 1:
        template = field.ask_l2 or field.ask_l1 or field.ask_missing
    else:
        template = anchored_template(standard, field, form) or (field.ask_missing or field.ask_l1 if target.status == "MISSING" else field.ask_l1 or field.ask_missing)
    template = template or f"请补充{field.label}，以便把需求记录清楚。"
    reply = template.replace("{snippet}", snippet).replace("{who}", _b1_beneficiary(form))
    # 动态必填项（2026-10-26 拍板统一必填）与真必填同权：追问不附「后续补充」话术出口
    if target.attempts >= 1 and not field.required and field.key not in dynamic_required_keys(standard, form):
        reply += " 也可以说“后续补充”。"
    return reply


def _quoted_reask(standard: Standard, target: ElementStatus, form: dict) -> str:
    """手改后仍不达标的引述式重问（2026-10-19 拍板）：引述用户刚填的原话+说明差距+追问模板，
    避免「我不是填了吗」的观感；手填值本身是用户权威，只提示不擅改。"""
    field = next(e for e in standard.elements if e.key == target.key)
    value = str(get_value(form, field.field_path) or "").replace("\n", " ").strip()
    snippet = value[:20] + ("…" if len(value) > 20 else "")
    template = field.ask_l2 or field.ask_l1 or field.ask_missing or f"请补充{field.label}，以便把需求记录清楚。"
    template = template.replace("{who}", _b1_beneficiary(form))
    hint = target.note or field.vague_hint or "还不够具体"
    return f"你填的「{field.label}」『{snippet}』我记下了，不过{hint}——" + template


def _display_text(value) -> str:
    """播报用的值文本：list（如干系人）用「、」连接，不把 ['…'] 程序内部格式泄漏给提报人。"""
    if isinstance(value, list):
        return "、".join(str(v) for v in value)
    return str(value).replace("\n", " ").strip()


def _supplement_confirm(standard: Standard, previous_form: dict, merged: dict, prev_target: str | None, *, skip_keys=None) -> str:
    """补充/纠正的引述式确认（2026-10-19 拍板）：列出本轮值发生变化的非当前问题要素并引述
    新值片段请用户确认——与 C3 双锚定话术同风格，AI 听错/抽错时用户能当场发现并纠正。
    系统字段/底稿/标题/类型不做确认（content 为首轮回填、title/类型由系统判定）；
    skip_keys（手改场景=用户手填的要素）已由手改播报告知，不再重复确认。
    播报瘦身（2026-10-25 拍板）：≤2 处保留引述式（防抽错仍靠预览）；≥3 处合并为一句汇总
    （列字段名、不带截断预览）——改名类机械联动动辄波及 5 个字段，逐条罗列+「…」截断
    密不透风，提报人真正想听的只是「改过来了」一句确认，细节看表单卡。"""
    parts: list[tuple[str, str]] = []
    for field in standard.elements:
        if field.system or field.key in ("title", "demandTypeCode", "content") or field.key == prev_target or (skip_keys and field.key in skip_keys):
            continue
        new_v = get_value(merged, field.field_path)
        old_v = get_value(previous_form, field.field_path)
        if not blank(new_v) and old_v != new_v:
            text = _display_text(new_v)
            snippet = text if len(text) <= 20 else text[:20] + "…"
            parts.append((_plain_label(field), snippet))
    if not parts:
        return "好的，补充的我记下了。"
    if len(parts) >= 3:
        labels = "、".join(label for label, _ in parts)
        return f"好的，已按你说的同步更新了 {len(parts)} 处：{labels}。"
    return "；".join(f"「{label}」已更新：{snippet}" for label, snippet in parts) + "。"


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
    if light:
        can_submit = selected is not None and not schema_errors(selected, merged, required=True, required_keys=LIGHT_REQUIRED_KEYS)
    else:
        # B 区统一必填（2026-10-26 拍板）：提交门槛恒为 A/C/D 三区 + 判型归业务需求的 B1~B4 动态必填
        can_submit = selected is not None and not schema_errors(selected, merged, required=True, active_zones={"A", "C", "D"})
    if not prev:
        # 首轮闲聊：只引导不追问（单问题原则）——此前连发引导+标题确认两个问题，用户不知答哪个
        target = None
        reply = CHITCHAT_GREET_FIRST
    else:
        target = pick_follow_up(standard, curr, light=light, form=merged, can_submit=can_submit, previous_form=previous_form)
        reply = CHITCHAT_GUIDE
        if target is not None:
            reply += " " + reply_for(standard, target, merged, light=light)
    return {
        "structured": merged, "fieldSources": field_sources,
        "missing": compute_missing(standard, merged), "elements": [e.model_dump(by_alias=True) for e in curr],
        "askedTarget": target.key if target else None, "canSubmit": can_submit, "ready": can_submit,
        "guidanceComplete": target is None, "qualityComplete": all(e.status == "OK" for e in curr),
        "quickReplies": quick_replies(standard, target, merged), "reply": reply,
        "typeRecognition": recognition, "mode": mode, "granularityHint": None,
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
    merged, field_sources, selected, evidences = merge_structured(output.structured, form, sources, standards=standards, grounded_text=text)
    # 误回填清理推广（2026-10-20 拍板，问题②）：提问/指令与闲聊同口径——纯提问（「什么是需求标题？」）
    # 或流程指令（「提交吧」）并非需求内容，prepare 预填的底稿连来源一起清掉
    if kind in ("question", "command"):
        _clear_echo_backfill(merged, field_sources, text)
    # 未定类型仍使用共用三个质量字段，不暴露 TECH 扩展要素。
    standard = selected or (standards["MATL"] if standards else standard_loader.get("MATL"))
    # FR-01/FR-03 判型（2026-10-27 拍板 evidence 机制；第二轮扩至 B2；第三轮出处三档化）：B1/B2/B3 本轮新写入且随值附了
    # 原话证据的，机械验真（evidence 归一化后为本轮消息原文连续子串、≥4 字）通过 → 出处提升 user_evidence，
    # 参与业务派生；未附/验真失败保持 agent（AI 代拟或来源存疑），保守判型不判业务，受理侧人工兜底。
    # B1/B2/B3 同标准——旧版 B1 无出处检查（「契约必须用户答出」约束不了模型，#50 案例整句灌 B1
    # 蒙对判型），B3 用整值/分句模糊匹配（#49 案例代拟改写打碎子串蒙错出处），统一收编为证据验真。
    # 三档化（修 #60 问题⑤）：验真升档不再等同手改 user 硬保护——用户后续针对该字段作答时模型可并入
    # 新事实修订，附新证据重验保持 user_evidence；不附/验不上则值照常落库、出处降回 agent
    if kind in ("answer", "supplement"):
        for b_path in EVIDENCE_PATHS:
            if (field_sources.get(b_path) in ("agent", "user_evidence") and not blank(get_value(merged, b_path))
                    and _evidence_user_voiced(evidences.get(b_path), text)):
                field_sources[b_path] = "user_evidence"
    # 派生+合并：本轮素材派生与历史生效层级取高（只涨不跌），confirmed 人工定稿最高优先
    recognition = merge_recognition((form.get("ext") or {}).get("typeRecognition"), merged, field_sources)
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
    said_skip = user_said_skip(standard, text) if counting else False
    curr = inherit_and_count(prev, curr, prev_target if counting else None,
                             said_skip,
                             standard=standard, previous_form=previous_form, form=merged,
                             count_keys=manual_keys)
    # B1 答不出（2026-10-24/10-26 拍板）：非业务判型——白话一问答「不清楚/说不好」类 → SKIP 终结该问题，
    # 回复带固定放行书（不追问第二次、不标质量问题、不拦提交、不承诺"后续找谁补"）；
    # 判型归业务需求（B1 已转动态必填）——答不出不放行不打 SKIP（上方已按未答好计次），
    # 回复带改判引导：说不上组织好处可点归类标签改判为用户需求（用户拍板：不设轻量出口）
    dyn = dynamic_required_keys(standard, merged)
    b1_released = said_skip and prev_target == "businessGoal" and "businessGoal" not in dyn
    b1_blocked = said_skip and prev_target == "businessGoal" and "businessGoal" in dyn
    # B 区统一必填（2026-10-26 拍板）：提交门槛 = A/C/D 必填 + 判型归业务需求的 B1~B4 动态必填
    # （schema_errors 内按 typeRecognition 自动加码，不分原生/升级路径）；非业务判型维持 A/C/D 门槛
    if light:
        can_submit = selected is not None and not schema_errors(selected, merged, required=True, required_keys=LIGHT_REQUIRED_KEYS)
    else:
        can_submit = selected is not None and not schema_errors(selected, merged, required=True, active_zones={"A", "C", "D"})
    # 判型播报句整句删除（2026-10-27 第四轮拍板）：「这条需求关系到组织的好处…我帮你填好了」播报
    # 干扰提报人注意力——判型派生/归类标签/白话副标题已承担透明度，不再拼文字播报进回复
    # 追问顺序与提交门槛同口径（2026-10-24 拍板）：A/C/D 必填先问完，再必问一次 B1 白话问题；
    # light 模式只按最小集追问（每项一次）并按最小集放行提交，B 区不问
    target = pick_follow_up(standard, curr, light=light, form=merged, can_submit=can_submit, previous_form=previous_form)
    # 合并一问（三段防线②）：无单项追问目标且必填已齐时，对从没被问过的笼统必填项合并问一次。
    # command（用户明说「提交吧」）尊重明确指令不叠加——确认提交弹窗仍在，合并一问属提醒而非闸门
    batch_fields = vague_batch_fields(standard, curr, merged, light=light, can_submit=can_submit) if target is None and kind != "command" else None
    if batch_fields:
        merged.setdefault("ext", {})["qualityBatchDone"] = now().isoformat(timespec="seconds")
        field_sources["ext.qualityBatchDone"] = "agent"
    granularity = detect_granularity(standard, merged, text)
    # D9 建议方案首次抽取播报（2026-10-12 拍板）：用户设想的候选方案/实现路径此前被五区白名单
    # 静默丢弃，AI 还回「都记好了」构成误导；现在落库后由模板层告知"已记入、供评估、非定案"（模型自述不可靠）。
    # 2026-10-15 调整：播报改引述式（截取原文片段，误归类时用户能认出是哪句、可纠正），并后置到追问之后——
    # 此前抽象概括+前置，用户不知哪句被归为"设想做法"、先听方案再被追问，观感莫名其妙。仅 TECH 标准有 D9，MATL/TRAIN 跳过
    solution_notice = ""
    solution_field = next((f for f in standard.elements if f.key == "proposedSolution"), None)
    if solution_field is not None and blank(get_value(form, solution_field.field_path)) and not blank(get_value(merged, solution_field.field_path)):
        solution_text = get_value(merged, solution_field.field_path).replace("\n", " ").strip()
        snippet = solution_text if len(solution_text) <= 30 else solution_text[:30] + "…"
        # 播报精简（2026-10-23 拍板）：去掉「最终做法由产品和技术评估后再定」尾巴，播报一句到位
        solution_notice = f"你说的「{snippet}」我先记到「建议方案」里，随需求给受理方参考。"
    # command（流程指令，2026-10-19 拍板）：回复聚焦指令本身，不叠加模式播报/方案播报等前缀——
    # 用户说「提交吧」时播「这个需求听起来改动面不小」完全文不对题
    if kind == "command":
        is_return = bool(_return_reason_of(merged))
        if can_submit:
            reply = ("好的，信息都齐了，点下方「确认提交」就能重新提交。" if is_return
                     else "好的，信息都齐了，点下方「提交」按钮就能提报。")
        else:
            missing_labels = [_plain_label(f) for f in standard.elements if f.key in compute_missing(standard, merged)]
            reply = "还差几项必填信息才能提交：" + "、".join(f"「{label}」" for label in missing_labels) + "。"
            if target is not None:
                reply += " " + reply_for(standard, target, merged, light=light, trigger=trigger)
            else:
                reply += " 请在下方表单里补齐后提交。"
    else:
        # 手改要素仍不达标被选中重问时换引述式话术（2026-10-19 拍板）：引原话+说差距，避免「我不是填了吗」
        if target is not None and manual_keys and target.key in manual_keys and target.status == "VAGUE":
            reply = _quoted_reask(standard, target, merged)
        elif batch_fields:
            # 合并一问（三段防线②）：替代「可以提交」完成话术——问完这一轮，下轮自然出完成话术
            reply = _vague_batch_reply(batch_fields, merged, curr)
        else:
            reply = reply_for(standard, target, merged, light=light, trigger=trigger)
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
        # 多段拼接排版（2026-10-23 拍板）：提示/播报类各自空行成段，行动项（追问）沉底——
        # 原单空格首尾相接密不透风，建议方案播报还压在追问后面，重点被淹（vision 场景最典型）
        paragraphs = []
        if granularity:
            paragraphs.append(granularity["hint"])
        if solution_notice:
            paragraphs.append(solution_notice)
        if b1_released:
            # B1 答不出放行书（2026-10-24 拍板）：对用户回答的直接回应，跟在播报类之后、行动项之前
            paragraphs.append(B1_RELEASE)
        if b1_blocked:
            # B1 硬堵改判引导（2026-10-26 拍板统一必填；10-27 第四轮拍板解释与改判出口后置）：
            # 业务需求答不出 B1 不放行，解释必填缘由并给改判用户需求出口
            paragraphs.append(B1_RECLASSIFY_GUIDE)
        paragraphs.append(reply)  # 追问（含意图桥接/模式播报）始终末段，离输入框最近
        reply = "\n\n".join(paragraphs)
        # 打回原因引述（2026-10-20 拍板）：补充会话只引述一次——调用方按历史消息判定是否首次；
        # 打回当刻另有完整通知，重提清除 returnReason 后引述自然消失；模型自述不可靠，引述由模板层保证。
        # command 意图不叠加（「点确认提交重新提交」与引述尾巴语义重复）
        reply = _prefix_return_quote(reply, merged, return_quoted=return_quoted)
    # vision 前缀（2026-10-22 拍板）：告知内容来自图片转写，误识别可在后续追问中自然纠正；
    # 挂在最外层（含 command 分支）——转写文本里若出现「提交吧」等字样被误判指令，前缀同样成立；
    # 与建议方案播报同属"整理播报"（2026-10-23 拍板）：播报恰为首段时空格同段衔接，否则空行自成一段
    if trigger == "vision":
        if solution_notice and kind != "command" and reply.startswith(solution_notice):
            reply = VISION_PREFIX + " " + reply
        else:
            reply = VISION_PREFIX + "\n\n" + reply
    return {
        "structured": merged, "fieldSources": field_sources,
        "missing": compute_missing(standard, merged), "elements": [e.model_dump(by_alias=True) for e in curr],
        "askedTarget": target.key if target else None, "canSubmit": can_submit, "ready": can_submit,
        "guidanceComplete": target is None, "qualityComplete": all(e.status == "OK" for e in curr),
        "quickReplies": quick_replies(standard, target, merged), "reply": reply,
        "typeRecognition": recognition, "mode": mode, "granularityHint": granularity,
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
    curr = list(assess(standard, form, light=light))
    prev_elements = [ElementStatus.model_validate(e) for e in ((previous or {}).get("elements") or [])]
    prev_structured = (previous or {}).get("structured") or {}
    curr = inherit_and_count(prev_elements, curr, None, False, standard=standard,
                             previous_form=prev_structured, form=form,
                             count_keys=changed_keys)
    if light:
        can_submit = not schema_errors(standard, form, required=True, required_keys=LIGHT_REQUIRED_KEYS)
    else:
        # B 区统一必填（2026-10-26 拍板）：提交门槛恒为 A/C/D 三区 + 判型归业务需求的 B1~B4 动态必填
        can_submit = not schema_errors(standard, form, required=True, active_zones={"A", "C", "D"})
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
    target = pick_follow_up(standard, curr, light=light, form=form, can_submit=can_submit, previous_form=prev_structured)
    # 合并一问（三段防线②）：对话外事件（手改/附件/进页）把必填补齐时同样兜底问一次；
    # extUpdates 由调用方落库 demand.ext——本函数为纯规则接续，不直接碰库
    batch_fields = vague_batch_fields(standard, curr, form, light=light, can_submit=can_submit) if target is None else None
    if target is not None and changed_keys and target.key in changed_keys and target.status == "VAGUE":
        reply = _quoted_reask(standard, target, form)
    elif batch_fields:
        reply = _vague_batch_reply(batch_fields, form, curr)
    else:
        reply = reply_for(standard, target, form, light=light, trigger=trigger)
    # 打回原因引述（2026-10-20 拍板）：补充会话只引述一次，由调用方按历史消息判定 return_quoted
    reply = _prefix_return_quote(reply, form, return_quoted=return_quoted)
    return {
        "reply": reply,
        "askedTarget": target.key if target else None,
        "elements": [e.model_dump(by_alias=True) for e in curr],
        "canSubmit": can_submit, "guidanceComplete": target is None,
        # 合并一问不再附带「不清楚」快捷回复 chip（2026-10-25 拍板）：话术里已有文字出口，
        # 不再多占一个按钮；batch 轮 target=None 时 quick_replies 天然返回空
        "quickReplies": quick_replies(standard, target, form),
        "extUpdates": {"qualityBatchDone": now().isoformat(timespec="seconds")} if batch_fields else None,
    }
