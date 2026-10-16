"""渠道管理服务（蓝本 ChannelAdminService，决策②裁剪版：只做登记/启停）。

口径：渠道无新增/删除接口（SQL 种子注册）；config_json 为蓝本预留列，序列化时
secret 类 key 一律脱敏 "***"；部门未映射清单只读 + 校准后删行（记录 upsert 属登录链路，本期不动）。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BizError, ErrorCode
from app.db.models import ChannelDeptUnmapped, DemandChannel

ACTIVE = "ACTIVE"
DISABLED = "DISABLED"
STATUSES = (ACTIVE, DISABLED)


def _mask_config(config: dict | None) -> dict | None:
    """config_json 透传时 secret 类 key 脱敏（蓝本 appSecret 口径）。"""
    if config is None:
        return None
    return {k: ("***" if "secret" in k.lower() else v) for k, v in config.items()}


def serialize_channel(row: DemandChannel) -> dict:
    return {
        "id": row.id,
        "channelCode": row.channel_code,
        "channelName": row.channel_name,
        "appId": row.app_id,
        "callbackEnabled": bool(row.callback_enabled),
        "status": row.status,
        "whitelistEnabled": bool(row.whitelist_enabled),
        "whitelistContact": row.whitelist_contact,
        "configJson": _mask_config(row.config_json),
        "createdAt": row.created_at.isoformat(sep=" ", timespec="seconds") if row.created_at else None,
        "updatedAt": row.updated_at.isoformat(sep=" ", timespec="seconds") if row.updated_at else None,
    }


def serialize_unmapped(row: ChannelDeptUnmapped) -> dict:
    return {
        "id": row.id,
        "channelCode": row.channel_code,
        "deptId": row.dept_id,
        "deptName": row.dept_name,
        "deptPath": row.dept_path,
        "sampleChannelUserId": row.sample_channel_user_id,
        "hitCount": row.hit_count,
        "firstSeenAt": row.first_seen_at.isoformat(sep=" ", timespec="seconds") if row.first_seen_at else None,
        "lastSeenAt": row.last_seen_at.isoformat(sep=" ", timespec="seconds") if row.last_seen_at else None,
    }


async def list_channels(db: AsyncSession) -> list[dict]:
    rows = (await db.execute(
        select(DemandChannel).order_by(DemandChannel.id))).scalars().all()
    return [serialize_channel(row) for row in rows]


async def update_status(db: AsyncSession, channel_id: int, *, status: str) -> DemandChannel:
    row = (await db.execute(
        select(DemandChannel).where(DemandChannel.id == channel_id))).scalar_one_or_none()
    if row is None:
        raise BizError(ErrorCode.NOT_FOUND, "渠道不存在")
    if status not in STATUSES:
        raise BizError(ErrorCode.PARAM_INVALID, f"状态仅允许 {'/'.join(STATUSES)}")
    row.status = status
    await db.flush()
    return row


async def list_unmapped(db: AsyncSession, channel_code: str | None = None) -> list[dict]:
    stmt = select(ChannelDeptUnmapped).order_by(ChannelDeptUnmapped.last_seen_at.desc())
    if channel_code:
        stmt = stmt.where(ChannelDeptUnmapped.channel_code == channel_code)
    rows = (await db.execute(stmt)).scalars().all()
    return [serialize_unmapped(row) for row in rows]


async def delete_unmapped(db: AsyncSession, unmapped_id: int) -> None:
    row = (await db.execute(
        select(ChannelDeptUnmapped).where(ChannelDeptUnmapped.id == unmapped_id))
    ).scalar_one_or_none()
    if row is None:
        raise BizError(ErrorCode.NOT_FOUND, "未映射记录不存在")
    await db.delete(row)
    await db.flush()
