"""评论服务：增改查；仅作者可改、不可物理删除（改留 updated_at）。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BizError, ErrorCode
from app.core.result import encode
from app.db.models import Comment, User, now
from app.services.flow_service import get_viewable


def serialize_comment(comment: Comment, author_name: str | None = None) -> dict:
    return {
        "id": comment.id, "demandId": comment.demand_id,
        "authorId": comment.author_id, "authorName": author_name,
        "content": comment.content, "mentionedUserIds": comment.mentioned_user_ids,
        "createdAt": encode(comment.created_at), "updatedAt": encode(comment.updated_at),
    }


async def add(
    db: AsyncSession, user: User, *,
    demand_id: int, content: str, mentioned_user_ids: list[int] | None,
) -> Comment:
    await get_viewable(db, user, demand_id)
    content = (content or "").strip()
    if not content:
        raise BizError(ErrorCode.PARAM_INVALID, "评论内容必填")
    comment = Comment(
        demand_id=demand_id, author_id=user.id, content=content,
        mentioned_user_ids=",".join(str(i) for i in mentioned_user_ids) if mentioned_user_ids else None,
    )
    db.add(comment)
    await db.flush()
    return comment


async def update(db: AsyncSession, user: User, comment_id: int, *, content: str) -> Comment:
    comment = await db.get(Comment, comment_id)
    if comment is None:
        raise BizError(ErrorCode.NOT_FOUND, "评论不存在")
    if comment.author_id != user.id:
        raise BizError(ErrorCode.FORBIDDEN, "仅评论作者可修改")
    content = (content or "").strip()
    if not content:
        raise BizError(ErrorCode.PARAM_INVALID, "评论内容必填")
    comment.content = content
    comment.updated_at = now()
    await db.flush()
    return comment


async def list_comments(db: AsyncSession, user: User, demand_id: int) -> list[dict]:
    await get_viewable(db, user, demand_id)
    rows = (await db.execute(
        select(Comment, User.name)
        .join(User, Comment.author_id == User.id)
        .where(Comment.demand_id == demand_id)
        .order_by(Comment.id)
    )).all()
    return [serialize_comment(c, name) for c, name in rows]
