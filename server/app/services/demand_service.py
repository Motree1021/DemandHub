import hashlib
import json
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.mysql import insert

from app.core.deps import is_admin
from app.core.errors import BizError, ErrorCode
from app.core.result import encode
from app.db.models import AgentMessage, AgentSession, Demand, PromptVersion, now
from app.services.demand_no import next_no
from app.standards import rules
from app.standards.loader import ensure_snapshot
from app.standards.loader import get as get_standard
from app.standards.schema import Standard

TOP_FIELDS = {"title": "title", "demandTypeCode": "demand_type_code", "content": "content",
              "urgency": "urgency", "expectDeliveryAt": "expect_delivery_at"}


def fingerprint(value: dict) -> str:
    return hashlib.sha256(json.dumps(encode(value), sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":")).encode()).hexdigest()


def form_of(demand: Demand) -> dict:
    return {"title": demand.title, "demandTypeCode": demand.demand_type_code,
            "content": demand.content, "urgency": demand.urgency,
            "expectDeliveryAt": demand.expect_delivery_at.isoformat() if demand.expect_delivery_at else None,
            "ext": dict(demand.ext or {})}


def serialize_demand(demand: Demand) -> dict:
    result = {"id": demand.id, "demandNo": demand.demand_no, **form_of(demand),
              "subtypeCode": demand.subtype_code, "revision": demand.revision,
              "fieldSources": demand.field_sources or {}, "status": demand.status,
              "quality": demand.quality or [], "submitterId": demand.submitter_id,
              "submitterName": demand.submitter_name, "submitterDept": demand.submitter_dept,
              "channel": demand.channel, "sessionId": demand.session_id,
              "standardVersionId": demand.standard_version_id, "qualityContentHash": demand.quality_content_hash,
              "submittedAt": demand.submitted_at, "closedAt": demand.closed_at,
              "closeReason": demand.close_reason, "createdAt": demand.created_at, "updatedAt": demand.updated_at}
    return encode(result)


def normalized(form: dict) -> tuple[dict, Standard | None]:
    type_code = form.get("demandTypeCode")
    std = get_standard(type_code) if type_code else None
    try:
        result = rules.filter_form(std, form)
        errors = rules.schema_errors(std, result)
        if errors:
            raise ValueError(errors[0])
        for path, value in paths(result).items():
            if rules.blank(value):
                rules.set_value(result, path, None)
        if result.get("urgency") is None:
            result["urgency"] = "NORMAL"
        return result, std
    except ValueError as exc:
        raise BizError(ErrorCode.PARAM_INVALID, str(exc)) from None


def paths(form: dict) -> dict:
    return {**{k: v for k, v in form.items() if k != "ext"},
            **{"ext." + k: v for k, v in (form.get("ext") or {}).items()}}


def assign(demand: Demand, form: dict, sources: dict) -> None:
    for key, attr in TOP_FIELDS.items():
        value = form.get(key)
        if key == "expectDeliveryAt":
            value = date.fromisoformat(value) if value else None
        setattr(demand, attr, value)
    demand.ext = dict(form.get("ext") or {})
    demand.field_sources = {path: source for path, source in sources.items() if path in paths(form)}
    demand.subtype_code = demand.ext.get("techSubtype")


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


async def create_draft(db, user, payload: dict) -> Demand:
    form, _ = normalized({"urgency": "NORMAL", **payload})
    supplied_sources = payload.get("fieldSources") or {}
    sources = {}
    for path, value in paths(form).items():
        source = supplied_sources.get(path)
        sources[path] = "default" if source == "default" and path in {"urgency", "demandTypeCode"} else "user"
        if rules.blank(value) and source is None:
            sources.pop(path, None)
    if "urgency" not in payload:
        sources["urgency"] = "default"
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
    patch = {k: v for k, v in payload.items() if k in TOP_FIELDS or k == "ext"}
    merged = {**before, **patch, "ext": {**before["ext"], **(patch.get("ext") or {})}}
    form, _ = normalized(merged)
    sources = dict(demand.field_sources or {})
    requested = payload.get("fieldSources") or {}
    for path, value in paths(patch).items():
        # 显式改值/清空均是手改；保留未改变的已有来源，客户端不能降级 user。
        if sources.get(path) == "user" or requested.get(path) == "user" or value != rules.get_value(before, path):
            sources[path] = "user"
        elif path not in sources and not rules.blank(value):
            sources[path] = "user"
    assign(demand, form, sources)
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
    merged = {**before, "ext": dict(before["ext"])}
    for path, value in paths(patch).items():
        if sources.get(path) == "user" or rules.blank(value):
            continue
        rules.set_value(merged, path, value)
        if value != rules.get_value(before, path):
            sources[path] = "agent"
        elif field_sources and field_sources.get(path) == "user":
            sources[path] = "user"
    form, _ = normalized(merged)
    assign(demand, form, sources)
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
    errors = rules.schema_errors(std, form, required=True)
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
    if demand.status != "SUBMITTED":
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
    return {"records": [serialize_demand(d) for d in records], "total": total,
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
    return {"demand": serialize_demand(demand), "quality": demand.quality or [],
            "standard": std.model_dump(mode="json", by_alias=True) if std else None, "messages": messages}
