"""业务字典接口：管理端 CRUD（仅 ADMIN，蓝本 SysDictAdminController）+ 登录用户查 ACTIVE 项。"""

from fastapi import APIRouter, Depends
from pydantic import Field

from app.core.deps import get_db, require_admin
from app.core.result import ApiModel, ok
from app.services import dict_service as service

router = APIRouter(prefix="/admin/dicts", dependencies=[Depends(require_admin)])
# 登录用户查询（提报表单等下拉用），无角色要求
query_router = APIRouter(prefix="/dicts")


class DictSave(ApiModel):
    dict_type: str = Field(min_length=1, max_length=64)
    item_code: str = Field(min_length=1, max_length=64)
    item_name: str = Field(min_length=1, max_length=128)
    sort: int = 0


class DictUpdate(ApiModel):
    item_name: str | None = Field(default=None, min_length=1, max_length=128)
    sort: int | None = None
    status: str | None = None


@router.get("")
async def list_all(dictType: str | None = None, db=Depends(get_db)):
    return ok(await service.list_dicts(db, dict_type=dictType))


@router.get("/types")
async def list_types(db=Depends(get_db)):
    return ok(await service.list_types(db))


@router.post("")
async def create(payload: DictSave, db=Depends(get_db)):
    async with db.begin():
        row = await service.create_dict(
            db, dict_type=payload.dict_type, item_code=payload.item_code,
            item_name=payload.item_name, sort=payload.sort)
    return ok(service.serialize_dict(row))


@router.put("/{dict_id}")
async def update(dict_id: int, payload: DictUpdate, db=Depends(get_db)):
    async with db.begin():
        row = await service.update_dict(
            db, dict_id, item_name=payload.item_name, sort=payload.sort, status=payload.status)
    return ok(service.serialize_dict(row))


@query_router.get("")
async def list_active(dictType: str, db=Depends(get_db)):
    return ok(await service.list_active(db, dict_type=dictType))
