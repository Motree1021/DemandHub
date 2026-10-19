"""OneID 一期：渠道身份的查询、管理员挂接（归并）与改挂。

口径（2026-10-17 定稿，用户确认）：
- 挂接（LINK）：把未归属渠道身份挂到 PC 用户（channel='ACCOUNT' 的 OneID 用户）名下——
  身份改指 PC 用户 + 临时人业务数据全量过户 + 临时人角色授权作废 + 票据吊销 + 停用 + 审计。
  此后渠道免登进入的即该 PC 用户，历史数据天然归一。
- 改挂（REBIND）：已归属身份从 PC 用户 A 移到 PC 用户 B——只移钥匙不搬历史数据
  （首次挂接数据已过户给 A，无法再区分；前端弹窗明确警示）。
- 角色/类型权限以 PC 用户为准，临时人角色配置作废。
- 并发保护：挂接/改挂前校验当前归属人，与预期不符即报 1128。
"""
import json

from sqlalchemy import delete, func, select

from app.core.errors import BizError, ErrorCode
from app.db.models import (
    AgentDraft,
    AgentSession,
    Assignment,
    ChannelIdentity,
    Comment,
    Demand,
    DemandAttachment,
    DemandChangeLog,
    DemandRoleGrant,
    DemandTransitionLog,
    EffortLog,
    IdentityLinkLog,
    Notification,
    NotificationPreference,
    RefreshToken,
    ReportExportTask,
    Review,
    Solution,
    User,
)

# 过户清单（UPDATE 指向 dh_user.id 的业务外键；快照姓名列保留历史不动）：
# (模型, 外键列, 展示名)——展示名进审计 moved_counts，供管理员确认与事后核对
_TRANSFER_RULES = [
    (Demand, "submitter_id", "提报需求"),
    (Demand, "assignee_id", "处理需求"),
    (DemandChangeLog, "changed_by", "要素变更"),
    (DemandAttachment, "uploaded_by", "附件"),
    (AgentSession, "user_id", "智能体会话"),
    (AgentDraft, "created_by", "智能体草稿"),
    (DemandTransitionLog, "operator_id", "流转记录"),
    (Assignment, "operator_id", "分派记录"),
    (Solution, "author_id", "方案"),
    (Review, "reviewer_id", "评审"),
    (Comment, "author_id", "评论"),
    (EffortLog, "user_id", "工时"),
    (Notification, "receiver_id", "通知"),
    (ReportExportTask, "requester_id", "导出任务"),
    (DemandRoleGrant, "granted_by", "授权操作记录"),
]


def _is_pc_user(user: User) -> bool:
    """PC 端用户（账密建档）= OneID 用户；渠道自动建档的为临时人。"""
    return user.channel == "ACCOUNT"


async def _find_suspects(db, names: list[str]) -> dict[str, list[dict]]:
    """挂接防错的同名线索（2026-10-18 二期拍板）：仅「姓名完全一致」且仅正式用户
    （PC 端 ACTIVE）——宁缺毋滥，不引入相似度算法，也不把渠道临时人当疑似。
    返回 {渠道姓名: [候选, 至多3个]}；同名≠同一人，仅供管理员核对参考。"""
    if not names:
        return {}
    rows = (await db.execute(select(User).where(
        User.channel == "ACCOUNT", User.status == "ACTIVE", User.name.in_(names))
        .order_by(User.id))).scalars().all()
    grouped: dict[str, list[dict]] = {}
    for u in rows:
        candidates = grouped.setdefault(u.name, [])
        if len(candidates) < 3:
            candidates.append({"id": u.id, "name": u.name, "loginAccount": u.login_account})
    return grouped


