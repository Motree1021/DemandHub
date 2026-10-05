from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy import select

from app.core.deps import get_db, require_admin
from app.core.errors import BizError, ErrorCode
from app.core.result import ok
from app.db.models import Demand
from app.services import demand_service as service
from app.services.export import to_xlsx

router = APIRouter(prefix="/admin/demand", dependencies=[Depends(require_admin)])


def filter_args(status, type_code, date_from, date_to):
    if date_from and date_to and date_from > date_to:
        raise BizError(ErrorCode.PARAM_INVALID, "开始日期不能晚于结束日期")
    return dict(status=status, type_code=type_code, date_from=date_from, date_to=date_to)


@router.get("/list")
async def list_all(page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
    status: Literal["DRAFT", "SUBMITTED", "CLOSED"] | None = None,
    type_code: Literal["TECH", "MATL", "TRAIN"] | None = Query(None, alias="type"),
    date_from: date | None = Query(None, alias="from"), date_to: date | None = Query(None, alias="to"),
    db=Depends(get_db)):
    return ok(await service.list_records(db, page=page, size=size,
        **filter_args(status, type_code, date_from, date_to)))


@router.get("/export.xlsx")
async def export_all(status: Literal["DRAFT", "SUBMITTED", "CLOSED"] | None = None,
    type_code: Literal["TECH", "MATL", "TRAIN"] | None = Query(None, alias="type"),
    date_from: date | None = Query(None, alias="from"), date_to: date | None = Query(None, alias="to"),
    db=Depends(get_db)):
    statement = service.filters(select(Demand), **filter_args(status, type_code, date_from, date_to))
    demands = (await db.execute(statement.order_by(Demand.id))).scalars().all()
    standards = {d.id: await service.standard_for(db, d) for d in demands}
    return Response(to_xlsx(demands, standards), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="demandhub.xlsx"'})
