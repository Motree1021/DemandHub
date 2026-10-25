import hashlib
import json
import logging
import shutil
from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.mysql import insert

from app.agent.policy import process, resume_follow_up, return_quote_seen
from app.config import get_settings
from app.core.errors import BizError, ErrorCode
from app.core.result import encode
from app.core.statemachine import engine
from app.db.models import (
    AgentDraft,
    AgentMessage,
    AgentSession,
    Assignment,
    Comment,
    Demand,
    DemandAttachment,
    DemandChangeLog,
    DemandRelation,
    DemandTransitionLog,
    EffortLog,
    Notification,
    PromptVersion,
    RagVector,
    Review,
    Solution,
    User,
    now,
)
from app.services import session_service
from app.services.demand_no import next_no
from app.standards import rules
from app.standards.loader import ensure_snapshot
from app.standards.loader import get as get_standard
from app.standards.migration_map import elements_from_legacy, legacy_from_elements
from app.standards.schema import Standard

logger = logging.getLogger(__name__)

TOP_FIELDS = {"title": "title", "demandTypeCode": "demand_type_code", "content": "content",
              "urgency": "urgency", "expectDeliveryAt": "expect_delivery_at"}

# ext 保留位：判型结果（FR-03）、实例切分建议（BR-T11，一期打标）、轻重模式（2026-10-11 方案②）、
# 打回原因（2026-10-11 方案③ NEED_INFO 闭环）、合并一问记账（2026-10-25 三段防线②）不走标准要素白名单，全程保留
RESERVED_EXT_KEYS = ("typeRecognition", "pendingSplits", "overview", "mode", "returnReason", "qualityBatchDone")


def fingerprint(value: dict) -> str:
    return hashlib.sha256(json.dumps(encode(value), sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":")).encode()).hexdigest()


def form_of(demand: Demand) -> dict:
    form = {"title": demand.title, "demandTypeCode": demand.demand_type_code,
            "content": demand.content, "urgency": demand.urgency,
            "expectDeliveryAt": demand.expect_delivery_at.isoformat() if demand.expect_delivery_at else None,
            "ext": dict(demand.ext or {})}
    # 存量草稿 elements 为空时按迁移映射回退读 ext（概念模型 §6.2，无需数据回填）
    form["elements"] = deepcopy(demand.elements) if demand.elements is not None else elements_from_legacy(demand.ext)
    return form


def serialize_change_log(row: DemandChangeLog) -> dict:
    return {"id": row.id, "fieldKey": row.field_key, "oldValue": row.old_value, "newValue": row.new_value,
            "source": row.source, "changedBy": row.changed_by, "createdAt": encode(row.created_at)}


def serialize_demand(demand: Demand, change_logs: list | None = None, assignee_name: str | None = None) -> dict:
    result = {"id": demand.id, "demandNo": demand.demand_no, **form_of(demand),
              "subtypeCode": demand.subtype_code, "revision": demand.revision,
              "fieldSources": demand.field_sources or {}, "status": demand.status,
              "quality": demand.quality or [], "submitterId": demand.submitter_id,
              "submitterName": demand.submitter_name, "submitterDept": demand.submitter_dept,
              "channel": demand.channel, "sessionId": demand.session_id,
              "standardVersionId": demand.standard_version_id, "qualityContentHash": demand.quality_content_hash,
              "changeLogs": change_logs or [],
              "submittedAt": demand.submitted_at, "closedAt": demand.closed_at,
              "closeReason": demand.close_reason, "createdAt": demand.created_at, "updatedAt": demand.updated_at,
              # P2 流转字段
              "assigneeId": demand.assignee_id, "assigneeName": assignee_name,
              "onHold": demand.hold_snapshot_status is not None,
              "holdSnapshotStatus": demand.hold_snapshot_status, "holdReason": demand.hold_reason,
              "confirmedAt": demand.confirmed_at, "doneAt": demand.done_at,
              "qualityScore": demand.quality_score, "satisfactionScore": demand.satisfaction_score,
              "splitFromId": demand.split_from_id, "splitGroupId": demand.split_group_id}
    return encode(result)


async def assignee_names_map(db, demands: list[Demand]) -> dict[int, str]:
    """批量取处理人姓名（列表序列化避免 N+1）。"""
    ids = {d.assignee_id for d in demands if d.assignee_id}
    if not ids:
        return {}
    from app.db.models import User
    rows = (await db.execute(select(User.id, User.name).where(User.id.in_(ids)))).all()
    return dict(rows)


async def change_logs_map(db, demand_ids: list[int]) -> dict[int, list]:
    """按需求 id 批量取变更留痕（E7），避免列表 N+1。"""
    if not demand_ids:
        return {}
    rows = (await db.execute(select(DemandChangeLog).where(DemandChangeLog.demand_id.in_(demand_ids)).order_by(DemandChangeLog.id))).scalars().all()
    result: dict[int, list] = {demand_id: [] for demand_id in demand_ids}
    for row in rows:
        result.setdefault(row.demand_id, []).append(serialize_change_log(row))
    return result


async def serialize_with_logs(db, demand: Demand) -> dict:
    assignee_name = (await assignee_names_map(db, [demand])).get(demand.assignee_id)
    return serialize_demand(demand, (await change_logs_map(db, [demand.id]))[demand.id], assignee_name)


def normalized(form: dict) -> tuple[dict, Standard | None]:
    type_code = form.get("demandTypeCode")
    std = get_standard(type_code) if type_code else None
    try:
        result = rules.filter_form(std, form)
        for key in RESERVED_EXT_KEYS:
            if (form.get("ext") or {}).get(key) is not None:
                result.setdefault("ext", {})[key] = form["ext"][key]
        errors = rules.schema_errors(std, result)
        if errors:
            raise ValueError(errors[0])
        for path, value in paths(result).items():
            if rules.blank(value):
                rules.set_value(result, path, None)
        return result, std
    except ValueError as exc:
        raise BizError(ErrorCode.PARAM_INVALID, str(exc)) from None


def paths(form: dict) -> dict:
    result = {k: v for k, v in form.items() if k not in ("ext", "elements")}
    result.update({"ext." + k: v for k, v in (form.get("ext") or {}).items()})
    for zone, values in (form.get("elements") or {}).items():
        result.update({f"elements.{zone}.{k}": v for k, v in (values or {}).items()})
    return result


def merge_elements(base: dict | None, patch: dict | None) -> dict:
    """elements 按区深合并（区→要素两层）。"""
    result = {zone: dict(values or {}) for zone, values in (base or {}).items()}
    for zone, values in (patch or {}).items():
        result.setdefault(zone, {}).update(values or {})
    return result


