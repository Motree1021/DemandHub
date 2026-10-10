import hashlib
import json
from copy import deepcopy
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.mysql import insert

from app.core.deps import is_admin
from app.core.errors import BizError, ErrorCode
from app.core.result import encode
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

# ext 保留位：判型结果（FR-03）与实例切分建议（BR-T11，一期打标）不走标准要素白名单，全程保留
RESERVED_EXT_KEYS = ("typeRecognition", "pendingSplits", "overview")


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


def serialize_demand(demand: Demand, change_logs: list | None = None) -> dict:
    result = {"id": demand.id, "demandNo": demand.demand_no, **form_of(demand),
              "subtypeCode": demand.subtype_code, "revision": demand.revision,
              "fieldSources": demand.field_sources or {}, "status": demand.status,
              "quality": demand.quality or [], "submitterId": demand.submitter_id,
              "submitterName": demand.submitter_name, "submitterDept": demand.submitter_dept,
              "channel": demand.channel, "sessionId": demand.session_id,
              "standardVersionId": demand.standard_version_id, "qualityContentHash": demand.quality_content_hash,
              "changeLogs": change_logs or [],
              "submittedAt": demand.submitted_at, "closedAt": demand.closed_at,
              "closeReason": demand.close_reason, "createdAt": demand.created_at, "updatedAt": demand.updated_at}
    return encode(result)


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
    return serialize_demand(demand, (await change_logs_map(db, [demand.id]))[demand.id])


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
    if demand.status != "DRAFT":
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


def describe_changes(std: Standard | None, before: dict, after: dict) -> str:
    """手工改要素的聊天播报（FR-06）：与 write_change_logs 同源 diff，保留位与派生摘要不播报。"""
    elements = {item.field_path: item for item in std.elements} if std else {}
    lines = []
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
            lines.append(f"你已手动清空了「{label}」")
        elif rules.blank(old):
            lines.append(f"你已手动填写了「{label}」：{new_text}")
        else:
            lines.append(f"你已手动更新了「{label}」：由「{old_text}」改为「{new_text}」")
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
        # 手工改要素播报（FR-06）：与留痕同源 diff 写入会话，让用户与 AI 都感知本次手改内容
        text = describe_changes(std, before, form)
        if text:
            await session_service.append(db, demand.session_id, "ASSISTANT", text)
    demand.revision += 1
    demand.updated_at = now()
    await db.flush()
    return demand


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


async def submit(db, user, demand_id: int, expected_revision: int) -> Demand:
    demand = await get_owned_draft(db, user, demand_id, for_update=True)
    if demand.status == "SUBMITTED":
        return demand
    assert_editable(demand, expected_revision)
    form, std = normalized(form_of(demand))
    # B 区必填按判型门槛生效（FR-03/PRD §4.3）：判型或确认为业务需求时全量四区，否则 A/C/D
    active_zones = {"A", "C", "D"} | ({"B"} if rules.business_confirmed((demand.ext or {}).get("typeRecognition")) else set())
    errors = rules.schema_errors(std, form, required=True, active_zones=active_zones)
    if errors:
        raise BizError(ErrorCode.PARAM_INVALID, errors[0])
    version = await ensure_snapshot(db, std)
    demand.quality = [{"key": item.key, "status": item.status, "note": item.note} for item in rules.assess(std, form)]
    demand.standard_version_id = version.id
    demand.quality_content_hash = fingerprint(form)
    demand.demand_no = await next_no(db, demand.demand_type_code, now().date())
    demand.submitter_name, demand.submitter_dept = user.name, user.dept_name
    demand.channel = user.channel
    demand.status, demand.submitted_at = "SUBMITTED", now()
    demand.revision += 1
    if demand.session_id is not None:
        session = (await db.execute(select(AgentSession).where(AgentSession.id == demand.session_id).with_for_update())).scalar_one()
        if session.demand_id != demand.id or session.user_id != user.id:
            raise BizError(ErrorCode.CONFLICT, "草稿与会话关联不一致")
        session.status = "CLOSED"
    await db.flush()
    return demand


async def close(db, user, demand_id: int, reason: str) -> Demand:
    demand = await get_owned_draft(db, user, demand_id, for_update=True)
    # 草稿撤销与已提交撤回同一出口（DRAFT/SUBMITTED → CLOSED）；CLOSED 不可重复流转
    if demand.status not in ("DRAFT", "SUBMITTED"):
        raise BizError(ErrorCode.ILLEGAL_STATE_TRANSITION)
    demand.status, demand.close_reason, demand.closed_at = "CLOSED", reason, now()
    demand.revision += 1
    await db.flush()
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
    return {"records": [serialize_demand(d, logs[d.id]) for d in records], "total": total,
            "size": size, "current": page, "pages": (total + size - 1) // size}


async def standard_for(db, demand: Demand) -> Standard | None:
    if demand.standard_version_id:
        snapshot = await db.get(PromptVersion, demand.standard_version_id)
        return Standard.model_validate(snapshot.snapshot["standard"])
    return get_standard(demand.demand_type_code) if demand.demand_type_code else None


async def detail(db, user, demand_id: int) -> dict:
    demand = await db.get(Demand, demand_id)
    if demand is None or (demand.submitter_id != user.id and not is_admin(user)):
        raise BizError(ErrorCode.DEMAND_NOT_FOUND)
    std = await standard_for(db, demand)
    messages = []
    if demand.session_id:
        rows = (await db.execute(select(AgentMessage).where(AgentMessage.session_id == demand.session_id).order_by(AgentMessage.id))).scalars().all()
        messages = [{"id": row.id, "sessionId": row.session_id, "role": row.role, "content": row.content,
            "structuredPayload": json.dumps(row.structured_payload, ensure_ascii=False) if row.structured_payload else None,
            "createdAt": encode(row.created_at)} for row in rows]
    return {"demand": serialize_demand(demand, (await change_logs_map(db, [demand.id]))[demand.id]), "quality": demand.quality or [],
            "standard": std.model_dump(mode="json", by_alias=True) if std else None, "messages": messages}
