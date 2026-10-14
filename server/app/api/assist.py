"""处理辅助 Agent + RAG 检索（照蓝本 AgentAssistController/RagController）。

草稿区人工确认后才入 solution 表；大模型不可用 → 1401 降级提示，处理主流程不受影响。
"""
from datetime import date

from fastapi import APIRouter, Depends

from app.agent.llm_client import get_llm_client
from app.core.deps import get_current_user, get_db
from app.core.result import ApiModel, ok
from app.services import assist_service, rag_service

router = APIRouter(prefix="/agent", tags=["agent-assist"])


class GenerateBody(ApiModel):
    session_id: int


class ConfirmBody(ApiModel):
    spec_content: str | None = None
    solution_content: str | None = None
    plan_delivery_at: date | None = None


@router.post("/assist/questions")
async def questions(payload: GenerateBody, db=Depends(get_db), user=Depends(get_current_user),
                    llm=Depends(get_llm_client)):
    async with db.begin():
        draft = await assist_service.generate_questions(db, user, payload.session_id, llm=llm)
        result = assist_service.serialize_draft(draft)
    return ok(result)


@router.post("/assist/solution")
async def solution(payload: GenerateBody, db=Depends(get_db), user=Depends(get_current_user),
                   llm=Depends(get_llm_client)):
    async with db.begin():
        draft = await assist_service.generate_solution(db, user, payload.session_id, llm=llm)
        result = assist_service.serialize_draft(draft)
    return ok(result)


@router.get("/assist/drafts")
async def drafts(demandId: int, db=Depends(get_db), user=Depends(get_current_user)):
    return ok([assist_service.serialize_draft(d) for d in await assist_service.drafts(db, demandId)])


@router.post("/assist/drafts/{draft_id}/confirm")
async def confirm(draft_id: int, payload: ConfirmBody | None = None, db=Depends(get_db),
                  user=Depends(get_current_user)):
    body = payload or ConfirmBody()
    async with db.begin():
        draft = await assist_service.confirm(
            db, user, draft_id, spec_content=body.spec_content,
            solution_content=body.solution_content, plan_delivery_at=body.plan_delivery_at)
        result = assist_service.serialize_draft(draft)
    return ok(result)


@router.post("/assist/drafts/{draft_id}/discard")
async def discard(draft_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    async with db.begin():
        await assist_service.discard(db, user, draft_id)
    return ok()


@router.get("/rag/similar")
async def similar(demandId: int, topN: int = 5, db=Depends(get_db), user=Depends(get_current_user),
                  llm=Depends(get_llm_client)):
    clamped = min(max(topN, 1), 10)
    return ok(await rag_service.similar(db, demandId, clamped, llm=llm))