def assign(demand: Demand, form: dict, sources: dict) -> None:
    for key, attr in TOP_FIELDS.items():
        value = form.get(key)
        if key == "expectDeliveryAt":
            value = date.fromisoformat(value) if value else None
        setattr(demand, attr, value)
    if "elements" in form:
        # TECH 五区表单：elements 主写，ext 保留兼容副本（概念模型 §6.2 双写过渡）+ 保留位
        demand.elements = {zone: dict(values or {}) for zone, values in (form.get("elements") or {}).items()}
        reserved = {k: deepcopy(form["ext"][k]) for k in RESERVED_EXT_KEYS if k in (form.get("ext") or {})}
        demand.ext = {**legacy_from_elements(demand.elements), **reserved}
        demand.subtype_code = (demand.elements.get("A") or {}).get("techSubtype")
    else:
        # MATL/TRAIN ext 表单（未升级五区）
        demand.ext = dict(form.get("ext") or {})
        demand.elements = None
        demand.subtype_code = demand.ext.get("techSubtype")
    demand.field_sources = {path: source for path, source in sources.items() if path in paths(form)}


async def get_owned_draft(db, user, demand_id: int, for_update: bool = False) -> Demand:
    statement = select(Demand).where(Demand.id == demand_id, Demand.submitter_id == user.id)
    if for_update:
        statement = statement.with_for_update()
    demand = (await db.execute(statement.execution_options(populate_existing=True))).scalar_one_or_none()
    if demand is None:
        raise BizError(ErrorCode.DEMAND_NOT_FOUND)
    return demand


def assert_editable(demand: Demand, expected_revision: int) -> None:
    # NEED_INFO（管理员打回待补充，方案③）与 DRAFT 同为可编辑态：对话/表单补填后重提
    if demand.status not in ("DRAFT", "NEED_INFO"):
        raise BizError(ErrorCode.ILLEGAL_STATE_TRANSITION)
    if demand.revision != expected_revision:
        raise BizError(ErrorCode.CONFLICT)


def write_change_logs(db, demand: Demand, before: dict, after: dict, sources: dict, user_id: int) -> None:
    """要素级修改留痕（FR-06/E7）：before/after 均为规范化表单，逐路径比对，有变化写一行。"""
    for path, new in paths(after).items():
        # ext.overview 是 AI 每轮重写的派生摘要、ext.qualityBatchDone 是合并一问的内部记账标记，
        # 留痕会刷噪音；原文与要素留痕已足够追溯
        if path in ("ext.overview", "ext.qualityBatchDone"):
            continue
        old = rules.get_value(before, path)
        if old == new:
            continue
        db.add(DemandChangeLog(demand_id=demand.id, field_key=path,
                               old_value=encode(old), new_value=encode(new),
                               source=sources.get(path) or "user", changed_by=user_id))


# 手工改要素播报的兜底标签（标准要素优先取 yaml label，措辞与 tech.yaml 一致）
TOP_LABELS = {"title": "需求标题", "demandTypeCode": "需求类型", "content": "原始提报文本",
              "urgency": "紧急程度", "expectDeliveryAt": "期望交付时间"}


def _display_value(element, value) -> str:
    """播报值转可读文字：enum 转标签、列表逐项拼接，其余原样。"""
    if value is None:
        return ""
    if isinstance(value, list):
        return "、".join(_display_value(element, item) for item in value)
    if isinstance(value, str) and element is not None and element.kind == "enum":
        return element.options.get(value, value)
    return str(value)


def _clip_text(text: str, limit: int = 50) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[:limit] + "…"


def change_items(std: Standard | None, before: dict, after: dict) -> list[dict]:
    """手工改要素的结构化播报数据（FR-06）：与 write_change_logs 同源 diff，保留位不播报。"""
    elements = {item.field_path: item for item in std.elements} if std else {}
    items = []
    for path, new in paths(after).items():
        if path in {f"ext.{key}" for key in RESERVED_EXT_KEYS}:
            continue
        old = rules.get_value(before, path)
        if old == new:
            continue
        element = elements.get(path)
        label = element.label if element else TOP_LABELS.get(path, path.rsplit(".", 1)[-1])
        key = element.key if element else path
        old_text, new_text = _clip_text(_display_value(element, old)), _clip_text(_display_value(element, new))
        if rules.blank(new):
            items.append({"action": "clear", "key": key, "label": label, "old": old_text, "new": ""})
        elif rules.blank(old):
            items.append({"action": "fill", "key": key, "label": label, "old": "", "new": new_text})
        else:
            items.append({"action": "update", "key": key, "label": label, "old": old_text, "new": new_text})
    return items


def describe_changes(items: list[dict]) -> str:
    """播报纯文本（导出/回放兜底）；前端优先按 payload 渲染卡片。"""
    lines = []
    for label, old, new, action in ((item["label"], item["old"], item["new"], item["action"]) for item in items):
        if action == "clear":
            lines.append(f"你已手动清空了「{label}」")
        elif action == "fill":
            lines.append(f"你已手动填写了「{label}」：{new}")
        else:
            lines.append(f"你已手动更新了「{label}」：由「{old}」改为「{new}」")
    return "\n".join(lines)


_TYPE_CONFIRM_LABELS = {"business": "业务需求", "user": "用户需求", "function": "功能需求"}


def _describe_type_change(before: dict | None, after: dict | None) -> str | None:
    """归类改判播报文案（2026-10-20 拍板）：只关注 confirmed——提报人确认/改判/恢复 AI 判断。
    判型与 B 区解耦（2026-10-24 拍板）：判型标签仅作归类展示，不再驱动 B 区必填门槛，
    播报不再宣称「纳入必填」；AI 侧的 judgedType/置信度变化归对话链路播报，不在此重复。"""
    before_confirmed = before.get("confirmed") if isinstance(before, dict) else None
    after_confirmed = after.get("confirmed") if isinstance(after, dict) else None
    if before_confirmed == after_confirmed:
        return None
    if after_confirmed is None:
        return "你已恢复由 AI 自动判断需求归类，我会按对话内容重新分析。"
    label = _TYPE_CONFIRM_LABELS.get(after_confirmed, after_confirmed)
    return f"你已确认为{label}。"


def with_legacy_elements(payload: dict) -> dict:
    """旧六要素 ext 手填兼容（P4 前 H5 表单）：映射为五区 elements，显式 elements 同 key 优先。"""
    legacy = elements_from_legacy(payload.get("ext"))
    if legacy:
        payload = {**payload, "elements": merge_elements(legacy, payload.get("elements"))}
    return payload