async def list_identities(db, linked: bool, keyword: str | None, page: int, size: int):
    """渠道身份全量列表（独立「渠道身份」页数据源）。

    linked=False 待归一：归属人仍是渠道临时人，按最近活跃倒序（管理员从待办出发挂接），
        每行附 suspects 同名 PC 用户线索（挂接防错，仅供核对）；
    linked=True  已归一：归属人是 PC 用户（OneID 用户），按挂接/改挂时间倒序。
    identity.updated_at 在每次渠道免登时刷新（姓名快照始终更新），即最近活跃时间。
    """
    stmt = (select(ChannelIdentity, User)
            .join(User, ChannelIdentity.user_id == User.id)
            .where((User.channel == "ACCOUNT") if linked else (User.channel != "ACCOUNT"))
            .order_by(ChannelIdentity.updated_at.desc()))
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(ChannelIdentity.channel_user_id.like(like)
                          | ChannelIdentity.channel_user_name.like(like)
                          | User.name.like(like)
                          | User.login_account.like(like))
    rows = (await db.execute(stmt)).all()
    total = len(rows)
    page_rows = rows[(page - 1) * size: page * size]
    suspect_map = {} if linked else await _find_suspects(
        db, [identity.channel_user_name for identity, _ in page_rows])
    items = [{"id": identity.id, "channel": identity.channel,
              "channelUserId": identity.channel_user_id,
              "channelUserName": identity.channel_user_name,
              "ownerId": owner.id, "ownerName": owner.name,
              "ownerAccount": owner.login_account,
              "lastSeenAt": identity.updated_at.isoformat() if identity.updated_at else None,
              **({"suspects": suspect_map.get(identity.channel_user_name, [])} if not linked else {})}
             for identity, owner in page_rows]
    return items, total


async def list_link_logs(db, page: int, size: int):
    """挂接/改挂审计分页列表（「挂接记录」Tab 数据源；行只增不改，按时间倒序）。"""
    total = (await db.execute(select(func.count()).select_from(IdentityLinkLog))).scalar_one()
    logs = (await db.execute(select(IdentityLinkLog)
                             .order_by(IdentityLinkLog.id.desc())
                             .offset((page - 1) * size).limit(size))).scalars().all()
    items = [{"id": log.id, "action": log.action, "channel": log.channel,
              "channelUserId": log.channel_user_id,
              "fromUserId": log.from_user_id, "fromUserName": log.from_user_name,
              "toUserId": log.to_user_id, "toUserName": log.to_user_name,
              "movedCounts": json.loads(log.moved_counts) if log.moved_counts else None,
              "operatorName": log.operator_name,
              "createdAt": log.created_at.isoformat() if log.created_at else None}
             for log in logs]
    return items, total


async def list_of_user(db, user_id: int):
    """某 PC 用户已挂接的渠道身份。"""
    rows = (await db.execute(select(ChannelIdentity)
                             .where(ChannelIdentity.user_id == user_id)
                             .order_by(ChannelIdentity.created_at))).scalars().all()
    return [{"id": i.id, "channel": i.channel, "channelUserId": i.channel_user_id,
             "channelUserName": i.channel_user_name,
             "createdAt": i.created_at.isoformat() if i.created_at else None} for i in rows]


async def _transfer_data(db, from_id: int, to_id: int) -> dict[str, int]:
    """临时人业务数据全量过户（同事务）；返回各项过户数量（仅非零项，进审计）。"""
    counts: dict[str, int] = {}
    for model, column, label in _TRANSFER_RULES:
        result = await db.execute(
            model.__table__.update()
            .where(getattr(model, column) == from_id)
            .values(**{column: to_id}))
        if result.rowcount:
            counts[label] = result.rowcount
    # 通知偏好：撞 (user_id, notify_type) 唯一键的行以 PC 用户为准，删临时人的；其余过户。
    # 先查后删两步走：MySQL 不允许 DELETE 的 WHERE 子查询直查目标表本身（1093）。
    target_types = (await db.execute(select(NotificationPreference.notify_type)
                                     .where(NotificationPreference.user_id == to_id))).scalars().all()
    if target_types:
        await db.execute(delete(NotificationPreference).where(
            NotificationPreference.user_id == from_id,
            NotificationPreference.notify_type.in_(target_types)))
    pref = await db.execute(NotificationPreference.__table__.update()
                            .where(NotificationPreference.user_id == from_id)
                            .values(user_id=to_id))
    if pref.rowcount:
        counts["通知偏好"] = pref.rowcount
    # 临时人角色授权作废（角色/类型权限以 PC 用户为准）；票据吊销
    await db.execute(delete(DemandRoleGrant).where(DemandRoleGrant.user_id == from_id))
    await db.execute(delete(RefreshToken).where(RefreshToken.user_id == from_id))
    return counts


