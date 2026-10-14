"""组织管理接口（仅 ADMIN，蓝本 OrgAdminController）：树/平铺查询 + 新增/修改/删除。

移动 = 修改时换 parentId（整棵子树路径自动前缀替换）；删除做五项引用校验。"""

from fastapi import APIRouter, Depends
from pydantic import Field

from app.core.deps import get_db, require_admin
from app.core.result import ApiModel, ok
from app.services import org_service as service

router = APIRouter(prefix="/admin/orgs", dependencies=[Depends(require_admin)])


class OrgSave(ApiModel):
    name: str = Field(min_length=1, max_length=128)
    level: str = Field(min_length=1, max_length=16)
    parent_id: int = Field(gt=0)
    org_kind: str = Field(min_length=1, max_length=16)
    external_dept_id: str | None = Field(default=None, max_length=32)


class OrgUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    level: str | None = Field(default=None, min_length=1, max_length=16)
    parent_id: int | None = Field(default=None, gt=0)
    org_kind: str | None = Field(default=None, min_length=1, max_length=16)
    external_dept_id: str | None = Field(default=None, max_length=32)
    status: str | None = None


@router.get("")
async def list_all(db=Depends(get_db)):
    """平铺列表（类型管理等下拉用）。"""
    return ok(await service.list_orgs(db))


@router.get("/tree")
async def tree(db=Depends(get_db)):
    return ok(await service.tree(db))


@router.post("")
async def create(payload: OrgSave, db=Depends(get_db)):
    async with db.begin():
        row = await service.create_org(
            db, name=payload.name, level=payload.level, parent_id=payload.parent_id,
            org_kind=payload.org_kind, external_dept_id=payload.external_dept_id)
    return ok(service.serialize_org(row))


@router.put("/{org_id}")
async def update(org_id: int, payload: OrgUpdate, db=Depends(get_db)):
    async with db.begin():
        row = await service.update_org(
            db, org_id, name=payload.name, level=payload.level, parent_id=payload.parent_id,
            org_kind=payload.org_kind, external_dept_id=payload.external_dept_id,
            status=payload.status)
    return ok(service.serialize_org(row))


@router.delete("/{org_id}")
async def remove(org_id: int, db=Depends(get_db)):
    async with db.begin():
        await service.delete_org(db, org_id)
    return ok(None)