async def create_draft(db, user, payload: dict) -> Demand:
    form, _ = normalized(with_legacy_elements(payload))
    supplied_sources = payload.get("fieldSources") or {}
    sources = {}
    for path, value in paths(form).items():
        source = supplied_sources.get(path)
        sources[path] = "default" if source == "default" and path == "demandTypeCode" else "user"
        if rules.blank(value) and source is None:
            sources.pop(path, None)
    digest = fingerprint(payload)
    # 草稿落库即写提报人快照（2026-10-20 拍板）：管理端草稿可见提报人；submit 时仍会按最新资料刷新
    statement = insert(Demand).values(submitter_id=user.id, submitter_name=user.name,
        submitter_dept=user.dept_name, client_request_id=payload["clientRequestId"],
        create_request_hash=digest, ext={}, field_sources={}, revision=0, status="DRAFT", channel=user.channel)
    await db.execute(statement.on_duplicate_key_update(id=Demand.id))
    demand = (await db.execute(select(Demand).where(Demand.submitter_id == user.id,
        Demand.client_request_id == payload["clientRequestId"]).with_for_update())).scalar_one()
    if demand.create_request_hash != digest:
        raise BizError(ErrorCode.CONFLICT, "clientRequestId 已用于不同的草稿输入")
    # 重放不能覆盖后来编辑的草稿。
    if demand.title is None and demand.demand_type_code is None and demand.content is None and not demand.ext and demand.revision == 0:
        assign(demand, form, sources)
        await db.flush()
    return demand


async def update_draft(db, user, demand_id: int, payload: dict) -> Demand:
    demand = await get_owned_draft(db, user, demand_id, for_update=True)
    assert_editable(demand, payload["expectedRevision"])
    before = form_of(demand)
    patch = with_legacy_elements({k: v for k, v in payload.items() if k in TOP_FIELDS or k in ("ext", "elements")})
    # ext.overview 概述只归 AI 派生链路（guide/后台重写）所有：H5 每次整表单回传带旧概述，
    # 不忽略会把后台刚重写的新概述覆盖回旧值；ext.mode 轻重判定同理只归 AI 判定链路（2026-10-11 方案②）；
    # ext.returnReason 只归管理员打回链路（方案③），提报人回传不得篡改打回原因
    if isinstance(patch.get("ext"), dict):
        patch["ext"] = {k: v for k, v in patch["ext"].items() if k not in ("overview", "mode", "returnReason")}
    merged = {**before, **patch, "ext": {**before["ext"], **(patch.get("ext") or {})}}
    old_recognition = before["ext"].get("typeRecognition")
    new_recognition = (patch.get("ext") or {}).get("typeRecognition")
    if isinstance(old_recognition, dict) and isinstance(new_recognition, dict):
        # 判型确认/改判按层合并，只更新给定键，不丢置信度与依据
        merged["ext"]["typeRecognition"] = {**old_recognition, **new_recognition}
    if "elements" in patch:
        merged["elements"] = merge_elements(before["elements"], patch.get("elements"))
    # B1 落库即判业务（2026-10-24 拍板）：手改补齐 B1 与对话答出同口径翻转（对话链路在 policy.process 内处理）；
    # 放在 elements 深合并之后——merged 须为完整新表单才能正确判定「空→有」
    promoted = rules.promote_business_on_b1(merged["ext"].get("typeRecognition"), before, merged)
    if promoted is not None:
        merged["ext"]["typeRecognition"] = promoted
    form, std = normalized(merged)
    sources = dict(demand.field_sources or {})
    requested = payload.get("fieldSources") or {}
    for path, value in paths(patch).items():
        # 显式改值/清空均是手改；保留未改变的已有来源，客户端不能降级 user。
        if sources.get(path) == "user" or requested.get(path) == "user" or value != rules.get_value(before, path):
            sources[path] = "user"
        elif path not in sources and not rules.blank(value):
            sources[path] = "user"
    assign(demand, form, sources)
    write_change_logs(db, demand, before, form, sources, user.id)
    notified = False
    changed_keys: set[str] = set()
    if payload.get("notifyChanges") and demand.session_id is not None:
        # 手工改要素播报（FR-06）：与留痕同源 diff 写入会话；结构化 payload 供前端渲染卡片
        items = change_items(std, before, form)
        if items:
            await session_service.append(db, demand.session_id, "ASSISTANT", describe_changes(items),
                                          {"kind": "manualChange", "changes": items})
            notified = True
            changed_keys = {item["key"] for item in items}
    demand.revision += 1
    demand.updated_at = now()
    if notified:
        # 手改后的流程接续（2026-10-19 拍板问题②+合并方案）：AI 不停在播报——
        # 手填长文本先过模型做跨要素抽取归位（失败静默降级），规则层续上下一追问/完成话术
        await append_conversation_follow_up(db, user, demand, changed_keys=changed_keys, trigger="manual")
    # 归类改判播报+接续（2026-10-20 拍板，与手改要素/口径改判同规则）：typeRecognition 是保留键
    # 不入 change_items，独立检测 confirmed 变化——判型影响 B 区必填门槛，当场重算质量卡：
    # 有缺口按新门槛追问、要素齐备出「确认提交」快照；手改要素已接续过的快照已含新归类口径，不重复注入
    type_notice = _describe_type_change((before.get("ext") or {}).get("typeRecognition"), (form.get("ext") or {}).get("typeRecognition"))
    if type_notice and demand.session_id is not None:
        await session_service.append(db, demand.session_id, "ASSISTANT", type_notice, {"kind": "typeChange"})
        if not notified:
            await append_conversation_follow_up(db, user, demand)
    await db.flush()
    return demand


def _manual_extract_texts(std: Standard | None, form: dict, changed_keys: set[str]) -> list[tuple[str, str]]:
    """本轮手填的文本类要素（≥10 字）：短字段/枚举/日期/清空几乎不含跨要素信息，不触发模型抽取。"""
    if std is None:
        return []
    fields = {e.key: e for e in std.elements}
    result = []
    for key in sorted(changed_keys):
        field = fields.get(key)
        if field is None or field.kind != "text":
            continue
        value = str(rules.get_value(form, field.field_path) or "").strip()
        if len(value) >= 10:
            result.append((field.label, value))
    return result


