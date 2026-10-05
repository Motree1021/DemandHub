from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.agent.guide import GuideService
from app.agent.llm_client import get_llm_client
from app.agent.schemas import CreateSessionRequest, GuideChatRequest
from app.core.deps import get_current_user, get_db
from app.core.result import ok
from app.services import session_service

router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/session")
async def create_session(payload: CreateSessionRequest, db=Depends(get_db), user=Depends(get_current_user)):
    async with db.begin():
        value = await session_service.create(db, user, payload.scene, payload.demand_id, payload.first_message)
        result = session_service.serialize_session(value)
    return ok(result)


@router.get("/session/list")
async def list_sessions(scene: str | None = None, db=Depends(get_db), user=Depends(get_current_user)):
    return ok([session_service.serialize_session(s) for s in await session_service.list_mine(db, user, scene)])


@router.get("/session/{session_id}/messages")
async def messages(session_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    return ok([session_service.serialize_message(m) for m in await session_service.messages(db, user, session_id)])


@router.post("/guide/chat/stream")
async def guide_stream(payload: GuideChatRequest, db=Depends(get_db), user=Depends(get_current_user), llm=Depends(get_llm_client)):
    service = GuideService(db, user, llm)
    await service.prepare(payload)
    return StreamingResponse(service.stream(payload), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/guide/chat")
async def guide_chat(payload: GuideChatRequest, db=Depends(get_db), user=Depends(get_current_user), llm=Depends(get_llm_client)):
    return ok((await GuideService(db, user, llm).execute(payload)).model_dump(mode="json", by_alias=True))
