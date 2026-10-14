"""受理分派服务：受理队列 / 处理池 / 受理 / 打回 / 关闭 / 分派 / 领取 / 改型 / 我的处理单。

角色口径（P4 对齐蓝本）：受理、打回、关闭、分派 = MANAGER；改型 = EXECUTIVE；领取 = HANDLER。
并发领取用数据库行锁实现（无 Redis，既定降级口径）。
"""

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BizError, ErrorCode
from app.core.statemachine import engine
from app.db.models import Assignment, Demand, DemandRelation, User, now
from app.standards.loader import get as get_standard

URGENCY_RANK = case(
    (Demand.urgency == "CRITICAL", 0),
    (Demand.urgency == "URGENT", 1),
    else_=2,
)


async def list_queue(
    db: AsyncSession, *, urgency: str | None, type_code: str | None, page: int, size: int,
) -> tuple[list[Demand], int]:
    """受理队列：SUBMITTED 待受理，先提交先受理（FIFO）。"""
    filters = [Demand.status == "SUBMITTED"]
    if urgency:
        filters.append(Demand.urgency == urgency)
    if type_code:
        filters.append(Demand.demand_type_code == type_code)
    total = (await db.execute(select(func.count(Demand.id)).where(*filters))).scalar_one()
    rows = (await db.execute(
        select(Demand).where(*filters)
        .order_by(Demand.submitted_at.asc(), Demand.id.asc())
        .offset((page - 1) * size).limit(size)
    )).scalars().all()
    return list(rows), total


async def list_pool(
    db: AsyncSession, *, urgency: str | None, page: int, size: int,
) -> tuple[list[Demand], int]:
    """处理池：TRIAGE 已受理未认领，特急>紧急>普通，同级先提交优先。"""
    filters = [Demand.status == "TRIAGE"]
    if urgency:
        filters.append(Demand.urgency == urgency)
    total = (await db.execute(select(func.count(Demand.id)).where(*filters))).scalar_one()
    rows = (await db.execute(
        select(Demand).where(*filters)
        .order_by(URGENCY_RANK, Demand.submitted_at.asc(), Demand.id.asc())
        .offset((page - 1) * size).limit(size)
    )).scalars().all()
    return list(rows), total


async def counts(db: AsyncSession) -> dict[str, int]:
    """队列/池计数（工作台徽标）。"""
    queue = (await db.execute(select(func.count(Demand.id)).where(Demand.status == "SUBMITTED"))).scalar_one()
    pool = (await db.execute(select(func.count(Demand.id)).where(Demand.status == "TRIAGE"))).scalar_one()
    return {"queue": queue, "pool": pool}


async def list_mine(
    db: AsyncSession, user: User, *, status: str | None, page: int, size: int,
) -> tuple[list[Demand], int]:
    """我的处理单：assignee_id=本人，按更新时间倒序。"""
    filters = [Demand.assignee_id == user.id]
    if status:
        filters.append(Demand.status == status)
    else:
        filters.append(Demand.status.in_(
            ["ANALYZING", "SOLUTION_REVIEW", "CONFIRMED", "IN_PROGRESS", "ACCEPTANCE", "DONE"]))
    total = (await db.execute(select(func.count(Demand.id)).where(*filters))).scalar_one()
    rows = (await db.execute(
        select(Demand).where(*filters)
        .order_by(Demand.updated_at.desc(), Demand.id.desc())
        .offset((page - 1) * size).limit(size)
    )).scalars().all()
    return list(rows), total


async def list_all(
    db: AsyncSession, user: User, *, status: str | None, urgency: str | None,
    type_code: str | None, page: int, size: int,
) -> tuple[list[Demand], int]:
    """管理视角需求列表：ADMIN 全量；HANDLER 仅流转态（与详情可见性同口径），按更新时间倒序。"""
    from app.core.deps import is_admin
    from app.services.flow_service import FLOW_STATUSES

    filters = []
    if not is_admin(user):
        filters.append(Demand.status.in_(sorted(FLOW_STATUSES)))
    if status:
        filters.append(Demand.status == status)
    if urgency:
        filters.append(Demand.urgency == urgency)
    if type_code:
        filters.append(Demand.demand_type_code == type_code)
    total = (await db.execute(select(func.count(Demand.id)).where(*filters))).scalar_one()
    rows = (await db.execute(
        select(Demand).where(*filters)
        .order_by(Demand.updated_at.desc(), Demand.id.desc())
        .offset((page - 1) * size).limit(size)
    )).scalars().all()
    return list(rows), total


async def _get(db: AsyncSession, demand_id: int) -> Demand:
    demand = await db.get(Demand, demand_id)
    if demand is None:
        raise BizError(ErrorCode.DEMAND_NOT_FOUND)
    return demand