async def _follow_up_with_model(user, std: Standard, form: dict, sources: dict, previous: dict | None,
                                history: list, manual_texts: list[tuple[str, str]], changed_keys: set[str],
                                *, trigger: str = "manual", return_quoted: bool = True) -> dict:
    """手改触发的补充式抽取（2026-10-19 拍板）：手填长文本交模型做跨要素抽取归位，
    意图固定为补充（supplement）——手改就是补充，不需要模型再判意图；
    走 process 流水线：来源保护（手填字段不被改写）→ 抽取合并 → 引述确认（跳过手填项）→ 接续。
    trigger/return_quoted（2026-10-20 拍板）：完成话术与打回引述按触发动作/一次性口径透传。"""
    from app.agent.guide import build_prompt
    from app.agent.llm_client import get_llm_client
    from app.agent.schemas import ElementStatus, Intent, parse_model_output
    llm = get_llm_client()
    if not llm.available():
        return None
    prev_elements = [ElementStatus.model_validate(e) for e in ((previous or {}).get("elements") or [])]
    previous_form = deepcopy((previous or {}).get("structured") or {})
    chat_history = [{"role": "user" if m.role == "USER" else "assistant", "content": m.content}
                    for m in history if m.role in {"USER", "ASSISTANT"}]
    text = "我在表单里手动写了这些内容：" + "；".join(f"「{label}」{value}" for label, value in manual_texts)
    messages, _, registry, _ = build_prompt(form, sources, prev_elements, None, chat_history, text)
    event = await llm.complete_json(messages)
    output = parse_model_output(event.raw)
    output = output.model_copy(update={"intent": Intent(kind="supplement")})
    standards = {code: standard for code, standard in registry.items()}
    return process(output, form, sources, prev_elements, None, previous_form, text,
                   standards=standards, manual_keys=changed_keys,
                   trigger=trigger, return_quoted=return_quoted)


async def append_conversation_follow_up(db, user, demand: Demand, *, changed_keys: set[str] | None = None,
                                        trigger: str = "event", quote_return: bool | None = None) -> None:
    """对话外事件（手改要素/附件回执，2026-10-19 拍板）后的流程接续：
    手填长文本先过模型做跨要素抽取归位（补充式意图，手填字段受来源保护不被改写；
    模型不可用/失败静默降级为规则接续），规则层续上下一追问/完成话术，
    并同步 agent_session.asked_target——AI 不停在播报，对话不中断。
    trigger（2026-10-20 拍板）：attachment/manual/enter/event——决定完成话术口径；
    打回原因引述按历史消息判定，本补充会话只引述一次；quote_return 显式覆盖（打回当刻已有
    完整通知，开场快照传 False 不重复引述）。
    payload 结构对齐对话结果消息（demandId/sessionId/revision/elements/structured），
    供前端质量清单回放、并被 guide.prepare 认作下一轮 previous 快照（无 kind 字段）。"""
    if demand.session_id is None:
        return
    form = form_of(demand)
    std = get_standard(demand.demand_type_code) if demand.demand_type_code else get_standard("MATL")
    history = await session_service.messages(db, user, demand.session_id)
    # 上一轮表单快照只认真正的对话结果消息：手改播报/附件回执/打回播报/口径改判播报/归类改判播报不是模型产物
    previous = next((m.structured_payload for m in reversed(history) if m.role == "ASSISTANT"
                     and m.structured_payload
                     and (m.structured_payload or {}).get("kind") not in ("manualChange", "attachmentReceipt", "returnNotice", "modeChange", "typeChange")), None)
    # 打回原因引述只引述一次（2026-10-20 拍板）：查历史助理消息；打回当刻通知措辞不含引述标记，不算已引述
    return_quoted = (not return_quote_seen([m.content for m in history if m.role == "ASSISTANT"])) if quote_return is None else quote_return
    keys = changed_keys or set()
    follow = None
    manual_texts = _manual_extract_texts(std, form, keys)
    if manual_texts:
        try:
            follow = await _follow_up_with_model(user, std, form, dict(demand.field_sources or {}),
                                                 previous, history, manual_texts, keys,
                                                 trigger=trigger, return_quoted=return_quoted)
        except Exception as exc:
            logger.warning("手改跨要素抽取失败，降级为规则接续 demand=%s %s: %s", demand.id, type(exc).__name__, exc)
            follow = None
    if follow is not None:
        # 抽取归位落库：手填字段 user 来源保护不动，抽中的其他要素 agent 来源；与手改同一 revision（一次保存动作）
        extracted, extracted_sources = follow["structured"], follow["fieldSources"]
        if extracted != form:
            write_change_logs(db, demand, form, extracted, extracted_sources, user.id)
            assign(demand, extracted, extracted_sources)
            demand.updated_at = now()
        follow = {"reply": follow["reply"], "askedTarget": follow["askedTarget"],
                  "elements": follow["elements"], "canSubmit": follow["canSubmit"],
                  "guidanceComplete": follow["guidanceComplete"], "quickReplies": follow["quickReplies"]}
        form = extracted
    else:
        follow = resume_follow_up(std, form, previous, changed_keys=keys,
                                  trigger=trigger, return_quoted=return_quoted)
        # 合并一问记账（2026-10-25 三段防线②）：纯规则接续路径不经 apply_agent_patch，
        # ext.qualityBatchDone 在此直接落库并同步进播报快照，保证「全程只一次」
        if follow.get("extUpdates"):
            ext = dict(demand.ext or {})
            ext.update(follow["extUpdates"])
            demand.ext = ext
            form = {**form, "ext": ext}
    # payload 须含 fieldSources（2026-10-21 修复）：前端回放时按对话结果结构整体应用表单，
    # 缺 fieldSources 会把 form.fieldSources 覆盖成 undefined，下一次手改要素即抛 TypeError
    await session_service.append(db, demand.session_id, "ASSISTANT", follow["reply"], {
        "demandId": demand.id, "sessionId": demand.session_id, "revision": demand.revision,
        "reply": follow["reply"],
        "elements": follow["elements"], "structured": form,
        "fieldSources": dict(demand.field_sources or {}),
        "askedTarget": follow["askedTarget"], "canSubmit": follow["canSubmit"],
        "guidanceComplete": follow["guidanceComplete"], "quickReplies": follow["quickReplies"],
    })
    agent_session = (await db.execute(select(AgentSession).where(AgentSession.id == demand.session_id))).scalar_one_or_none()
    if agent_session is not None:
        agent_session.asked_target = follow["askedTarget"]


# 管理端改要素（2026-10-13 拍板）：处理人/管理员在需求详情页双击编辑 B/C/D 要素。
# 与提报人 update_draft 分线——不走草稿态校验；终态禁改、乐观锁、要素留痕、质量重算口径与提交链路一致
ADMIN_EDIT_FORBID_STATUSES = ("DONE", "CLOSED")


