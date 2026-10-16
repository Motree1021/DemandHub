"""渠道白名单服务（2026-10-16 方案定稿）。

口径：
- 白名单管「允许谁进」，与 dh_user 用户档案相互独立；登录拦截在 upsert 自动建档之前
- 全局开关挂渠道行：关闭/渠道行缺失 = 全放行（兼容现状）；开启后仅 ENABLED 条目放行
- dev-login / test-login 不纳入校验（本地与契约测试工具；test-login 本就只放行已存在用户）
- 移除为硬删（留痕表保全历史），不删用户档案；全部管理操作落 demand_channel_whitelist_log
"""

import re

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BizError, ErrorCode
from app.db.models import (
    Demand,
    DemandChannel,
    DemandChannelWhitelist,
    DemandChannelWhitelistLog,
    User,
)

ENABLED = "ENABLED"
DISABLED = "DISABLED"
STATUSES = (ENABLED, DISABLED)

# 留痕动作
ADD = "ADD"
ENABLE = "ENABLE"
DISABLE = "DISABLE"
REMOVE = "REMOVE"
SWITCH_ON = "SWITCH_ON"
SWITCH_OFF = "SWITCH_OFF"
UPDATE_CONTACT = "UPDATE_CONTACT"

USER_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
BATCH_LIMIT = 200
PENDING_LIMIT = 200


def serialize_entry(row: DemandChannelWhitelist, last_login_at=None) -> dict:
    return {
        "id": row.id,
        "channelCode": row.channel_code,
        "channelUserId": row.channel_user_id,
        "displayName": row.display_name,
        "status": row.status,
        "lastLoginAt": last_login_at.isoformat(sep=" ", timespec="seconds") if last_login_at else None,
        "createdByName": row.created_by_name,
        "createdAt": row.created_at.isoformat(sep=" ", timespec="seconds") if row.created_at else None,
        "updatedAt": row.updated_at.isoformat(sep=" ", timespec="seconds") if row.updated_at else None,
    }


def serialize_log(row: DemandChannelWhitelistLog) -> dict:
    return {
        "id": row.id,
        "action": row.action,
        "channelCode": row.channel_code,
        "channelUserId": row.channel_user_id,
        "operatorName": row.operator_name,
        "detail": row.detail,
        "createdAt": row.created_at.isoformat(sep=" ", timespec="seconds") if row.created_at else None,
    }


def _log(db: AsyncSession, channel_code: str, action: str, operator: User, *,
         channel_user_id: str | None = None, detail: str | None = None) -> None:
    db.add(DemandChannelWhitelistLog(
        action=action, channel_code=channel_code, channel_user_id=channel_user_id,
        operator_id=operator.id, operator_name=operator.name,
        detail=detail[:512] if detail else None))


async def get_channel_or_404(db: AsyncSession, channel_code: str) -> DemandChannel:
    channel = (await db.execute(select(DemandChannel).where(
        DemandChannel.channel_code == channel_code))).scalar_one_or_none()
    if channel is None:
        raise BizError(ErrorCode.NOT_FOUND, "渠道不存在")
    return channel


# ---------- 登录链路 ----------

async def assert_allowed(db: AsyncSession, channel_code: str, channel_user_id: str) -> None:
    """渠道登录拦截（channel-sso / channel-parameters 共用）：开关关闭=放行；开启仅 ENABLED 放行。"""
    channel = (await db.execute(select(DemandChannel).where(
        DemandChannel.channel_code == channel_code))).scalar_one_or_none()
    if channel is None or not channel.whitelist_enabled:
        return
    hit = (await db.execute(select(DemandChannelWhitelist.id).where(
        DemandChannelWhitelist.channel_code == channel_code,
        DemandChannelWhitelist.channel_user_id == channel_user_id,
        DemandChannelWhitelist.status == ENABLED))).scalar_one_or_none()
    if hit is None:
        raise BizError(ErrorCode.CHANNEL_NOT_WHITELISTED)


async def get_contact(db: AsyncSession, channel_code: str) -> str | None:
    """拦截页联系引导（公开接口用，被拦用户无登录态）；渠道行缺失返回 None。"""
    return (await db.execute(select(DemandChannel.whitelist_contact).where(
        DemandChannel.channel_code == channel_code))).scalar_one_or_none()


# ---------- 白名单列表 ----------

