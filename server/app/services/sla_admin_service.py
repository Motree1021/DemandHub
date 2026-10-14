"""SLA 配置管理服务（蓝本 SlaConfigAdminService）：类型 × 状态 组合的停留时长阈值 CRUD。

口径：uk(demand_type_code, status) 冲突 409；warn/max 必须为正且 warn < max（黄档先于红档）；
status 仅允许主状态（ON_HOLD 是叠加态不是主状态，配置了也永远扫不到）；
与字典不同，SLA 配置允许删除（蓝本有 DELETE）。"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BizError, ErrorCode
from app.core.statemachine.engine import ON_HOLD, STATUS_LABELS
from app.db.models import SlaConfig

MAIN_STATUSES = tuple(s for s in STATUS_LABELS if s != ON_HOLD)


def serialize_config(row: SlaConfig) -> dict:
    return {
        "id": row.id,
        "demandTypeCode": row.demand_type_code,
        "status": row.status,
        "warnMinutes": row.warn_minutes,
        "maxMinutes": row.max_minutes,
        "enabled": row.enabled,
        "remark": row.remark,
        "createdAt": row.created_at.isoformat(sep=" ", timespec="seconds") if row.created_at else None,
        "updatedAt": row.updated_at.isoformat(sep=" ", timespec="seconds") if row.updated_at else None,
    }


async def list_configs(db: AsyncSession, demand_type_code: str | None = None) -> list[dict]:
    stmt = select(SlaConfig).order_by(SlaConfig.demand_type_code, SlaConfig.id)
    if demand_type_code:
        stmt = stmt.where(SlaConfig.demand_type_code == demand_type_code)
    rows = (await db.execute(stmt)).scalars().all()
    return [serialize_config(row) for row in rows]


def _check(status: str, warn_minutes: int, max_minutes: int) -> None:
    if status not in MAIN_STATUSES:
        raise BizError(ErrorCode.PARAM_INVALID,
                       f"状态仅允许主状态：{'/'.join(MAIN_STATUSES)}")
    if warn_minutes <= 0 or max_minutes <= 0:
        raise BizError(ErrorCode.PARAM_INVALID, "预警/告警分钟数必须为正整数")
    if warn_minutes >= max_minutes:
        raise BizError(ErrorCode.PARAM_INVALID, "预警分钟数必须小于告警分钟数（黄档先于红档）")


async def create_config(db: AsyncSession, *, demand_type_code: str, status: str,
                        warn_minutes: int, max_minutes: int,
                        remark: str | None = None) -> SlaConfig:
    _check(status, warn_minutes, max_minutes)
    exists = (await db.execute(
        select(func.count(SlaConfig.id)).where(
            SlaConfig.demand_type_code == demand_type_code,
            SlaConfig.status == status))).scalar_one()
    if exists:
        raise BizError(ErrorCode.CONFLICT, f"SLA 配置已存在: {demand_type_code}/{status}")
    row = SlaConfig(demand_type_code=demand_type_code, status=status,
                    warn_minutes=warn_minutes, max_minutes=max_minutes,
                    enabled=True, remark=remark)
    db.add(row)
    await db.flush()
    return row


async def update_config(db: AsyncSession, config_id: int, *, warn_minutes: int | None = None,
                        max_minutes: int | None = None, enabled: bool | None = None,
                        remark: str | None = None) -> SlaConfig:
    """demand_type_code/status 不可改（组合即身份，要换组合请删除重建）。"""
    row = (await db.execute(
        select(SlaConfig).where(SlaConfig.id == config_id))).scalar_one_or_none()
    if row is None:
        raise BizError(ErrorCode.NOT_FOUND, "SLA 配置不存在")
    new_warn = warn_minutes if warn_minutes is not None else row.warn_minutes
    new_max = max_minutes if max_minutes is not None else row.max_minutes
    _check(row.status, new_warn, new_max)
    row.warn_minutes, row.max_minutes = new_warn, new_max
    if enabled is not None:
        row.enabled = enabled
    if remark is not None:
        row.remark = remark
    await db.flush()
    return row


async def delete_config(db: AsyncSession, config_id: int) -> None:
    row = (await db.execute(
        select(SlaConfig).where(SlaConfig.id == config_id))).scalar_one_or_none()
    if row is None:
        raise BizError(ErrorCode.NOT_FOUND, "SLA 配置不存在")
    await db.delete(row)
    await db.flush()