async def update_elements(db, user, demand_id: int, payload: dict) -> dict:
    from app.services.flow_service import can_view_demand
    demand = await db.get(Demand, demand_id, with_for_update=True)
    if demand is None or not can_view_demand(user, demand):
        raise BizError(ErrorCode.DEMAND_NOT_FOUND)
    if demand.status in ADMIN_EDIT_FORBID_STATUSES:
        raise BizError(ErrorCode.BIZ_ERROR, "终态需求不可再修改要素")
    if demand.revision != payload["expectedRevision"]:
        raise BizError(ErrorCode.CONFLICT)
    before = form_of(demand)
    patch_elements = payload.get("elements") or {}
    form, std = normalized({**before, "elements": merge_elements(before["elements"], patch_elements)})
    sources = dict(demand.field_sources or {})
    for path, value in paths({"elements": patch_elements}).items():
        if value != rules.get_value(before, path):
            sources[path] = "user"
    assign(demand, form, sources)
    write_change_logs(db, demand, before, form, sources, user.id)
    if std is not None:
        light = rules.demand_mode(form) == "light"
        demand.quality = [{"key": item.key, "status": item.status, "note": item.note}
                          for item in rules.assess(std, form, light=light)]
    demand.revision += 1
    demand.updated_at = now()
    await db.flush()
    return {"demand": await serialize_with_logs(db, demand), "quality": demand.quality or []}


async def apply_agent_patch(db, user, demand, *, expected_revision: int, patch: dict, field_sources: dict | None = None) -> Demand:
    assert_editable(demand, expected_revision)
    if demand.submitter_id != user.id:
        raise BizError(ErrorCode.DEMAND_NOT_FOUND)
    before = form_of(demand)
    sources = dict(demand.field_sources or {})
    # 必须深拷贝：set_value 沿嵌套 dict 就地写入，浅拷贝会污染 before，导致来源比对与 change_log diff 失效
    merged = deepcopy(before)
    for path, value in paths(patch).items():
        if sources.get(path) == "user" or rules.blank(value):
            continue
        rules.set_value(merged, path, value)
        # 策略层判定为 user 的来源（如 A8 原文回填）优先于值比对
        if (field_sources or {}).get(path) == "user":
            sources[path] = "user"
        elif value != rules.get_value(before, path):
            sources[path] = "agent"
    form, _ = normalized(merged)
    assign(demand, form, sources)
    write_change_logs(db, demand, before, form, sources, user.id)
    demand.revision += 1
    demand.updated_at = now()
    await db.flush()
    return demand


async def return_demand(db, admin_user, demand_id: int, reason: str) -> Demand:
    """管理员打回待补充（2026-10-11 方案③）：SUBMITTED → NEED_INFO。

    - 打回原因存 ext.returnReason（保留位），并写 change_log（status/ext.returnReason 两行，source=admin）
    - 提报口径保持原样（2026-10-20 拍板）：不再强制升 standard——打回原因可能只是一处小补充，
      轻量需求仍按 4 项最小集补填重提，完整/轻量由提报人自主判断
    - 会话重开 ACTIVE 并注入一条引述打回原因的播报消息（kind=returnNotice，不参与质量快照回放）
    """
    demand = (await db.execute(select(Demand).where(Demand.id == demand_id).with_for_update())).scalar_one_or_none()
    if demand is None:
        raise BizError(ErrorCode.DEMAND_NOT_FOUND)
    # 类型权限（2026-10-16 拍板）：经理打回也受 type_scope 约束（ADMIN 直通）
    from app.services import role_service
    role_service.assert_type_allowed(admin_user, demand.demand_type_code)
    if demand.status != "SUBMITTED":
        raise BizError(ErrorCode.ILLEGAL_STATE_TRANSITION, "仅已提交的需求可打回")
    reason_text = reason.strip()
    ext = dict(demand.ext or {})
    ext["returnReason"] = {"reason": reason_text, "returnedBy": admin_user.name,
                           "returnedAt": now().isoformat(timespec="seconds")}
    demand.ext = ext
    # P2 硬约束：打回经状态机 RETURN 事件（SUBMITTED → NEED_INFO）并写 transition_log
    await engine.transition(db, demand_id, "RETURN", admin_user, comment=reason_text)
    db.add(DemandChangeLog(demand_id=demand.id, field_key="status", old_value="SUBMITTED", new_value="NEED_INFO",
                           source="admin", changed_by=admin_user.id))
    db.add(DemandChangeLog(demand_id=demand.id, field_key="ext.returnReason", old_value=None,
                           new_value=encode(ext["returnReason"]), source="admin", changed_by=admin_user.id))
    if demand.session_id is not None:
        session = (await db.execute(select(AgentSession).where(AgentSession.id == demand.session_id).with_for_update())).scalar_one()
        if session.demand_id != demand.id:
            raise BizError(ErrorCode.CONFLICT, "草稿与会话关联不一致")
        session.status = "ACTIVE"
        notice = (f"这条需求被产品经理打回了，需要补充信息后重新提交。\n打回原因：{reason_text}\n"
                  "可以直接回复我来补充，我会帮你把缺的内容问齐；也可以点开「需求要素表单」卡片逐项修改。")
        await session_service.append(db, demand.session_id, "ASSISTANT", notice,
                                     {"kind": "returnNotice", "reason": reason_text})
        # 打回开场快照（2026-10-20 拍板方案A）：纯规则按 12 项完整口径重算质量快照，落库为正式对话
        # 结果消息（带打回后 revision）——修复「状态机流转 bump
        # revision 甩开最后快照 → 前端回放守卫拦截 → 重进提报页按钮/清单/步骤全丢」的引导断链：
        # 重进即见缺口追问，补齐后「确认提交」随新一轮快照自然出现。
        # 打回原因不再前置引述（上一条 returnNotice 已完整告知，2026-10-20 拍板）；
        # 提报人回来后第一次操作时由 return_quote_seen 自动判定引述一次
        owner = await db.get(User, demand.submitter_id)
        if owner is not None:
            await append_conversation_follow_up(db, owner, demand, trigger="enter", quote_return=False)
    await db.flush()
    return demand


