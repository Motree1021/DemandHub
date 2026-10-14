"""会话：SUBMIT_GUIDE 绑定本人唯一草稿；HANDLE_ASSIST 为需求级共享工作区（每需求一个）。"""
import json
from uuid import uuid4

from sqlalchemy import select

from app.core.errors import BizError, ErrorCode
from app.db.models import AgentMessage, AgentSession, Demand


async def create(db, user, scene, demand_id, first_message=""):
    if scene == "HANDLE_ASSIST":
        return await _create_assist(db, user, demand_id)
    if scene != "SUBMIT_GUIDE":
        raise BizError(ErrorCode.PARAM_INVALID, "不支持的会话场景")
    demand = (await db.execute(select(Demand).where(Demand.id == demand_id, Demand.submitter_id == user.id).with_for_update())).scalar_one_or_none()
    if demand is None:
        raise BizError(ErrorCode.DEMAND_NOT_FOUND)
    # NEED_INFO（管理员打回待补充，方案③）：无会话的打回需求也允许进入对话补填
    if demand.status not in ("DRAFT", "NEED_INFO"):
        raise BizError(ErrorCode.ILLEGAL_STATE_TRANSITION, "会话仅能绑定本人可编辑需求")
    existing = (await db.execute(select(AgentSession).where(AgentSession.demand_id == demand_id, AgentSession.scene == scene))).scalar_one_or_none()
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


async def _create_assist(db, user, demand_id):
    """处理辅助会话：需求级共享（(demand_id, scene) 唯一），谁打开谁接入同一会话。"""
    demand = (await db.execute(select(Demand).where(Demand.id == demand_id).with_for_update())).scalar_one_or_none()
    if demand is None:
        raise BizError(ErrorCode.DEMAND_NOT_FOUND)
    existing = (await db.execute(select(AgentSession).where(AgentSession.demand_id == demand_id, AgentSession.scene == "HANDLE_ASSIST"))).scalar_one_or_none()
    if existing:
        return existing
    agent_session = AgentSession(session_no=uuid4().hex, user_id=user.id, scene="HANDLE_ASSIST", demand_id=demand_id, title=(demand.title or "")[:30] or "处理辅助", status="ACTIVE")
    db.add(agent_session)
    await db.flush()
    return agent_session


async def require_owned(db, user, session_id, lock=False):
    statement = select(AgentSession).where(AgentSession.id == session_id)
    if lock:
        statement = statement.with_for_update()
    result = (await db.execute(statement)).scalar_one_or_none()
    # SUBMIT_GUIDE 严格本人；HANDLE_ASSIST 需求级共享（处理人更替/管理员查看不断会话）
    if result is None or (result.scene == "SUBMIT_GUIDE" and result.user_id != user.id):
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
