"""OneID：渠道身份挂接管理（仅 ADMIN）。

- GET  /channel-identities?linked=false|true    渠道身份列表（待归一附同名线索 suspects）
- GET  /identity-link-logs                      挂接/改挂审计记录（「挂接记录」Tab）
- GET  /users/{user_id}/channel-identities      某 PC 用户已挂接的渠道身份
- POST /users/{user_id}/channel-identities      挂接（含临时人数据过户/停用/审计）
- POST /channel-identities/{identity_id}/rebind 改挂（只移钥匙不搬数据，前端已警示）
"""
from fastapi import APIRouter, Depends, Query
from pydantic import Field

from app.core.deps import get_db, require_admin
from app.core.result import ApiModel, ok
from app.services import identity_service

router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])


@router.get("/channel-identities")
async def list_identities(linked: bool = Query(False),
                          keyword: str | None = Query(None, max_length=64),
                          page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
                          db=Depends(get_db)):
    items, total = await identity_service.list_identities(db, linked, keyword, page, size)
    return ok({"list": items, "total": total, "page": page, "size": size})


@router.get("/identity-link-logs")
async def list_link_logs(page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
                         db=Depends(get_db)):
    items, total = await identity_service.list_link_logs(db, page, size)
    return ok({"list": items, "total": total, "page": page, "size": size})


@router.get("/users/{user_id}/channel-identities")
async def list_user_identities(user_id: int, db=Depends(get_db)):
    return ok(await identity_service.list_of_user(db, user_id))


class LinkIdentity(ApiModel):
    identity_id: int = Field(alias="identityId", ge=1)


@router.post("/users/{user_id}/channel-identities")
async def link_identity(user_id: int, payload: LinkIdentity,
                        admin=Depends(require_admin), db=Depends(get_db)):
    async with db.begin():
        result = await identity_service.link(db, payload.identity_id, user_id, admin)
    return ok(result)


class RebindIdentity(ApiModel):
    user_id: int = Field(alias="userId", ge=1)


@router.post("/channel-identities/{identity_id}/rebind")
async def rebind_identity(identity_id: int, payload: RebindIdentity,
                          admin=Depends(require_admin), db=Depends(get_db)):
    async with db.begin():
        result = await identity_service.rebind(db, identity_id, payload.user_id, admin)
    return ok(result)
