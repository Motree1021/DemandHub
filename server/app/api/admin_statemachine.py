"""状态机配置管理接口（仅 ADMIN，蓝本 StateMachineConfigAdminController）。

口径：整包 configJson 覆盖式保存（无规则级 CRUD）；保存时聚合校验一次性报全量错误；
保存即热刷（不重启生效）+ 30s 定时兜底 + /reload 手动重载；config_key 唯一不可改。"""

from fastapi import APIRouter, Depends
from pydantic import Field

from app.core.deps import get_db, require_admin
from app.core.result import ApiModel, ok
from app.core.statemachine import engine
from app.services import statemachine_service as service

router = APIRouter(prefix="/admin/state-machines", dependencies=[Depends(require_admin)])


class ConfigSave(ApiModel):
    config_key: str = Field(min_length=1, max_length=64)
    config_name: str = Field(min_length=1, max_length=64)
    config_json: str = Field(min_length=1)
    remark: str | None = Field(default=None, max_length=255)


class ConfigUpdate(ApiModel):
    config_name: str | None = Field(default=None, min_length=1, max_length=64)
    config_json: str | None = Field(default=None, min_length=1)
    status: str | None = None
    remark: str | None = Field(default=None, max_length=255)


@router.get("")
async def list_all(db=Depends(get_db)):
    """配置列表（含 configJson 全文，前端编辑直接取用）。"""
    return ok(await service.list_configs(db))


@router.get("/default-json")
async def default_json():
    """内置兜底规则的 pretty JSON，用于「从默认配置新建」。"""
    return ok({"configJson": service.default_json()})


@router.post("")
async def create(payload: ConfigSave, db=Depends(get_db)):
    async with db.begin():
        row = await service.create_config(
            db, config_key=payload.config_key, config_name=payload.config_name,
            config_json=payload.config_json, remark=payload.remark)
    return ok(service.serialize_config(row))


@router.put("/{config_id}")
async def update(config_id: int, payload: ConfigUpdate, db=Depends(get_db)):
    async with db.begin():
        row = await service.update_config(
            db, config_id, config_name=payload.config_name, config_json=payload.config_json,
            status=payload.status, remark=payload.remark)
    return ok(service.serialize_config(row))


@router.post("/reload")
async def reload(db=Depends(get_db)):
    """手动热重载：从 state_machine_config 表重新加载全部 ACTIVE 规则，不重启生效。"""
    return ok(await engine.load_from_db(db))
