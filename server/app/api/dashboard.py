"""统计看板接口（蓝本 DashboardController）。

manager/org 为经理与管理者看板（实时 SQL，一期 DataScope=全量）；
stat-refresh 手动重算 demand_stat_daily 当日快照（ADMIN/EXECUTIVE，ADMIN 经 is_admin 直通）。
"""

from datetime import date

from fastapi import APIRouter, Depends, Query

from app.core.deps import get_db, require_role
from app.core.result import ok
from app.services import stat_service as service

router = APIRouter(prefix="/dashboard")


@router.get("/manager")
async def manager(
    range_kind: str = Query("month", alias="range"),
    from_date: date | None = Query(None, alias="from"),
    to_date: date | None = Query(None, alias="to"),
    user=Depends(require_role("EXECUTIVE", "MANAGER")), db=Depends(get_db),
):
    return ok(await service.manager_board(db, range_kind, from_date, to_date))


@router.get("/org")
async def org(
    range_kind: str = Query("month", alias="range"),
    from_date: date | None = Query(None, alias="from"),
    to_date: date | None = Query(None, alias="to"),
    user=Depends(require_role("EXECUTIVE", "MANAGER")), db=Depends(get_db),
):
    return ok(await service.org_board(db, range_kind, from_date, to_date))


@router.post("/stat-refresh")
async def stat_refresh(user=Depends(require_role("EXECUTIVE")), db=Depends(get_db)):
    async with db.begin():
        rows = await service.refresh_today(db)
    return ok({"rows": rows})
