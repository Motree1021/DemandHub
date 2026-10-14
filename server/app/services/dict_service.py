"""业务字典服务（蓝本 SysDictAdminService）：分组 CRUD + 登录用户查 ACTIVE 项。

口径：dict_type+item_code 唯一；编码创建后不可改（历史数据按编码关联）；
无"被引用禁止停用"校验，停用后历史数据仍按原名称展示（快照口径）。
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BizError, ErrorCode
from app.db.models import SysDict

ACTIVE = "ACTIVE"
DISABLED = "DISABLED"
STATUSES = (ACTIVE, DISABLED)


def serialize_dict(row: SysDict) -> dict:
    return {
        "id": row.id,
        "dictType": row.dict_type,
        "itemCode": row.item_code,
        "itemName": row.item_name,
        "sort": row.sort,
        "status": row.status,
        "createdAt": row.created_at.isoformat(sep=" ", timespec="seconds") if row.created_at else None,
        "updatedAt": row.updated_at.isoformat(sep=" ", timespec="seconds") if row.updated_at else None,
    }


async def list_dicts(db: AsyncSession, dict_type: str | None = None) -> list[dict]:
    stmt = select(SysDict).order_by(SysDict.dict_type, SysDict.sort, SysDict.id)
    if dict_type:
        stmt = stmt.where(SysDict.dict_type == dict_type)
    rows = (await db.execute(stmt)).scalars().all()
    return [serialize_dict(row) for row in rows]


async def list_types(db: AsyncSession) -> list[str]:
    rows = (await db.execute(
        select(SysDict.dict_type).distinct().order_by(SysDict.dict_type))).scalars().all()
    return list(rows)


async def list_active(db: AsyncSession, dict_type: str) -> list[dict]:
    """登录用户查询：仅 ACTIVE 项（蓝本 Redis 60s 缓存，移植版量小直查表）。"""
    rows = (await db.execute(
        select(SysDict).where(SysDict.dict_type == dict_type, SysDict.status == ACTIVE)
        .order_by(SysDict.sort, SysDict.id))).scalars().all()
    return [serialize_dict(row) for row in rows]


async def create_dict(db: AsyncSession, *, dict_type: str, item_code: str,
                      item_name: str, sort: int = 0) -> SysDict:
    exists = (await db.execute(
        select(func.count(SysDict.id)).where(
            SysDict.dict_type == dict_type, SysDict.item_code == item_code))).scalar_one()
    if exists:
        raise BizError(ErrorCode.CONFLICT, f"字典项已存在: {dict_type}/{item_code}")
    row = SysDict(dict_type=dict_type, item_code=item_code, item_name=item_name,
                  sort=sort, status=ACTIVE)
    db.add(row)
    await db.flush()
    return row


async def update_dict(db: AsyncSession, dict_id: int, *, item_name: str | None = None,
                      sort: int | None = None, status: str | None = None) -> SysDict:
    """仅名称/排序/状态可改；dict_type/item_code 不可改（蓝本口径）。"""
    row = (await db.execute(select(SysDict).where(SysDict.id == dict_id))).scalar_one_or_none()
    if row is None:
        raise BizError(ErrorCode.NOT_FOUND, "字典项不存在")
    if status is not None and status not in STATUSES:
        raise BizError(ErrorCode.PARAM_INVALID, f"状态仅允许 {'/'.join(STATUSES)}")
    if item_name is not None:
        row.item_name = item_name
    if sort is not None:
        row.sort = sort
    if status is not None:
        row.status = status
    await db.flush()
    return row
