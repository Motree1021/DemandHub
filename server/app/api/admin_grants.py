"""P4 业务角色授权管理（仅 ADMIN）：demand_role_grant 分页/新增/修改/回收。

有效角色 = 静态 role ∪ 生效授权（role_service.effective_roles），
状态机与角色守卫逐请求读库，授权变更即时生效（无需会话失效）。
"""
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import Field

from app.core.deps import get_db, require_admin
from app.core.result import ApiModel, ok
from app.services import role_service

router = APIRouter(prefix="/admin/grants", dependencies=[Depends(require_admin)])

RoleCode = Literal["ADMIN", "EXECUTIVE", "MANAGER", "HANDLER"]


class GrantSave(ApiModel):
    user_id: int
    role_code: RoleCode
    org_id: int | None = None
    demand_type_scope: str | None = Field(default=None, max_length=256)
    effective_from: datetime | None = None
    effective_to: datetime | None = None


@router.get("")
async def page(user_id: int | None = Query(None, alias="userId"),
               role_code: RoleCode | None = Query(None, alias="roleCode"),
               page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
               db=Depends(get_db)):
    rows, total = await role_service.page_grants(
        db, user_id=user_id, role_code=role_code, page=page, size=size)
    return ok({"list": [role_service.serialize_grant(g) for g in rows],
               "total": total, "page": page, "size": size})


@router.post("")
async def create(payload: GrantSave, admin=Depends(require_admin), db=Depends(get_db)):
    async with db.begin():
        grant = await role_service.create_grant(
            db, user_id=payload.user_id, role_code=payload.role_code, org_id=payload.org_id,
            demand_type_scope=payload.demand_type_scope, effective_from=payload.effective_from,
            effective_to=payload.effective_to, granted_by=admin.id)
    return ok(role_service.serialize_grant(grant))


@router.put("/{grant_id}")
async def update(grant_id: int, payload: GrantSave, db=Depends(get_db)):
    async with db.begin():
        grant = await role_service.update_grant(
            db, grant_id, user_id=payload.user_id, role_code=payload.role_code,
            org_id=payload.org_id, demand_type_scope=payload.demand_type_scope,
            effective_from=payload.effective_from, effective_to=payload.effective_to)
    return ok(role_service.serialize_grant(grant))


@router.delete("/{grant_id}")
async def delete(grant_id: int, db=Depends(get_db)):
    async with db.begin():
        await role_service.delete_grant(db, grant_id)
    return ok({"success": True})
