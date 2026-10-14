"""需求类型服务（蓝本 DemandTypeAdminService）：表管注册/启停/状态机绑定/排序。

口径：type_code 大写 ^[A-Z0-9_]{2,16}$ 唯一且创建后不可改；
state_machine_key 只校验非空与长度 ≤64（蓝本口径：不验存在，运行时未命中回落 DEFAULT 内置表）；
default_org_id 非空时必须在 demand_org 存在；五区字段标准仍走 yaml 快照。
"""

import re

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BizError, ErrorCode
from app.db.models import DemandOrg, DemandType

ACTIVE = "ACTIVE"
DISABLED = "DISABLED"
STATUSES = (ACTIVE, DISABLED)
TYPE_CODE_PATTERN = re.compile(r"^[A-Z0-9_]{2,16}$")


def serialize_type(row: DemandType) -> dict:
    return {
        "id": row.id,
        "typeCode": row.type_code,
        "typeName": row.type_name,
        "parentTypeCode": row.parent_type_code,
        "defaultOrgId": row.default_org_id,
        "stateMachineKey": row.state_machine_key,
        "slaConfig": row.sla_config,
        "sort": row.sort,
        "status": row.status,
        "createdAt": row.created_at.isoformat(sep=" ", timespec="seconds") if row.created_at else None,
        "updatedAt": row.updated_at.isoformat(sep=" ", timespec="seconds") if row.updated_at else None,
    }


async def list_types(db: AsyncSession) -> list[dict]:
    rows = (await db.execute(
        select(DemandType).order_by(DemandType.sort, DemandType.id))).scalars().all()
    return [serialize_type(row) for row in rows]


async def list_active(db: AsyncSession) -> list[DemandType]:
    """登录下拉用（/standards 列表的数据源）：仅 ACTIVE，按 sort+id。"""
    return (await db.execute(
        select(DemandType).where(DemandType.status == ACTIVE)
        .order_by(DemandType.sort, DemandType.id))).scalars().all()


def _check_state_machine_key(state_machine_key: str) -> None:
    if not state_machine_key or len(state_machine_key) > 64:
        raise BizError(ErrorCode.PARAM_INVALID, "状态机 key 必填且长度不超过 64")


async def _check_org_exists(db: AsyncSession, default_org_id: int | None) -> None:
    if default_org_id is None:
        return
    exists = (await db.execute(
        select(func.count(DemandOrg.id)).where(DemandOrg.id == default_org_id))).scalar_one()
    if not exists:
        raise BizError(ErrorCode.PARAM_INVALID, f"默认承接组织不存在: {default_org_id}")


async def create_type(db: AsyncSession, *, type_code: str, type_name: str,
                      default_org_id: int | None = None, state_machine_key: str = "DEFAULT",
                      sort: int = 0) -> DemandType:
    code = type_code.strip().upper()
    if not TYPE_CODE_PATTERN.match(code):
        raise BizError(ErrorCode.PARAM_INVALID, "类型编码须为 2-16 位大写字母/数字/下划线")
    _check_state_machine_key(state_machine_key)
    await _check_org_exists(db, default_org_id)
    exists = (await db.execute(
        select(func.count(DemandType.id)).where(DemandType.type_code == code))).scalar_one()
    if exists:
        raise BizError(ErrorCode.CONFLICT, f"类型编码已存在: {code}")
    row = DemandType(type_code=code, type_name=type_name, default_org_id=default_org_id,
                     state_machine_key=state_machine_key, sort=sort, status=ACTIVE)
    db.add(row)
    await db.flush()
    return row


async def update_type(db: AsyncSession, type_id: int, *, type_name: str | None = None,
                      default_org_id: int | None = None, state_machine_key: str | None = None,
                      sort: int | None = None, status: str | None = None) -> DemandType:
    """type_code 不可改（蓝本口径）；org/key/sort/status 可改。"""
    row = (await db.execute(
        select(DemandType).where(DemandType.id == type_id))).scalar_one_or_none()
    if row is None:
        raise BizError(ErrorCode.NOT_FOUND, "需求类型不存在")
    if status is not None and status not in STATUSES:
        raise BizError(ErrorCode.PARAM_INVALID, f"状态仅允许 {'/'.join(STATUSES)}")
    if state_machine_key is not None:
        _check_state_machine_key(state_machine_key)
    if default_org_id is not None:
        await _check_org_exists(db, default_org_id)
    if type_name is not None:
        row.type_name = type_name
    if default_org_id is not None:
        row.default_org_id = default_org_id
    if state_machine_key is not None:
        row.state_machine_key = state_machine_key
    if sort is not None:
        row.sort = sort
    if status is not None:
        row.status = status
    await db.flush()
    return row