async def change_mode(db, user, demand_id: int, expected_revision: int, level: str) -> Demand:
    """提报口径改判（2026-10-11 方案④口径显性化）：轻量↔常规双向，由提报人主动发起。

    - AI 判定保持单向升不降（merge_mode_signal standard 粘性）；用户手动定过（origin=user）后 AI 双向不翻转
    - 打回补充期间同样可双向切换（2026-10-20 拍板）：口径由提报人自主判断，提交门槛随口径生效
    - 已填的 C/D 数据保留不清除，提交门槛随口径切换（light 只拦 4 项最小集）
    - 会话注入 kind=modeChange 播报（进对话上下文，AI 后续轮次可见；不参与质量快照回放）
    """
    demand = await get_owned_draft(db, user, demand_id, for_update=True)
    assert_editable(demand, expected_revision)
    before_level = rules.demand_mode(form_of(demand))
    if level == before_level:
        raise BizError(ErrorCode.PARAM_INVALID, "提报口径未变化")
    ext = dict(demand.ext or {})
    old_mode = ext.get("mode")
    ext["mode"] = {"level": level, "evidence": "提报人手动调整提报口径", "origin": "user"}
    demand.ext = ext
    demand.revision += 1
    demand.updated_at = now()
    db.add(DemandChangeLog(demand_id=demand.id, field_key="ext.mode", old_value=encode(old_mode),
                           new_value=encode(ext["mode"]), source="user", changed_by=user.id))
    if demand.session_id is not None:
        notice = ("你已把提报口径从「轻量提报」改为「常规提报」。我会按常规需求把该问的信息问齐，之前填的内容都保留。"
                  if level == "standard" else
                  "你已把提报口径从「常规提报」改为「轻量提报」。只需确认四项关键信息：标题、你的原话、紧急程度、期望效果，其余不再追问，之前填的内容都保留。")
        await session_service.append(db, demand.session_id, "ASSISTANT", notice,
                                     {"kind": "modeChange", "from": before_level, "to": level})
        # 当场按新口径接续（2026-10-20 拍板，与手改要素同规则）：重算质量卡——
        # 有缺口按新口径追问、要素齐备出「确认提交」快照，不再只发文案等下一轮
        await append_conversation_follow_up(db, user, demand)
    await db.flush()
    return demand


# 提交时整理的意图排除集（2026-10-20 拍板）：闲聊/提问/指令轮的用户消息不是需求内容，不入底稿
_NON_DEMAND_INTENTS = ("chitchat", "question", "command")


def _effective_user_turns(messages) -> list[str]:
    """有效对话的用户原话（2026-10-20 拍板）：按 request_id 与 ASSISTANT 消息 payload.intent 配对，
    排除闲聊/提问/指令轮；存量消息无 intent 标记视为有效（保守保留，不丢原话）。"""
    intent_by_request = {}
    for m in messages:
        if m.role == "ASSISTANT" and m.request_id:
            kind = (m.structured_payload or {}).get("intent")
            if kind:
                intent_by_request[m.request_id] = kind
    return [m.content.strip() for m in messages
            if m.role == "USER" and (m.content or "").strip()
            and intent_by_request.get(m.request_id) not in _NON_DEMAND_INTENTS]


def _join_turns(turns: list[str]) -> str:
    """按时序拼接为一段底稿（2026-10-20 拍板）：逐句原话不改写不润色（守住原文保真）；
    上一条未以标点收尾时补句号衔接。"""
    parts = []
    for turn in turns:
        if parts and not parts[-1].endswith(("。", "！", "？", "；", "…", ".", "!", "?", ";", "\n")):
            parts[-1] += "。"
        parts.append(turn)
    return "".join(parts)


def _first_sentence(text, limit=60) -> str:
    """取首句并截断（标题降级用）：按句读/换行切首句，再按 A1 字数上限截断。"""
    text = (text or "").strip()
    if not text:
        return ""
    for sep in ("。", "！", "？", "；", "\n", ".", "!", "?", ";"):
        idx = text.find(sep)
        if idx > 0:
            text = text[:idx]
            break
    return text[:limit].strip()


# 标题整理提示词（2026-10-20 拍板）：提交时基于全部有效对话重拟，约束与 A1 ok_when 一致；
# 信息不足输出空串，由调用方走降级截断链
_TITLE_POLISH_PROMPT = (
    "你是需求标题拟写助手。根据用户提报对话（turns，按时序）与需求表单（form），拟一个需求标题。"
    "要求：2~60字，一句话，能看出要解决什么问题；结尾不写句号，不要引号，不要解释；"
    "只整合用户说过的事实，不编造；信息不足以拟出合格标题时输出空字符串。"
    '只输出一个 JSON 对象：{"title":"标题或空字符串"}。'
)


