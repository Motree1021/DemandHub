from fastapi import APIRouter, Depends

from app.core.deps import get_current_user, get_db
from app.core.result import ok
from app.services import type_service
from app.standards import loader

router = APIRouter(prefix="/standards", tags=["standards"])


@router.get("")
async def list_standards(user=Depends(get_current_user), db=Depends(get_db)):
    """类型下拉数据源（P5 决策③：表管注册、yaml 管内容）。
    demand_type 表 ACTIVE 类型为主（name 用表注册名），yaml 仅补 version；
    表为空（测试库无种子）时回落 yaml 扫描，保持提报链路兼容。"""
    standards = loader.load_all()
    types = await type_service.list_active(db)
    if not types:
        return ok([{"code": std.type, "type": std.type, "name": std.name, "version": std.version}
                   for std in standards.values()])
    return ok([{"code": row.type_code, "type": row.type_code, "name": row.type_name,
                "version": standards[row.type_code].version if row.type_code in standards else None}
               for row in types])


@router.get("/{type_code}")
async def get_standard(type_code: str, user=Depends(get_current_user)):
    return ok(loader.get(type_code).model_dump(mode="json", by_alias=True))
