"""工时服务：登记 / 修改（仅本人）/ 列表 / 按需求汇总。终态需求不可登记。"""

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BizError, ErrorCode
from app.core.result import encode
from app.core.statemachine import TERMINAL_STATUSES
from app.db.models import Demand, EffortLog, User, now
from app.services.flow_service import get_viewable


def serialize_effort(effort: EffortLog, user_name: str | None = None) -> dict:
    return {
        "id": effort.id, "demandId": effort.demand_id,
        "userId": effort.user_id, "userName": user_name,
        "hours": float(effort.hours), "workDate": encode(effort.work_date),
        "remark": effort.remark,
        "createdAt": encode(effort.created_at), "updatedAt": encode(effort.updated_at),
    }


def _validate_hours(hours: float) -> None:
    if hours is None or hours <= 0 or hours > 24:
        raise BizError(ErrorCode.PARAM_INVALID, "工时须大于 0 且不超过 24 小时")


async def _require_not_terminal(db: AsyncSession, user: User, demand_id: int) -> Demand:
    demand = await get_viewable(db, user, demand_id)
    if demand.status in TERMINAL_STATUSES:
        raise BizError(ErrorCode.ILLEGAL_STATE_TRANSITION, "已完成或已关闭的需求不可登记工时")
    return demand


async def add(
    db: AsyncSession, user: User, *,
    demand_id: int, work_date: date, hours: float, remark: str | None,
) -> EffortLog:
    await _require_not_terminal(db, user, demand_id)
    _validate_hours(hours)
    effort = EffortLog(
        demand_id=demand_id, user_id=user.id,
        work_date=work_date, hours=Decimal(str(hours)), remark=remark,
    )
    db.add(effort)
    await db.flush()
    return effort


async def update(
    db: AsyncSession, user: User, effort_id: int, *,
    work_date: date, hours: float, remark: str | None,
) -> EffortLog:
    effort = await db.get(EffortLog, effort_id)
    if effort is None:
        raise BizError(ErrorCode.NOT_FOUND, "工时记录不存在")
    if effort.user_id != user.id:
        raise BizError(ErrorCode.FORBIDDEN, "仅本人可修改工时")
    await _require_not_terminal(db, user, effort.demand_id)
    _validate_hours(hours)
    effort.work_date = work_date
    effort.hours = Decimal(str(hours))
    effort.remark = remark
    effort.updated_at = now()
    await db.flush()
    return effort


async def list_efforts(db: AsyncSession, user: User, demand_id: int) -> list[dict]:
    await get_viewable(db, user, demand_id)
    rows = (await db.execute(
        select(EffortLog, User.name)
        .join(User, EffortLog.user_id == User.id)
        .where(EffortLog.demand_id == demand_id)
        .order_by(EffortLog.work_date.desc(), EffortLog.id)
    )).all()
    return [serialize_effort(e, name) for e, name in rows]


async def summary(db: AsyncSession, user: User, demand_id: int) -> dict:
    """按需求汇总：总工时 + 按人 + 按日期。"""
    await get_viewable(db, user, demand_id)
    total = (await db.execute(
        select(func.coalesce(func.sum(EffortLog.hours), 0)).where(EffortLog.demand_id == demand_id)
    )).scalar_one()
    by_user = (await db.execute(
        select(EffortLog.user_id, User.name, func.sum(EffortLog.hours))
        .join(User, EffortLog.user_id == User.id)
        .where(EffortLog.demand_id == demand_id)
        .group_by(EffortLog.user_id, User.name)
    )).all()
    by_date = (await db.execute(
        select(EffortLog.work_date, func.sum(EffortLog.hours))
        .where(EffortLog.demand_id == demand_id)
        .group_by(EffortLog.work_date).order_by(EffortLog.work_date)
    )).all()
    return {
        "totalHours": float(total),
        "byUser": [{"userId": uid, "userName": name, "hours": float(h)} for uid, name, h in by_user],
        "byDate": [{"workDate": encode(d), "hours": float(h)} for d, h in by_date],
    }
