"""需求关系服务：增删查；PARENT/DEPENDS/DUPLICATE/SPLIT 四类，双向可查。"""

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BizError, ErrorCode
from app.core.result import encode
from app.db.models import Demand, DemandRelation, User

RELATION_TYPES = {"PARENT", "DEPENDS", "DUPLICATE", "SPLIT"}


async def add(
    db: AsyncSession, user: User, *,
    demand_id: int, related_demand_id: int, relation_type: str,
) -> DemandRelation:
    if relation_type not in RELATION_TYPES:
        raise BizError(ErrorCode.PARAM_INVALID, "关系类型无效")
    if demand_id == related_demand_id:
        raise BizError(ErrorCode.PARAM_INVALID, "不能关联自身")
    for did in (demand_id, related_demand_id):
        if await db.get(Demand, did) is None:
            raise BizError(ErrorCode.DEMAND_NOT_FOUND, "关联的需求不存在")
    relation = DemandRelation(from_id=demand_id, to_id=related_demand_id, type=relation_type)
    db.add(relation)
    try:
        await db.flush()
    except IntegrityError:
        raise BizError(ErrorCode.BIZ_ERROR, "该关联已存在") from None
    return relation


async def delete(db: AsyncSession, user: User, relation_id: int) -> None:
    relation = await db.get(DemandRelation, relation_id)
    if relation is None:
        raise BizError(ErrorCode.NOT_FOUND, "关系不存在")
    await db.delete(relation)
    await db.flush()


async def list_relations(db: AsyncSession, user: User, demand_id: int) -> list[dict]:
    """双向查询：from=我 或 to=我 的关系都返回，并标注方向。"""
    rows = (await db.execute(
        select(DemandRelation)
        .where(or_(DemandRelation.from_id == demand_id, DemandRelation.to_id == demand_id))
        .order_by(DemandRelation.id)
    )).scalars().all()
    if not rows:
        return []
    other_ids = {r.to_id if r.from_id == demand_id else r.from_id for r in rows}
    demands = (await db.execute(
        select(Demand).where(Demand.id.in_(other_ids))
    )).scalars().all()
    demand_map = {d.id: d for d in demands}
    items = []
    for r in rows:
        other_id = r.to_id if r.from_id == demand_id else r.from_id
        other = demand_map.get(other_id)
        items.append({
            "id": r.id, "type": r.type,
            "direction": "OUT" if r.from_id == demand_id else "IN",
            "otherDemandId": other_id,
            "otherDemandNo": other.demand_no if other else None,
            "otherTitle": other.title if other else None,
            "otherStatus": other.status if other else None,
            "createdAt": encode(r.created_at),
        })
    return items
