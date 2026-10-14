"""渠道管理接口（仅 ADMIN，蓝本 ChannelAdminController，决策②裁剪版）。

只做登记/启停：渠道无新增/删除（SQL 种子注册），SSO 对接参数走 .env 不迁表、不动登录链路。
部门未映射校准：登录部门映射未命中的记录清单，管理员处理完映射后删行。"""

from fastapi import APIRouter, Depends
from pydantic import Field

from app.core.deps import get_db, require_admin
from app.core.result import ApiModel, ok
from app.services import channel_service as service

router = APIRouter(prefix="/admin/channels", dependencies=[Depends(require_admin)])


class StatusUpdate(ApiModel):
    status: str = Field(min_length=1, max_length=16)


@router.get("")
async def list_all(db=Depends(get_db)):
    return ok(await service.list_channels(db))


@router.put("/{channel_id}/status")
async def update_status(channel_id: int, payload: StatusUpdate, db=Depends(get_db)):
    async with db.begin():
        row = await service.update_status(db, channel_id, status=payload.status)
    return ok(service.serialize_channel(row))


@router.get("/dept-unmapped")
async def list_unmapped(channelCode: str | None = None, db=Depends(get_db)):
    return ok(await service.list_unmapped(db, channelCode))


@router.delete("/dept-unmapped/{unmapped_id}")
async def delete_unmapped(unmapped_id: int, db=Depends(get_db)):
    async with db.begin():
        await service.delete_unmapped(db, unmapped_id)
    return ok(None)