async def _get_user(db, user_id: int) -> User:
    user = (await db.execute(select(User).where(User.id == user_id)
                             .with_for_update())).scalar_one_or_none()
    if user is None:
        raise BizError(ErrorCode.USER_NOT_FOUND)
    return user


async def link(db, identity_id: int, target_user_id: int, operator: User) -> dict:
    """挂接：未归属渠道身份 → PC 用户（含临时人数据过户与停用）。返回审计出参。"""
    identity = (await db.execute(select(ChannelIdentity)
                                 .where(ChannelIdentity.id == identity_id)
                                 .with_for_update())).scalar_one_or_none()
    if identity is None:
        raise BizError(ErrorCode.IDENTITY_NOT_FOUND)
    target = await _get_user(db, target_user_id)
    if not _is_pc_user(target):
        raise BizError(ErrorCode.PARAM_INVALID, "仅可挂接到 PC 端用户（账密建档的 OneID 用户）")
    if target.status != "ACTIVE":
        raise BizError(ErrorCode.CHANNEL_ACCOUNT_UNAVAILABLE)
    source = await db.get(User, identity.user_id)
    if source is None:
        raise BizError(ErrorCode.USER_NOT_FOUND)
    if _is_pc_user(source):  # 并发保护：已被他人抢先挂接
        raise BizError(ErrorCode.IDENTITY_ALREADY_LINKED)
    counts = await _transfer_data(db, source.id, target.id)
    source.status = "DISABLED"  # 临时人停用（数据已归一，不再可登录）
    identity.user_id = target.id
    db.add(IdentityLinkLog(
        action="LINK", identity_id=identity.id, channel=identity.channel,
        channel_user_id=identity.channel_user_id,
        from_user_id=source.id, from_user_name=source.name,
        to_user_id=target.id, to_user_name=target.name,
        moved_counts=json.dumps(counts, ensure_ascii=False),
        operator_id=operator.id, operator_name=operator.name))
    return {"identityId": identity.id, "channel": identity.channel,
            "channelUserId": identity.channel_user_id,
            "sourceUser": {"id": source.id, "name": source.name},
            "targetUser": {"id": target.id, "name": target.name},
            "movedCounts": counts}


async def rebind(db, identity_id: int, target_user_id: int, operator: User) -> dict:
    """改挂：已归属身份 PC 用户 A → PC 用户 B。只移钥匙，不搬历史数据。"""
    identity = (await db.execute(select(ChannelIdentity)
                                 .where(ChannelIdentity.id == identity_id)
                                 .with_for_update())).scalar_one_or_none()
    if identity is None:
        raise BizError(ErrorCode.IDENTITY_NOT_FOUND)
    target = await _get_user(db, target_user_id)
    if not _is_pc_user(target):
        raise BizError(ErrorCode.PARAM_INVALID, "仅可改挂到 PC 端用户（账密建档的 OneID 用户）")
    if target.status != "ACTIVE":
        raise BizError(ErrorCode.CHANNEL_ACCOUNT_UNAVAILABLE)
    source = await db.get(User, identity.user_id)
    if source is None:
        raise BizError(ErrorCode.USER_NOT_FOUND)
    if not _is_pc_user(source):
        raise BizError(ErrorCode.PARAM_INVALID, "该渠道身份尚未挂接，请使用挂接操作")
    if source.id == target.id:
        raise BizError(ErrorCode.PARAM_INVALID, "该渠道身份已在当前用户名下")
    identity.user_id = target.id  # 只移钥匙：历史数据不搬（已在 A 名下，无法区分）
    db.add(IdentityLinkLog(
        action="REBIND", identity_id=identity.id, channel=identity.channel,
        channel_user_id=identity.channel_user_id,
        from_user_id=source.id, from_user_name=source.name,
        to_user_id=target.id, to_user_name=target.name,
        moved_counts=None, operator_id=operator.id, operator_name=operator.name))
    return {"identityId": identity.id, "channel": identity.channel,
            "channelUserId": identity.channel_user_id,
            "sourceUser": {"id": source.id, "name": source.name},
            "targetUser": {"id": target.id, "name": target.name}}
