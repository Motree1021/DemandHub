"""评论接口：增改查；仅作者可改、不可删（改留 updated_at）。"""

from fastapi import APIRouter, Depends, Query
from pydantic import Field

from app.core.deps import get_current_user, get_db
from app.core.result import ApiModel, ok
from app.services import comment_service as service

router = APIRouter(prefix="/comment")


class CommentAdd(ApiModel):
    demand_id: int
    content: str = Field(min_length=1, max_length=2000)
    mentioned_user_ids: list[int] | None = None


class CommentUpdate(ApiModel):
    content: str = Field(min_length=1, max_length=2000)


@router.post("")
async def add(payload: CommentAdd, user=Depends(get_current_user), db=Depends(get_db)):
    async with db.begin():
        comment = await service.add(db, user, demand_id=payload.demand_id,
                                    content=payload.content,
                                    mentioned_user_ids=payload.mentioned_user_ids)
    return ok(service.serialize_comment(comment, user.name))


@router.put("/{comment_id}")
async def update(comment_id: int, payload: CommentUpdate,
                 user=Depends(get_current_user), db=Depends(get_db)):
    async with db.begin():
        comment = await service.update(db, user, comment_id, content=payload.content)
    return ok(service.serialize_comment(comment, user.name))


@router.get("/list")
async def list_comments(demand_id: int = Query(..., alias="demandId"),
                        user=Depends(get_current_user), db=Depends(get_db)):
    return ok(await service.list_comments(db, user, demand_id))