async def _polish_title(form: dict, turns: list[str]) -> str:
    """模型重拟标题（2026-10-20 拍板）；模型不可用/输出非法/信息不足一律返回空串，由调用方降级。"""
    try:
        from app.agent.llm_client import get_llm_client
        llm = get_llm_client()
        if not llm.available():
            return ""
        payload = {"turns": turns, "form": {k: v for k, v in form.items() if k != "ext"}}
        event = await llm.complete_json([
            {"role": "system", "content": _TITLE_POLISH_PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ])
        data = json.loads(event.raw)
        title = str(data.get("title") or "").strip().strip("「」\"'").rstrip("。.").strip() if isinstance(data, dict) else ""
        if len(title) < 2:
            return ""
        return title[:60]
    except Exception as exc:
        logger.warning("提交标题重拟失败，走降级截断 %s: %s", type(exc).__name__, exc)
        return ""


async def submit(db, user, demand_id: int, expected_revision: int) -> Demand:
    demand = await get_owned_draft(db, user, demand_id, for_update=True)
    if demand.status == "SUBMITTED":
        return demand
    was_returned = demand.status == "NEED_INFO"
    assert_editable(demand, expected_revision)
    form, std = normalized(form_of(demand))
    # 提交时最后整理（2026-10-20 拍板，仅科技需求）：底稿（A8）与标题（A1）同为系统提取项——
    # ①底稿=按时序拼接全部有效对话（排除闲聊/提问/指令轮，逐句原话不改写）；仍为空用标题兜底；
    # ②标题=模型基于有效对话重拟（失败降级：底稿首句截断→功能描述截断→未命名需求）。
    # 手改权威：来源=user 且非回填产物的值一律不动；回填产物判定=值恰等于某条用户消息原文。
    if demand.demand_type_code == "TECH":
        sources = dict(demand.field_sources or {})
        history = await session_service.messages(db, user, demand.session_id) if demand.session_id is not None else []
        turns = _effective_user_turns(history)
        joined = _join_turns(turns)
        all_user_texts = {m.content.strip() for m in history if m.role == "USER" and (m.content or "").strip()}
        current_content = (form.get("content") or "").strip()
        if not current_content or current_content in all_user_texts:
            new_content = joined or (demand.title or "").strip()
            if new_content:
                demand.content, form["content"] = new_content, new_content
                # 来源记 user：值即用户原话拼接/标题本身，受保护不被模型改写
                sources["content"] = "user"
            elif current_content:
                # 底稿是被排除轮次的陈旧回填（如旧流程误存的寒暄）：清空，不拦提交
                demand.content, form["content"] = None, None
                sources.pop("content", None)
        # 手改且非空的标题是权威内容，不动；空标题无论来源一律由系统兜底（A1 单据必填的保证在此）
        title_manual = not rules.blank(form.get("title")) and (sources.get("title") or "") == "user"
        if not title_manual:
            polished = await _polish_title(form, turns)
            if polished:
                demand.title, form["title"] = polished, polished
                sources["title"] = "agent"
            if rules.blank(form.get("title")):
                fallback = (_first_sentence(form.get("content"))
                            or _first_sentence(rules.get_value(form, "elements.D.functionDescription"))
                            or "未命名需求")
                demand.title, form["title"] = fallback, fallback
                sources["title"] = "agent"
        demand.field_sources = sources
    light = rules.demand_mode(form) == "light"
    if light:
        # 微需求快速通道（2026-10-11 方案②）：light 只拦最小集（A1标题+A6紧急度+D8期望效果），
        # C/D 其余 12 项模板要素对换 logo/调样式这类轻量需求会语义性误伤，不作为提交门槛
        errors = rules.schema_errors(std, form, required=True, required_keys=rules.LIGHT_REQUIRED_KEYS)
    else:
        # 判型与 B 区解耦（2026-10-24 拍板）：B 区要素全部非必填，提交门槛恒为 A/C/D 三区——
        # 组织级理由（B1）是受理方分析产物，提报侧只保留「B1 白话一问」治理动作，不再拦提交；
        # 受理侧兜底：standard 缺 B1 拒绝受理（triage_service.accept）
        errors = rules.schema_errors(std, form, required=True, active_zones={"A", "C", "D"})
    if errors:
        raise BizError(ErrorCode.PARAM_INVALID, errors[0])
    version = await ensure_snapshot(db, std)
    demand.quality = [{"key": item.key, "status": item.status, "note": item.note} for item in rules.assess(std, form, light=light)]
    demand.standard_version_id = version.id
    demand.quality_content_hash = fingerprint(form)
    if demand.demand_no is None:
        # 重提保留原编号：管理员按编号跟踪需求，换号会造成困扰
        demand.demand_no = await next_no(db, demand.demand_type_code, now().date())
    demand.submitter_name, demand.submitter_dept = user.name, user.dept_name
    demand.channel = user.channel
    demand.submitted_at = now()
    # P5 组织回填（蓝本口径）：提报人组织=dept_id 映射未命中挂 900；承接组织=类型默认承接组织
    from app.services import org_service
    demand.submitter_org_id = await org_service.resolve_user_org_id(db, user)
    demand.assignee_org_id = await org_service.resolve_type_org_id(db, demand.demand_type_code)
    # P2 硬约束：状态变更必须经状态机引擎并写 transition_log（提交/重提同为 SUBMIT 事件）
    await engine.transition(db, demand_id, "SUBMIT", user, comment="补充后重新提交" if was_returned else None)
    if was_returned:
        # 打回补齐重提成功：清除待处理的打回原因（历史打回记录在 change_log 可查），并写状态留痕
        ext = dict(demand.ext or {})
        ext.pop("returnReason", None)
        demand.ext = ext
        db.add(DemandChangeLog(demand_id=demand.id, field_key="status", old_value="NEED_INFO", new_value="SUBMITTED",
                               source="user", changed_by=user.id))
    # 角标闭环（2026-10-20 拍板）：提交即视为本需求相关待办已处理——将提报人对本需求的未读通知
    # 标记已读（首次提交时无通知自然空转；重提时清掉打回通知）。「我的需求」tab 角标随之下架
    await db.execute(
        update(Notification).where(
            Notification.receiver_id == user.id,
            Notification.demand_id == demand.id,
            Notification.is_read.is_(False),
        ).values(is_read=True, read_at=now())
    )
    if demand.session_id is not None:
        session = (await db.execute(select(AgentSession).where(AgentSession.id == demand.session_id).with_for_update())).scalar_one()
        if session.demand_id != demand.id or session.user_id != user.id:
            raise BizError(ErrorCode.CONFLICT, "草稿与会话关联不一致")
        session.status = "CLOSED"
    await db.flush()
    return demand


async def close(db, user, demand_id: int, reason: str) -> Demand:
    demand = await get_owned_draft(db, user, demand_id, for_update=True)
    # 草稿撤销与已提交撤回同一出口（DRAFT/SUBMITTED/NEED_INFO → CLOSED）；CLOSED 不可重复流转
    if demand.status not in ("DRAFT", "SUBMITTED", "NEED_INFO"):
        raise BizError(ErrorCode.ILLEGAL_STATE_TRANSITION)
    # P2 硬约束：经状态机 WITHDRAW 事件（提报人撤销）并写 transition_log
    await engine.transition(db, demand_id, "WITHDRAW", user, comment=reason,
                            field_update={"close_reason": reason, "closed_at": now()})
    return demand


# ---- 删除草稿需求（2026-10-22 拍板：①A 物理删除 + ②A 服务端记日志 + ③A 前端标准确认框）----
# 仅 ADMIN 可操作（路由 require_admin 守门）、仅 DRAFT 态可删（防误删正式需求的最重要一道闸）


async def delete_draft(db, user, demand_id: int) -> dict:
    """物理删除草稿及其全部关联数据（事务内级联）。返回删除前的快照信息供提交后留痕。"""
    demand = (await db.execute(
        select(Demand).where(Demand.id == demand_id).with_for_update()
    )).scalar_one_or_none()
    if demand is None:
        raise BizError(ErrorCode.DEMAND_NOT_FOUND)
    if demand.status != "DRAFT":
        raise BizError(ErrorCode.ILLEGAL_STATE_TRANSITION, "仅草稿需求可删除")
    snapshot = {"id": demand.id, "title": demand.title}
    # 级联删除：草稿态实际有数据的通常只有会话/消息/附件/变更留痕，其余表兜底删。
    # agent_message 挂 agent_session，须先取会话 id 再删消息
    session_ids = (await db.execute(
        select(AgentSession.id).where(AgentSession.demand_id == demand_id)
    )).scalars().all()
    if session_ids:
        await db.execute(delete(AgentMessage).where(AgentMessage.session_id.in_(session_ids)))
    await db.execute(delete(AgentDraft).where(AgentDraft.demand_id == demand_id))
    await db.execute(delete(AgentSession).where(AgentSession.demand_id == demand_id))
    await db.execute(delete(DemandAttachment).where(DemandAttachment.demand_id == demand_id))
    await db.execute(delete(DemandChangeLog).where(DemandChangeLog.demand_id == demand_id))
    await db.execute(delete(DemandTransitionLog).where(DemandTransitionLog.demand_id == demand_id))
    await db.execute(delete(RagVector).where(RagVector.demand_id == demand_id))
    # review.target_id 外键指向 solution，先删 review 再删 solution
    await db.execute(delete(Review).where(Review.demand_id == demand_id))
    await db.execute(delete(Solution).where(Solution.demand_id == demand_id))
    await db.execute(delete(Comment).where(Comment.demand_id == demand_id))
    await db.execute(delete(EffortLog).where(EffortLog.demand_id == demand_id))
    await db.execute(delete(Assignment).where(Assignment.demand_id == demand_id))
    await db.execute(delete(DemandRelation).where(
        (DemandRelation.from_id == demand_id) | (DemandRelation.to_id == demand_id)
    ))
    # notification.demand_id 是普通列无外键，同步清理避免悬空引用
    await db.execute(delete(Notification).where(Notification.demand_id == demand_id))
    await db.delete(demand)
    return snapshot


def purge_draft_attachments(demand_id: int) -> None:
    """删除草稿的附件物理目录（须在 DB 事务提交后调用，避免回滚时文件先丢、记录还在的不一致）。"""
    # 附件按 demand_id 分目录存放（attachment_service.storage_path 同规则），整目录删除
    shutil.rmtree(Path(get_settings().attachment_dir) / str(demand_id), ignore_errors=True)


def filters(statement, *, status=None, type_code=None, date_from=None, date_to=None):
    if status:
        statement = statement.where(Demand.status == status)
    if type_code:
        statement = statement.where(Demand.demand_type_code == type_code)
    if date_from:
        statement = statement.where(Demand.submitted_at >= date_from)
    if date_to:
        statement = statement.where(Demand.submitted_at < date_to + timedelta(days=1))
    return statement


async def need_info_count(db, user) -> int:
    """「我的需求」tab 角标（2026-10-20 拍板改口径）：待补充需求数，
    与 /demand/my?status=NEED_INFO 完全同口径——补充重提/撤销后状态流转，角标自动消，
    不再依赖通知已读（通知无可信已读通路时会产生幽灵角标）。"""
    return (await db.execute(
        select(func.count(Demand.id)).where(
            Demand.submitter_id == user.id,
            Demand.status == "NEED_INFO",
        )
    )).scalar_one()


async def list_records(db, user=None, *, page=1, size=20, **query):
    statement = select(Demand)
    if user is not None:
        statement = statement.where(Demand.submitter_id == user.id)
    statement = filters(statement, **query)
    total = (await db.execute(select(func.count()).select_from(statement.subquery()))).scalar_one()
    records = (await db.execute(statement.order_by(Demand.created_at.desc(), Demand.id.desc()).offset((page-1)*size).limit(size))).scalars().all()
    logs = await change_logs_map(db, [d.id for d in records])
    names = await assignee_names_map(db, records)
    return {"records": [serialize_demand(d, logs[d.id], names.get(d.assignee_id)) for d in records], "total": total,
            "size": size, "current": page, "pages": (total + size - 1) // size}


async def standard_for(db, demand: Demand) -> Standard | None:
    if demand.standard_version_id:
        snapshot = await db.get(PromptVersion, demand.standard_version_id)
        return Standard.model_validate(snapshot.snapshot["standard"])
    return get_standard(demand.demand_type_code) if demand.demand_type_code else None


async def _ensure_entry_opening_snapshot(db, demand: Demand, rows) -> bool:
    """进入提报页即校验要素（2026-10-20 拍板）：打回补提与草稿续提统一兜底——凡可提报状态
    （DRAFT/NEED_INFO），会话中无「与当前 revision 匹配、且要素键集合与当前模板一致的正式快照
    （无 kind 的对话结果消息）」时，纯规则重算并补注一条：要素齐备 → 快照 canSubmit=true，
    进页直接显示「确认提交」；有缺口 → AI 开口追问当前缺口。覆盖：修复上线前的存量打回单、
    手改/模式切换等顶了 revision 使快照失配的路径、无任何快照的老草稿。幂等——注入后再次
    读取命中既有快照即跳过。
    模板指纹校验（2026-10-20 拍板）：revision 只跟随表单数据，规则模板演进（如五区重构）
    不顶 revision——老模板生成的快照 revision 仍匹配会被误回放（陈旧快照污染：老 7 要素
    快照 canSubmit=true 掩盖五区缺口）。快照要素键集合与当前模板键集合不一致即视为失配，
    触发重算；同模板下 assess 恒输出全量键，不会误伤。"""
    if demand.status not in ("DRAFT", "NEED_INFO") or demand.session_id is None:
        return False
    std = await standard_for(db, demand)
    template_keys = ({field.key for field in std.elements if not field.system and field.assessed}
                     if std is not None else set())
    for row in reversed(rows):
        payload = row.structured_payload
        if (row.role == "ASSISTANT" and isinstance(payload, dict) and payload.get("kind") is None
                and payload.get("revision") == demand.revision
                and {e.get("key") for e in payload.get("elements") or [] if isinstance(e, dict)} == template_keys):
            return False
    owner = await db.get(User, demand.submitter_id)
    if owner is None:
        return False
    # 进页面补快照（2026-10-20）：enter 话术；打回引述按历史自动判定（第一次进补充会话引述一次）
    await append_conversation_follow_up(db, owner, demand, trigger="enter")
    await db.flush()
    return True


async def detail(db, user, demand_id: int) -> dict:
    demand = await db.get(Demand, demand_id)
    # P2 可见性：提报人/管理员 之外，处理人可查看已进入流转的需求（管理视角详情页）
    from app.services.flow_service import can_view_demand
    if demand is None or not can_view_demand(user, demand):
        raise BizError(ErrorCode.DEMAND_NOT_FOUND)
    std = await standard_for(db, demand)
    messages = []
    if demand.session_id:
        rows = (await db.execute(select(AgentMessage).where(AgentMessage.session_id == demand.session_id).order_by(AgentMessage.id))).scalars().all()
        # 进入提报页即校验：自愈注入后重取，保证本次响应即携带开场快照（回放/按钮一次就位）
        if await _ensure_entry_opening_snapshot(db, demand, rows):
            rows = (await db.execute(select(AgentMessage).where(AgentMessage.session_id == demand.session_id).order_by(AgentMessage.id))).scalars().all()
        messages = [{"id": row.id, "sessionId": row.session_id, "role": row.role, "content": row.content,
            "structuredPayload": json.dumps(row.structured_payload, ensure_ascii=False) if row.structured_payload else None,
            "createdAt": encode(row.created_at)} for row in rows]
    from app.services import attachment_service
    return {"demand": serialize_demand(demand, (await change_logs_map(db, [demand.id]))[demand.id],
                                       (await assignee_names_map(db, [demand])).get(demand.assignee_id)),
            "quality": demand.quality or [],
            "standard": std.model_dump(mode="json", by_alias=True) if std else None, "messages": messages,
            "attachments": await attachment_service.serialize_list(db, demand.id)}
