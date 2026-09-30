"""会话只绑定本人唯一草稿，事务交由API或编排负责。"""
import json
from uuid import uuid4

from sqlalchemy import select

from app.core.errors import BizError, ErrorCode
from app.db.models import AgentMessage, AgentSession, Demand


async def create(db, user, scene, demand_id, first_message=""):
    if scene != "SUBMIT_GUIDE":
        raise BizError(ErrorCode.PARAM_INVALID, "仅支持提报启发会话")
    demand = (await db.execute(select(Demand).where(Demand.id == demand_id, Demand.submitter_id == user.id).with_for_update())).scalar_one_or_none()
    if demand is None:
        raise BizError(ErrorCode.DEMAND_NOT_FOUND)
    if demand.status != "DRAFT":
        raise BizError(ErrorCode.ILLEGAL_STATE_TRANSITION, "会话仅能绑定本人草稿")
    existing = (await db.execute(select(AgentSession).where(AgentSession.demand_id == demand_id))).scalar_one_or_none()
    if existing:
        if existing.user_id != user.id or demand.session_id != existing.id:
            raise BizError(ErrorCode.CONFLICT, "草稿会话绑定不一致")
        return existing
    if demand.session_id is not None:
        raise BizError(ErrorCode.CONFLICT, "草稿会话绑定不一致")
    agent_session = AgentSession(session_no=uuid4().hex, user_id=user.id, scene=scene, demand_id=demand_id, title=first_message[:30] or "需求启发", status="ACTIVE")
    db.add(agent_session)
    await db.flush()
    demand.session_id = agent_session.id
    await db.flush()
    return agent_session


async def require_owned(db, user, session_id, lock=False):
    statement = select(AgentSession).where(AgentSession.id == session_id, AgentSession.user_id == user.id)
    if lock:
        statement = statement.with_for_update()
    result = (await db.execute(statement)).scalar_one_or_none()
    if result is None:
        raise BizError(ErrorCode.AGENT_SESSION_NOT_FOUND)
    return result


async def list_mine(db, user, scene=None):
    statement = select(AgentSession).where(AgentSession.user_id == user.id)
    if scene:
        statement = statement.where(AgentSession.scene == scene)
    return list((await db.execute(statement.order_by(AgentSession.id.desc()).limit(50))).scalars())


async def messages(db, user, session_id, limit=None):
    await require_owned(db, user, session_id)
    statement = select(AgentMessage).where(AgentMessage.session_id == session_id).order_by(AgentMessage.id.desc())
    if limit:
        statement = statement.limit(limit)
    result = list((await db.execute(statement)).scalars())
    return list(reversed(result))


async def append(db, session_id, role, content, structured_payload=None, *, request_id=None, request_hash=None, prompt_version_id=None, model=None, prompt_tokens=None, completion_tokens=None, latency_ms=None):
    result = AgentMessage(session_id=session_id, role=role, content=content, structured_payload=structured_payload, request_id=request_id, request_hash=request_hash, prompt_version_id=prompt_version_id, model=model, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens, latency_ms=latency_ms)
    db.add(result)
    await db.flush()
    return result


def serialize_session(value):
    return {"id": value.id, "sessionNo": value.session_no, "userId": value.user_id, "scene": value.scene, "demandId": value.demand_id, "title": value.title, "status": value.status, "askedTarget": value.asked_target, "createdAt": value.created_at.strftime("%Y-%m-%d %H:%M:%S"), "updatedAt": value.updated_at.strftime("%Y-%m-%d %H:%M:%S")}


def serialize_message(value):
    return {"id": value.id, "sessionId": value.session_id, "role": value.role, "content": value.content, "requestId": value.request_id, "structuredPayload": json.dumps(value.structured_payload, ensure_ascii=False) if value.structured_payload is not None else None, "createdAt": value.created_at.strftime("%Y-%m-%d %H:%M:%S")}