async def list_entries(db: AsyncSession, channel_code: str, *, page: int, size: int,
                       keyword: str | None, status: str | None) -> dict:
    filters = [DemandChannelWhitelist.channel_code == channel_code]
    if keyword:
        like = f"%{keyword.strip()}%"
        filters.append(or_(DemandChannelWhitelist.channel_user_id.like(like),
                           DemandChannelWhitelist.display_name.like(like)))
    if status:
        filters.append(DemandChannelWhitelist.status == status)
    total = (await db.execute(select(func.count()).select_from(
        select(DemandChannelWhitelist.id).where(*filters).subquery()))).scalar_one()
    stmt = (select(DemandChannelWhitelist, User.last_login_at)
            .outerjoin(User, (User.wecom_userid == DemandChannelWhitelist.channel_user_id)
                       & (User.channel == channel_code))
            .where(*filters)
            .order_by(DemandChannelWhitelist.id.desc())
            .offset((page - 1) * size).limit(size))
    rows = (await db.execute(stmt)).all()
    stats = await _stats(db, channel_code)
    return {"list": [serialize_entry(row, last_login) for row, last_login in rows],
            "total": total, "page": page, "size": size, "stats": stats}


async def _stats(db: AsyncSession, channel_code: str) -> dict:
    rows = (await db.execute(select(DemandChannelWhitelist.status, func.count())
                             .where(DemandChannelWhitelist.channel_code == channel_code)
                             .group_by(DemandChannelWhitelist.status))).all()
    counts = dict(rows)
    return {"enabled": counts.get(ENABLED, 0), "disabled": counts.get(DISABLED, 0)}


# ---------- 添加（单条 / 批量） ----------

async def add_entry(db: AsyncSession, channel_code: str, *, channel_user_id: str,
                    display_name: str | None, operator: User) -> DemandChannelWhitelist:
    await get_channel_or_404(db, channel_code)
    if not USER_ID_PATTERN.match(channel_user_id):
        raise BizError(ErrorCode.PARAM_INVALID, "企微ID 仅允许字母/数字/._-，不超过64字符")
    exists = (await db.execute(select(DemandChannelWhitelist.id).where(
        DemandChannelWhitelist.channel_code == channel_code,
        DemandChannelWhitelist.channel_user_id == channel_user_id))).scalar_one_or_none()
    if exists is not None:
        raise BizError(ErrorCode.WHITELIST_ENTRY_DUPLICATED)
    row = DemandChannelWhitelist(channel_code=channel_code, channel_user_id=channel_user_id,
                                 display_name=display_name, status=ENABLED,
                                 created_by=operator.id, created_by_name=operator.name)
    db.add(row)
    await db.flush()
    _log(db, channel_code, ADD, operator, channel_user_id=channel_user_id,
         detail=display_name or "姓名未填")
    return row


async def add_batch(db: AsyncSession, channel_code: str, *, entries: list[dict],
                    operator: User) -> dict:
    """批量添加：服务层对每条重复执行格式/重复校验（前端解析仅为体验，此处为兜底）。"""
    await get_channel_or_404(db, channel_code)
    if len(entries) > BATCH_LIMIT:
        raise BizError(ErrorCode.PARAM_INVALID, f"单次批量添加不超过 {BATCH_LIMIT} 条")
    existing = set((await db.execute(select(DemandChannelWhitelist.channel_user_id).where(
        DemandChannelWhitelist.channel_code == channel_code))).scalars().all())
    existing_lower = {v.lower() for v in existing}
    seen: set[str] = set()
    added: list[str] = []
    duplicated: list[str] = []
    invalid: list[str] = []
    for entry in entries:
        user_id = entry["channel_user_id"]
        name = entry.get("display_name")
        if not USER_ID_PATTERN.match(user_id):
            invalid.append(user_id)
            continue
        key = user_id.lower()
        if key in seen or key in existing_lower:
            duplicated.append(user_id)
            continue
        seen.add(key)
        db.add(DemandChannelWhitelist(channel_code=channel_code, channel_user_id=user_id,
                                      display_name=name, status=ENABLED,
                                      created_by=operator.id, created_by_name=operator.name))
        _log(db, channel_code, ADD, operator, channel_user_id=user_id,
             detail=f"批量添加：{name}" if name else "批量添加")
        added.append(user_id)
    await db.flush()
    return {"added": len(added), "addedIds": added, "duplicated": duplicated, "invalid": invalid}


