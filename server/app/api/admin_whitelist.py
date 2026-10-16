"""渠道白名单管理接口（仅 ADMIN，2026-10-16 方案定稿）。

登录拦截见 whitelist_service.assert_allowed（channel-sso / channel-parameters 两入口共用）；
dev-login / test-login 不纳入校验。全局开关与拦截页联系引导挂渠道行；全部操作落留痕表。
批量添加前端解析仅为体验，服务层对每条重复执行格式/重复校验兜底。"""

from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import Field

from app.core.deps import get_db, require_admin
from app.core.result import ApiModel, ok
from app.services import whitelist_service as service

router = APIRouter(prefix="/admin/channels", dependencies=[Depends(require_admin)])

StatusValue = Literal["ENABLED", "DISABLED"]


class AddEntry(ApiModel):
    channel_user_id: str = Field(min_length=1, max_length=64)
    display_name: str | None = Field(None, max_length=64)


class BatchEntry(ApiModel):
    # 宽松上限：格式合规性由服务层判定（不合规归入 invalid 返回，不报错整批拒绝）
    channel_user_id: str = Field(min_length=1, max_length=128)
    display_name: str | None = Field(None, max_length=64)


class BatchAdd(ApiModel):
    entries: list[BatchEntry] = Field(min_length=1, max_length=service.BATCH_LIMIT)


class StatusUpdate(ApiModel):
    status: StatusValue


class ConfigUpdate(ApiModel):
    whitelist_enabled: bool | None = None
    whitelist_contact: str | None = Field(None, max_length=255)


@router.get("/{channel_code}/whitelist")
async def list_entries(channel_code: str, page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
                       keyword: str | None = Query(None, max_length=64), status: StatusValue | None = None,
                       db=Depends(get_db)):
    return ok(await service.list_entries(db, channel_code, page=page, size=size,
                                         keyword=keyword, status=status))


@router.post("/{channel_code}/whitelist")
async def add_entry(channel_code: str, payload: AddEntry,
                    admin=Depends(require_admin), db=Depends(get_db)):
    async with db.begin():
        row = await service.add_entry(db, channel_code,
                                      channel_user_id=payload.channel_user_id.strip(),
                                      display_name=(payload.display_name or "").strip() or None,
                                      operator=admin)
    return ok(service.serialize_entry(row))


@router.post("/{channel_code}/whitelist/batch")
async def add_batch(channel_code: str, payload: BatchAdd,
                    admin=Depends(require_admin), db=Depends(get_db)):
    entries = [{"channel_user_id": e.channel_user_id.strip(),
                "display_name": (e.display_name or "").strip() or None} for e in payload.entries]
    async with db.begin():
        result = await service.add_batch(db, channel_code, entries=entries, operator=admin)
    return ok(result)


@router.put("/whitelist/{entry_id}/status")
async def update_status(entry_id: int, payload: StatusUpdate,
                        admin=Depends(require_admin), db=Depends(get_db)):
    async with db.begin():
        row = await service.update_entry_status(db, entry_id, status=payload.status, operator=admin)
    return ok(service.serialize_entry(row))


@router.delete("/whitelist/{entry_id}")
async def remove_entry(entry_id: int, admin=Depends(require_admin), db=Depends(get_db)):
    async with db.begin():
        await service.remove_entry(db, entry_id, operator=admin)
    return ok(None)


@router.get("/{channel_code}/whitelist/logs")
async def list_logs(channel_code: str, page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
                    db=Depends(get_db)):
    return ok(await service.list_logs(db, channel_code, page=page, size=size))


@router.get("/{channel_code}/whitelist/pending")
async def list_pending(channel_code: str, db=Depends(get_db)):
    return ok(await service.list_pending(db, channel_code))


@router.put("/{channel_code}/whitelist/config")
async def update_config(channel_code: str, payload: ConfigUpdate,
                        admin=Depends(require_admin), db=Depends(get_db)):
    async with db.begin():
        channel = await service.update_config(db, channel_code, enabled=payload.whitelist_enabled,
                                              contact=payload.whitelist_contact, operator=admin)
    return ok({"whitelistEnabled": bool(channel.whitelist_enabled),
               "whitelistContact": channel.whitelist_contact})
