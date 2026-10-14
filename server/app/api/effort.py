"""工时接口：登记/修改（仅本人）/列表/按需求汇总。"""

from datetime import date

from fastapi import APIRouter, Depends, Query
from pydantic import Field

from app.core.deps import get_db, require_role
from app.core.result import ApiModel, ok
from app.services import effort_service as service

router = APIRouter(prefix="/effort")

handler_plus = require_role("ADMIN", "HANDLER")


class EffortAdd(ApiModel):
    demand_id: int
    work_date: date
    hours: float = Field(gt=0, le=24)
    remark: str | None = Field(default=None, max_length=512)


class EffortUpdate(ApiModel):
    work_date: date
    hours: float = Field(gt=0, le=24)
    remark: str | None = Field(default=None, max_length=512)


@router.post("")
async def add(payload: EffortAdd, user=Depends(handler_plus), db=Depends(get_db)):
    async with db.begin():
        effort = await service.add(db, user, demand_id=payload.demand_id,
                                   work_date=payload.work_date, hours=payload.hours,
                                   remark=payload.remark)
    return ok(service.serialize_effort(effort, user.name))


@router.put("/{effort_id}")
async def update(effort_id: int, payload: EffortUpdate,
                 user=Depends(handler_plus), db=Depends(get_db)):
    async with db.begin():
        effort = await service.update(db, user, effort_id, work_date=payload.work_date,
                                      hours=payload.hours, remark=payload.remark)
    return ok(service.serialize_effort(effort, user.name))


@router.get("/list")
async def list_efforts(demand_id: int = Query(..., alias="demandId"),
                       user=Depends(handler_plus), db=Depends(get_db)):
    return ok(await service.list_efforts(db, user, demand_id))


@router.get("/summary")
async def summary(demand_id: int = Query(..., alias="demandId"),
                  user=Depends(handler_plus), db=Depends(get_db)):
    return ok(await service.summary(db, user, demand_id))
