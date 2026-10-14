"""通知信箱与偏好接口（蓝本 NotificationController + PreferenceController）。

mine/unread-count/read/read-all 为登录用户信箱；preferences 查改本人通知偏好（TODO 不可关闭）。
"""

from fastapi import APIRouter, Depends, Query

from app.core.deps import get_current_user, get_db
from app.core.result import ApiModel, ok
from app.services import notification_service as service

router = APIRouter(prefix="/notification")


class PreferenceBody(ApiModel):
    notify_type: str
    enabled: bool


@router.get("/mine")
async def mine(
    current: int = Query(1, ge=1), size: int = Query(10, ge=1, le=100),
    is_read: bool | None = Query(None, alias="isRead"),
    user=Depends(get_current_user), db=Depends(get_db),
):
    return ok(await service.page_mine(db, user, current=current, size=size, is_read=is_read))


@router.get("/mine/unread-count")
async def unread(user=Depends(get_current_user), db=Depends(get_db)):
    return ok({"count": await service.unread_count(db, user)})


@router.put("/mine/read-all")
async def read_all(user=Depends(get_current_user), db=Depends(get_db)):
    async with db.begin():
        updated = await service.mark_all_read(db, user)
    return ok({"updated": updated})


@router.put("/{notification_id}/read")
async def read(notification_id: int, user=Depends(get_current_user), db=Depends(get_db)):
    async with db.begin():
        updated = await service.mark_read(db, user, notification_id)
    return ok({"updated": updated})


@router.get("/preferences")
async def preferences(user=Depends(get_current_user), db=Depends(get_db)):
    return ok(await service.get_preferences(db, user))


@router.put("/preferences")
async def save_preference(payload: PreferenceBody, user=Depends(get_current_user), db=Depends(get_db)):
    async with db.begin():
        await service.set_preference(db, user, payload.notify_type, payload.enabled)
    return ok({"success": True})
