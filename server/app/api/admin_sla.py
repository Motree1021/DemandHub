"""SLA 配置管理接口（仅 ADMIN，蓝本 SlaConfigAdminController）：列表/新增/修改/删除。

白话：SLA = 需求在某状态最多能"泡"多久。黄牌=快到期提醒，红牌=已超时催办。"""

from fastapi import APIRouter, Depends
from pydantic import Field

from app.core.deps import get_db, require_admin
from app.core.result import ApiModel, ok
from app.services import sla_admin_service as service

router = APIRouter(prefix="/admin/sla-configs", dependencies=[Depends(require_admin)])


class SlaSave(ApiModel):
    demand_type_code: str = Field(min_length=1, max_length=32)
    status: str = Field(min_length=1, max_length=32)
    warn_minutes: int = Field(gt=0)
    max_minutes: int = Field(gt=0)
    remark: str | None = Field(default=None, max_length=512)


class SlaUpdate(ApiModel):
    warn_minutes: int | None = Field(default=None, gt=0)
    max_minutes: int | None = Field(default=None, gt=0)
    enabled: bool | None = None
    remark: str | None = Field(default=None, max_length=512)


@router.get("")
async def list_all(demandTypeCode: str | None = None, db=Depends(get_db)):
    return ok(await service.list_configs(db, demandTypeCode))


@router.post("")
async def create(payload: SlaSave, db=Depends(get_db)):
    async with db.begin():
        row = await service.create_config(
            db, demand_type_code=payload.demand_type_code, status=payload.status,
            warn_minutes=payload.warn_minutes, max_minutes=payload.max_minutes,
            remark=payload.remark)
    return ok(service.serialize_config(row))


@router.put("/{config_id}")
async def update(config_id: int, payload: SlaUpdate, db=Depends(get_db)):
    async with db.begin():
        row = await service.update_config(
            db, config_id, warn_minutes=payload.warn_minutes, max_minutes=payload.max_minutes,
            enabled=payload.enabled, remark=payload.remark)
    return ok(service.serialize_config(row))


@router.delete("/{config_id}")
async def remove(config_id: int, db=Depends(get_db)):
    async with db.begin():
        await service.delete_config(db, config_id)
    return ok(None)
