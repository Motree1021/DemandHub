"""状态机配置服务（蓝本 StateMachineConfigService）：配置 CRUD + 整包 JSON 覆盖 + 保存即热刷。

口径：config_key 唯一不可改；保存时聚合校验（validate_rules）一次性报全量错误；
保存成功后立即 load_from_db 热刷新（不重启即生效，另有 30s 定时兜底与手动 /reload）；
不校验 key 是否被 demand_type 引用（蓝本口径）。"""

import json

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BizError, ErrorCode
from app.core.statemachine import engine
from app.db.models import StateMachineConfig

ACTIVE = "ACTIVE"
DISABLED = "DISABLED"
STATUSES = (ACTIVE, DISABLED)


def serialize_config(row: StateMachineConfig) -> dict:
    return {
        "id": row.id,
        "configKey": row.config_key,
        "configName": row.config_name,
        "configJson": row.config_json,
        "version": row.version,
        "status": row.status,
        "remark": row.remark,
        "createdAt": row.created_at.isoformat(sep=" ", timespec="seconds") if row.created_at else None,
        "updatedAt": row.updated_at.isoformat(sep=" ", timespec="seconds") if row.updated_at else None,
    }


async def list_configs(db: AsyncSession) -> list[dict]:
    rows = (await db.execute(
        select(StateMachineConfig).order_by(StateMachineConfig.id))).scalars().all()
    return [serialize_config(row) for row in rows]


def default_json() -> str:
    """内置兜底规则（DEFAULT_RULES）序列化为 pretty JSON（蓝本 /default-json 口径）。"""
    rules = [
        {"from": rule.from_status, "event": rule.event, "to": rule.to,
         "roles": sorted(rule.roles), "remark": rule.remark}
        for rule in engine.DEFAULT_RULES
    ]
    return json.dumps({"rules": rules}, ensure_ascii=False, indent=2)


def _validate(config_json: str) -> None:
    errors = engine.validate_rules(config_json)
    if errors:
        raise BizError(ErrorCode.PARAM_INVALID, "；".join(errors))


async def create_config(db: AsyncSession, *, config_key: str, config_name: str,
                        config_json: str, remark: str | None = None) -> StateMachineConfig:
    _validate(config_json)
    exists = (await db.execute(
        select(func.count(StateMachineConfig.id)).where(
            StateMachineConfig.config_key == config_key))).scalar_one()
    if exists:
        raise BizError(ErrorCode.CONFLICT, f"状态机配置 key 已存在: {config_key}")
    row = StateMachineConfig(config_key=config_key, config_name=config_name,
                             config_json=config_json, status=ACTIVE, remark=remark)
    db.add(row)
    await db.flush()
    await engine.load_from_db(db)  # 保存即热刷（不重启生效）
    return row


async def update_config(db: AsyncSession, config_id: int, *, config_name: str | None = None,
                        config_json: str | None = None, status: str | None = None,
                        remark: str | None = None) -> StateMachineConfig:
    """config_key 不可改；config_json 变更时 version+1；保存即热刷。"""
    row = (await db.execute(
        select(StateMachineConfig).where(StateMachineConfig.id == config_id))).scalar_one_or_none()
    if row is None:
        raise BizError(ErrorCode.NOT_FOUND, "状态机配置不存在")
    if status is not None and status not in STATUSES:
        raise BizError(ErrorCode.PARAM_INVALID, f"状态仅允许 {'/'.join(STATUSES)}")
    if config_json is not None:
        _validate(config_json)
    if config_name is not None:
        row.config_name = config_name
    if config_json is not None and config_json != row.config_json:
        row.config_json = config_json
        row.version += 1
    if status is not None:
        row.status = status
    if remark is not None:
        row.remark = remark
    await db.flush()
    await engine.load_from_db(db)  # 保存即热刷
    return row
