import hashlib
import json
from copy import deepcopy
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.mysql import insert

from app.core.errors import BizError, ErrorCode
from app.core.result import encode
from app.core.statemachine import engine
from app.db.models import AgentMessage, AgentSession, Demand, DemandChangeLog, PromptVersion, now
from app.services import session_service
from app.services.demand_no import next_no
from app.standards import rules
from app.standards.loader import ensure_snapshot
from app.standards.loader import get as get_standard
from app.standards.migration_map import elements_from_legacy, legacy_from_elements
from app.standards.schema import Standard

TOP_FIELDS = {"title": "title", "demandTypeCode": "demand_type_code", "content": "content",
              "urgency": "urgency", "expectDeliveryAt": "expect_delivery_at"}

# ext 保留位：判型结果（FR-03）、实例切分建议（BR-T11，一期打标）、轻重模式（2026-10-11 方案②）、
# 打回原因（2026-10-11 方案③ NEED_INFO 闭环）不走标准要素白名单，全程保留
RESERVED_EXT_KEYS = ("typeRecognition", "pendingSplits", "overview", "mode", "returnReason")


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
        # ext.overview 是 AI 每轮重写的派生摘要，留痕会刷噪音；原文与要素留痕已足够追溯
        if path == "ext.overview":
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
        old_text, new_text = _clip_text(_display_value(element, old)), _clip_text(_display_value(element, new))
        if rules.blank(new):
            items.append({"action": "clear", "label": label, "old": old_text, "new": ""})
        elif rules.blank(old):
            items.append({"action": "fill", "label": label, "old": "", "new": new_text})
        else:
            items.append({"action": "update", "label": label, "old": old_text, "new": new_text})
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
    statement = insert(Demand).values(submitter_id=user.id, client_request_id=payload["clientRequestId"],
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
    if payload.get("notifyChanges") and demand.session_id is not None:
        # 手工改要素播报（FR-06）：与留痕同源 diff 写入会话；结构化 payload 供前端渲染卡片
        items = change_items(std, before, form)
        if items:
            await session_service.append(db, demand.session_id, "ASSISTANT", describe_changes(items),
                                          {"kind": "manualChange", "changes": items})
    demand.revision += 1
    demand.updated_at = now()
    await db.flush()
    return demand


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
    - ext.mode 强制升 standard：打回意味着信息不足，按 12 项完整口径补填，不回轻量快速通道
    - 会话重开 ACTIVE 并注入一条引述打回原因的播报消息（kind=returnNotice，不参与质量快照回放）
    """
    demand = (await db.execute(select(Demand).where(Demand.id == demand_id).with_for_update())).scalar_one_or_none()
    if demand is None:
        raise BizError(ErrorCode.DEMAND_NOT_FOUND)
    if demand.status != "SUBMITTED":
        raise BizError(ErrorCode.ILLEGAL_STATE_TRANSITION, "仅已提交的需求可打回")
    reason_text = reason.strip()
    ext = dict(demand.ext or {})
    ext["returnReason"] = {"reason": reason_text, "returnedBy": admin_user.name,
                           "returnedAt": now().isoformat(timespec="seconds")}
    ext["mode"] = {"level": "standard", "evidence": "管理员打回待补充，按完整口径补齐后重新提交"}
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
        notice = (f"这条需求被整理人员打回了，需要补充信息后重新提交。\n打回原因：{reason_text}\n"
                  "可以直接回复我来补充，我会帮你把缺的内容问齐；也可以点开「需求要素表单」卡片逐项修改。")
        await session_service.append(db, demand.session_id, "ASSISTANT", notice,
                                     {"kind": "returnNotice", "reason": reason_text})
    await db.flush()
    return demand


async def change_mode(db, user, demand_id: int, expected_revision: int, level: str) -> Demand:
    """提报口径改判（2026-10-11 方案④口径显性化）：轻量↔常规双向，由提报人主动发起。

    - AI 判定保持单向升不降（merge_mode_signal standard 粘性）；用户手动定过（origin=user）后 AI 双向不翻转
    - 打回补充期间（ext.returnReason 存在）不可切换为轻量：打回按 12 项完整口径补齐，重提清除后恢复自由
    - 已填的 C/D 数据保留不清除，提交门槛随口径切换（light 只拦 4 项最小集）
    - 会话注入 kind=modeChange 播报（进对话上下文，AI 后续轮次可见；不参与质量快照回放）
    """
    demand = await get_owned_draft(db, user, demand_id, for_update=True)
    assert_editable(demand, expected_revision)
    before_level = rules.demand_mode(form_of(demand))
    if level == before_level:
        raise BizError(ErrorCode.PARAM_INVALID, "提报口径未变化")
    if level == "light" and (demand.ext or {}).get("returnReason"):
        raise BizError(ErrorCode.PARAM_INVALID, "打回补充期间不可切换为轻量，请按打回原因补齐后重新提交")
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
    await db.flush()
    return demand


async def submit(db, user, demand_id: int, expected_revision: int) -> Demand:
    demand = await get_owned_draft(db, user, demand_id, for_update=True)
    if demand.status == "SUBMITTED":
        return demand
    was_returned = demand.status == "NEED_INFO"
    assert_editable(demand, expected_revision)
    form, std = normalized(form_of(demand))
    light = rules.demand_mode(form) == "light"
    if light:
        # 微需求快速通道（2026-10-11 方案②）：light 只拦最小集（A8原话+A1标题+A6紧急度+D8期望效果），
        # C/D 其余 12 项模板要素对换 logo/调样式这类轻量需求会语义性误伤，不作为提交门槛
        errors = rules.schema_errors(std, form, required=True, required_keys=rules.LIGHT_REQUIRED_KEYS)
    else:
        # B 区必填按判型门槛生效（FR-03/PRD §4.3）：判型或确认为业务需求时全量四区，否则 A/C/D
        active_zones = {"A", "C", "D"} | ({"B"} if rules.business_confirmed((demand.ext or {}).get("typeRecognition")) else set())
        errors = rules.schema_errors(std, form, required=True, active_zones=active_zones)
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
        messages = [{"id": row.id, "sessionId": row.session_id, "role": row.role, "content": row.content,
            "structuredPayload": json.dumps(row.structured_payload, ensure_ascii=False) if row.structured_payload else None,
            "createdAt": encode(row.created_at)} for row in rows]
    from app.services import attachment_service
    return {"demand": serialize_demand(demand, (await change_logs_map(db, [demand.id]))[demand.id],
                                       (await assignee_names_map(db, [demand])).get(demand.assignee_id)),
            "quality": demand.quality or [],
            "standard": std.model_dump(mode="json", by_alias=True) if std else None, "messages": messages,
            "attachments": await attachment_service.serialize_list(db, demand.id)}
