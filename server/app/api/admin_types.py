"""需求类型管理接口（仅 ADMIN，蓝本 DemandTypeAdminController）：列表/新增/修改。

五区字段标准仍走 yaml 快照，本模块只管类型注册/启停/状态机绑定/排序。"""

from fastapi import APIRouter, Depends
from pydantic import Field

from app.core.deps import get_db, require_admin
from app.core.result import ApiModel, ok
from app.services import type_service as service

router = APIRouter(prefix="/admin/types", dependencies=[Depends(require_admin)])


class TypeSave(ApiModel):
    type_code: str = Field(min_length=1, max_length=32)
    type_name: str = Field(min_length=1, max_length=64)
    default_org_id: int | None = None
    state_machine_key: str = Field(default="DEFAULT", max_length=64)
    sort: int = 0


class TypeUpdate(ApiModel):
    type_name: str | None = Field(default=None, min_length=1, max_length=64)
    default_org_id: int | None = None
    state_machine_key: str | None = Field(default=None, max_length=64)
    sort: int | None = None
    status: str | None = None


@router.get("")
async def list_all(db=Depends(get_db)):
    return ok(await service.list_types(db))


@router.post("")
async def create(payload: TypeSave, db=Depends(get_db)):
    async with db.begin():
        row = await service.create_type(
            db, type_code=payload.type_code, type_name=payload.type_name,
            default_org_id=payload.default_org_id, state_machine_key=payload.state_machine_key,
            sort=payload.sort)
    return ok(service.serialize_type(row))


@router.put("/{type_id}")
async def update(type_id: int, payload: TypeUpdate, db=Depends(get_db)):
    async with db.begin():
        row = await service.update_type(
            db, type_id, type_name=payload.type_name, default_org_id=payload.default_org_id,
            state_machine_key=payload.state_machine_key, sort=payload.sort, status=payload.status)
    return ok(service.serialize_type(row))