async def accept(db: AsyncSession, user: User, demand_id: int, comment: str | None) -> Demand:
    await _get(db, demand_id)
    await engine.transition(db, demand_id, "ACCEPT", user, comment=comment)
    return await _get(db, demand_id)


async def close(
    db: AsyncSession, user: User, demand_id: int, reason: str, duplicate_of_id: int | None,
) -> Demand:
    if not reason or not reason.strip():
        raise BizError(ErrorCode.PARAM_INVALID, "关闭原因必填")
    if duplicate_of_id is not None:
        await _get(db, duplicate_of_id)
    await engine.transition(
        db, demand_id, "CLOSE", user,
        comment=reason.strip(),
        field_update={"closed_at": now(), "close_reason": reason.strip()},
        extra={"duplicateOfId": duplicate_of_id} if duplicate_of_id else None,
    )
    if duplicate_of_id is not None and duplicate_of_id != demand_id:
        db.add(DemandRelation(from_id=demand_id, to_id=duplicate_of_id, type="DUPLICATE"))
    return await _get(db, demand_id)


async def assign(
    db: AsyncSession, user: User, demand_id: int, assignee_id: int, comment: str | None,
) -> Demand:
    """经理分派：TRIAGE → ANALYZING，指定处理人（须为 ACTIVE 且有效角色含 HANDLER/ADMIN）。"""
    from app.services import role_service

    assignee = await db.get(User, assignee_id)
    if assignee is None or assignee.status != "ACTIVE":
        raise BizError(ErrorCode.USER_NOT_FOUND)
    assignee_roles = await role_service.effective_roles(db, assignee)
    if "HANDLER" not in assignee_roles and "ADMIN" not in assignee_roles:
        raise BizError(ErrorCode.BIZ_ERROR, "被分派人不是处理人")
    await engine.transition(
        db, demand_id, "ASSIGN", user,
        comment=comment, field_update={"assignee_id": assignee_id},
        extra={"assigneeId": assignee_id, "assigneeName": assignee.name},
    )
    db.add(Assignment(
        demand_id=demand_id, from_user_id=None, to_user_id=assignee_id,
        action="ASSIGN", operator_id=user.id,
    ))
    return await _get(db, demand_id)


async def claim(db: AsyncSession, user: User, demand_id: int) -> Demand:
    """处理人领取：TRIAGE → ANALYZING。

    并发防抢（仅数据库锁，无中间件）：同事务内 SELECT ... FOR UPDATE 行锁——
    后到事务阻塞至先到事务提交，再读时 assignee 已写 → 仅一成功（1208）。
    """
    demand = (await db.execute(
        select(Demand).where(Demand.id == demand_id).with_for_update()
    )).scalar_one_or_none()
    if demand is None:
        raise BizError(ErrorCode.DEMAND_NOT_FOUND)
    if demand.assignee_id is not None:
        raise BizError(ErrorCode.DEMAND_ALREADY_CLAIMED)
    if demand.status != "TRIAGE":
        raise BizError(ErrorCode.ILLEGAL_STATE_TRANSITION, "仅待分派状态的需求可领取")
    await engine.transition(
        db, demand_id, "CLAIM", user,
        comment="处理人领取", field_update={"assignee_id": user.id},
        extra={"assigneeId": user.id},
    )
    db.add(Assignment(
        demand_id=demand_id, from_user_id=None, to_user_id=user.id,
        action="CLAIM", operator_id=user.id,
    ))
    return await _get(db, demand_id)


async def change_type(
    db: AsyncSession, user: User, demand_id: int, new_type_code: str, comment: str | None,
) -> Demand:
    """类型修正：主状态不变；subtype_code 置空重收集（蓝本口径）。"""
    if not new_type_code:
        raise BizError(ErrorCode.PARAM_INVALID, "新需求类型必填")
    get_standard(new_type_code)  # 非法类型抛 DEMAND_TYPE_INVALID
    demand = await _get(db, demand_id)
    if demand.demand_type_code == new_type_code:
        raise BizError(ErrorCode.BIZ_ERROR, "新类型与原类型相同")
    # P5 组织回填（蓝本口径）：类型修正 → 承接组织随新类型默认组织重路由
    from app.services import org_service
    new_org_id = await org_service.resolve_type_org_id(db, new_type_code)
    await engine.transition(
        db, demand_id, "CHANGE_TYPE", user,
        comment=comment or "类型修正",
        field_update={"demand_type_code": new_type_code, "subtype_code": None,
                      "assignee_org_id": new_org_id},
        extra={"fromType": demand.demand_type_code, "toType": new_type_code},
    )
    return await _get(db, demand_id)
