"""受理分派接口：队列/池/计数/受理/打回/关闭/分派/领取/退回池/改型/我的处理单。

角色口径（P4 对齐蓝本 TriageController）：受理/打回/关闭/分派 = MANAGER；改型 = EXECUTIVE；
池/领取/我的处理单 = HANDLER 以上；查看类放行 MANAGER/EXECUTIVE；ADMIN 一律直通。
并发领取仅数据库行锁（无中间件，既定降级口径）。
"""

from fastapi import APIRouter, Depends, Query
from pydantic import Field

from app.core.deps import get_db, require_role
from app.core.result import ApiModel, ok
from app.services import demand_service, triage_service
from app.services.flow_service import return_pool

router = APIRouter(prefix="/triage")

# 工作台查看类：处理人/经理/管理者均可（ADMIN 直通）
workbench = require_role("HANDLER", "MANAGER", "EXECUTIVE")
manager_only = require_role("MANAGER")


class CommentBody(ApiModel):
    comment: str | None = Field(default=None, max_length=512)


class ReturnBody(ApiModel):
    reason: str = Field(min_length=1, max_length=512)


class CloseBody(ApiModel):
    reason: str = Field(min_length=1, max_length=256)
    duplicate_of_id: int | None = None


class AssignBody(ApiModel):
    assignee_id: int
    comment: str | None = Field(default=None, max_length=512)


class ChangeTypeBody(ApiModel):
    new_type_code: str = Field(min_length=1, max_length=32)
    comment: str | None = Field(default=None, max_length=512)


async def _serialize_page(db, rows, total, page, size):
    names = await demand_service.assignee_names_map(db, rows)
    return {
        "records": [demand_service.serialize_demand(d, assignee_name=names.get(d.assignee_id)) for d in rows],
        "total": total, "size": size, "current": page, "pages": (total + size - 1) // size,
    }


@router.get("/queue")
async def queue(
    urgency: str | None = None, type_code: str | None = None,
    page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
    user=Depends(require_role("MANAGER", "EXECUTIVE")), db=Depends(get_db),
):
    rows, total = await triage_service.list_queue(
        db, user, urgency=urgency, type_code=type_code, page=page, size=size)
    return ok(await _serialize_page(db, rows, total, page, size))


@router.get("/pool")
async def pool(
    urgency: str | None = None,
    page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
    user=Depends(workbench), db=Depends(get_db),
):
    rows, total = await triage_service.list_pool(db, user, urgency=urgency, page=page, size=size)
    return ok(await _serialize_page(db, rows, total, page, size))


@router.get("/counts")
async def counts(user=Depends(workbench), db=Depends(get_db)):
    return ok(await triage_service.counts(db, user))


@router.get("/mine")
async def mine(
    status: str | None = None,
    page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
    user=Depends(workbench), db=Depends(get_db),
):
    rows, total = await triage_service.list_mine(db, user, status=status, page=page, size=size)
    return ok(await _serialize_page(db, rows, total, page, size))


@router.get("/demands")
async def demands(
    status: str | None = None, urgency: str | None = None, type_code: str | None = None,
    page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
    user=Depends(workbench), db=Depends(get_db),
):
    """管理视角需求列表（12 态过滤）：ADMIN 全量，HANDLER 仅流转态。"""
    rows, total = await triage_service.list_all(
        db, user, status=status, urgency=urgency, type_code=type_code, page=page, size=size)
    return ok(await _serialize_page(db, rows, total, page, size))


@router.post("/{demand_id}/accept")
async def accept(demand_id: int, payload: CommentBody | None = None,
                 user=Depends(manager_only), db=Depends(get_db)):
    async with db.begin():
        demand = await triage_service.accept(db, user, demand_id, payload.comment if payload else None)
        result = await demand_service.serialize_with_logs(db, demand)
    return ok(result)


@router.post("/{demand_id}/return")
async def return_for_info(demand_id: int, payload: ReturnBody,
                          user=Depends(manager_only), db=Depends(get_db)):
    """受理打回：与 P0 /admin/demand/{id}/return 同一链路（SUBMITTED → NEED_INFO，原因必填）。"""
    async with db.begin():
        demand = await demand_service.return_demand(db, user, demand_id, payload.reason)
        result = await demand_service.serialize_with_logs(db, demand)
    return ok(result)


@router.post("/{demand_id}/close")
async def close(demand_id: int, payload: CloseBody,
                user=Depends(manager_only), db=Depends(get_db)):
    async with db.begin():
        demand = await triage_service.close(db, user, demand_id, payload.reason, payload.duplicate_of_id)
        result = await demand_service.serialize_with_logs(db, demand)
    return ok(result)


@router.post("/{demand_id}/assign")
async def assign(demand_id: int, payload: AssignBody,
                 user=Depends(manager_only), db=Depends(get_db)):
    async with db.begin():
        demand = await triage_service.assign(db, user, demand_id, payload.assignee_id, payload.comment)
        result = await demand_service.serialize_with_logs(db, demand)
    return ok(result)


@router.post("/{demand_id}/claim")
async def claim(demand_id: int, user=Depends(require_role("HANDLER")), db=Depends(get_db)):
    async with db.begin():
        demand = await triage_service.claim(db, user, demand_id)
        result = await demand_service.serialize_with_logs(db, demand)
    return ok(result)


@router.post("/{demand_id}/return-pool")
async def return_to_pool(demand_id: int, payload: ReturnBody,
                         user=Depends(require_role("HANDLER", "MANAGER")), db=Depends(get_db)):
    """退回处理池：处理人退单或经理/管理员收回（ANALYZING → TRIAGE，清处理人）。"""
    async with db.begin():
        demand = await return_pool(db, user, demand_id, payload.reason)
        result = await demand_service.serialize_with_logs(db, demand)
    return ok(result)


@router.post("/{demand_id}/change-type")
async def change_type(demand_id: int, payload: ChangeTypeBody,
                      user=Depends(require_role("EXECUTIVE")), db=Depends(get_db)):
    async with db.begin():
        demand = await triage_service.change_type(db, user, demand_id, payload.new_type_code, payload.comment)
        result = await demand_service.serialize_with_logs(db, demand)
    return ok(result)


# 供分派弹窗选择处理人（ACTIVE 且有效角色含 HANDLER/ADMIN 的用户）
# 类型权限（2026-10-16 拍板）：typeCode 必传，只出「ADMIN 或类型范围覆盖该需求」的处理人
@router.get("/assignees")
async def assignees(typeCode: str = Query(...), user=Depends(manager_only), db=Depends(get_db)):
    from sqlalchemy import select

    from app.db.models import User
    from app.services import role_service

    rows = (await db.execute(
        select(User).where(User.status == "ACTIVE", User.role.in_(["HANDLER", "ADMIN"]))
        .order_by(User.id)
    )).scalars().all()
    candidates = [
        u for u in rows
        if role_service.user_type_codes(u) is None or typeCode in role_service.parse_type_scope(u.type_scope)
    ]
    return ok([{"id": u.id, "name": u.name, "role": u.role, "department": u.dept_name}
               for u in candidates])