# ---------- 启停 / 移除 ----------

async def get_entry_or_404(db: AsyncSession, entry_id: int) -> DemandChannelWhitelist:
    row = (await db.execute(select(DemandChannelWhitelist).where(
        DemandChannelWhitelist.id == entry_id).with_for_update())).scalar_one_or_none()
    if row is None:
        raise BizError(ErrorCode.WHITELIST_ENTRY_NOT_FOUND)
    return row


async def update_entry_status(db: AsyncSession, entry_id: int, *, status: str,
                              operator: User) -> DemandChannelWhitelist:
    if status not in STATUSES:
        raise BizError(ErrorCode.PARAM_INVALID, f"状态仅允许 {'/'.join(STATUSES)}")
    row = await get_entry_or_404(db, entry_id)
    if row.status == status:
        raise BizError(ErrorCode.PARAM_INVALID, "状态未变化")
    row.status = status
    await db.flush()
    _log(db, row.channel_code, ENABLE if status == ENABLED else DISABLE, operator,
         channel_user_id=row.channel_user_id, detail=row.display_name)
    return row


async def remove_entry(db: AsyncSession, entry_id: int, *, operator: User) -> None:
    row = await get_entry_or_404(db, entry_id)
    _log(db, row.channel_code, REMOVE, operator, channel_user_id=row.channel_user_id,
         detail=f"移除：{row.channel_user_id}（{row.display_name or '—'}）")
    await db.delete(row)
    await db.flush()


# ---------- 全局开关 / 联系引导 ----------

async def update_config(db: AsyncSession, channel_code: str, *, enabled: bool | None,
                        contact: str | None, operator: User) -> DemandChannel:
    channel = (await db.execute(select(DemandChannel).where(
        DemandChannel.channel_code == channel_code).with_for_update())).scalar_one_or_none()
    if channel is None:
        raise BizError(ErrorCode.NOT_FOUND, "渠道不存在")
    if enabled is not None and bool(channel.whitelist_enabled) != enabled:
        channel.whitelist_enabled = 1 if enabled else 0
        _log(db, channel_code, SWITCH_ON if enabled else SWITCH_OFF, operator,
             detail=f"{'关闭 → 开启' if enabled else '开启 → 关闭'}")
    if contact is not None:
        contact = contact.strip() or None
        if contact != channel.whitelist_contact:
            channel.whitelist_contact = contact
            _log(db, channel_code, UPDATE_CONTACT, operator,
                 detail=f"更新为「{contact}」" if contact else "清空联系引导")
    await db.flush()
    return channel


# ---------- 待登记渠道用户 / 留痕 ----------

async def list_pending(db: AsyncSession, channel_code: str) -> list[dict]:
    """已有系统档案但未入白名单的渠道用户（补登记辅助；已禁用用户本就被拦，不列入）。"""
    registered = select(DemandChannelWhitelist.channel_user_id).where(
        DemandChannelWhitelist.channel_code == channel_code)
    stmt = (select(User, func.count(Demand.id).label("demand_count"))
            .outerjoin(Demand, Demand.submitter_id == User.id)
            .where(User.channel == channel_code, User.status == "ACTIVE",
                   User.wecom_userid.not_in(registered))
            .group_by(User.id)
            .order_by(User.last_login_at.is_(None), User.last_login_at.desc())
            .limit(PENDING_LIMIT))
    rows = (await db.execute(stmt)).all()
    return [{"userId": user.id, "wecomUserid": user.wecom_userid, "name": user.name,
             "deptName": user.dept_name,
             "lastLoginAt": user.last_login_at.isoformat(sep=" ", timespec="seconds")
             if user.last_login_at else None,
             "demandCount": count} for user, count in rows]


async def list_logs(db: AsyncSession, channel_code: str, *, page: int, size: int) -> dict:
    filters = [DemandChannelWhitelistLog.channel_code == channel_code]
    total = (await db.execute(select(func.count()).select_from(
        select(DemandChannelWhitelistLog.id).where(*filters).subquery()))).scalar_one()
    rows = (await db.execute(select(DemandChannelWhitelistLog).where(*filters)
                             .order_by(DemandChannelWhitelistLog.id.desc())
                             .offset((page - 1) * size).limit(size))).scalars().all()
    return {"list": [serialize_log(row) for row in rows], "total": total, "page": page, "size": size}
