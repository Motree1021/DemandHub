from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError

from app.core.errors import BizError, ErrorCode
from app.db.models import ChannelIdentity, User, now

# MySQL 死锁错误码（InnoDB 检测到死锁后整体回滚牺牲事务）
_DEADLOCK = 1213


async def sso_transaction(db, work):
    """以独立事务执行 SSO 登录工作块；撞死锁整体重试（MySQL 官方建议的死锁处理姿势）。

    并发首登的唯一键裁决 + 当前读重查在多路并发下仍可能互等成死锁（InnoDB 锁图复杂，
    根除代价高）。死锁时 InnoDB 已整体回滚事务，重试在新事务新快照上进行，还能顺带绕开
    REPEATABLE READ 快照读不到并发胜者的问题。块内只允许可重入操作（只读校验 + upsert）。
    """
    for attempt in range(3):
        try:
            async with db.begin():
                return await work()
        except OperationalError as exc:
            code = exc.orig.args[0] if exc.orig is not None and exc.orig.args else None
            if code != _DEADLOCK or attempt == 2:
                raise


async def _find_identity(db, channel: str, channel_user_id: str) -> ChannelIdentity | None:
    # 不加锁：FOR UPDATE 未命中时间隙锁会让并发首登互相等待形成死锁
    return (await db.execute(
        select(ChannelIdentity)
        .where(ChannelIdentity.channel == channel,
               ChannelIdentity.channel_user_id == channel_user_id))).scalar_one_or_none()


async def _create_identity(db, profile, channel: str) -> ChannelIdentity:
    """未命中建档：直接 INSERT 让唯一键裁决，撞键后重查并发胜者。

    不预查 FOR UPDATE（唯一索引未命中间隙锁 + INSERT 插入意向锁互等 = 死锁）；
    SAVEPOINT 保证撞 IntegrityError 只回滚本段、不毁外层事务（死锁 1213 除外，整事务回滚由客户端重试）。
    """
    user = (await db.execute(select(User).where(User.wecom_userid == profile.user_id))
            ).scalar_one_or_none()
    if user is None:
        try:
            async with db.begin_nested():
                user = User(name=profile.name, wecom_userid=profile.user_id, channel=channel,
                            dept_name=profile.dept_name, status="ACTIVE", last_login_at=now())
                db.add(user)
                await db.flush()
        except IntegrityError:
            # 撞键=并发事务已提交该行。须 FOR UPDATE 当前读：REPEATABLE READ 下普通 SELECT
            # 走事务首个快照，看不到对方新提交的行（NoResultFound）；此时行必存在，无间隙锁。
            user = (await db.execute(select(User).where(User.wecom_userid == profile.user_id)
                                     .with_for_update().execution_options(populate_existing=True))
                    ).scalar_one()
    identity = None
    try:
        async with db.begin_nested():
            identity = ChannelIdentity(user_id=user.id, channel=channel,
                                       channel_user_id=profile.user_id,
                                       channel_user_name=profile.name)
            db.add(identity)
            await db.flush()
    except IntegrityError:
        identity = (await db.execute(
            select(ChannelIdentity)
            .where(ChannelIdentity.channel == channel,
                   ChannelIdentity.channel_user_id == profile.user_id)
            .with_for_update().execution_options(populate_existing=True))).scalar_one()
    return identity


async def upsert_from_sso(db, profile, channel="CHUANGJIN_LS") -> User:
    """渠道 SSO 建档/取人（OneID 一期：走渠道身份表，dh_user.wecom_userid 仅作对照）。

    - 命中渠道身份 → 取归属人（被管理员挂接过即 PC 用户，OneID 生效）。
      渠道姓名快照始终更新；归属仍是临时人时照旧覆盖姓名/部门（现状行为），
      已归并 PC 用户的不覆盖（姓名/部门以 PC 端维护为准）。
    - 未命中 → 建临时人（提报人）+ 渠道身份；人表已有该渠道编号的（存量/测试直插）则补建身份行。
    """
    identity = await _find_identity(db, channel, profile.user_id)
    if identity is None:
        identity = await _create_identity(db, profile, channel)
    user = (await db.execute(select(User).where(User.id == identity.user_id)
                             .with_for_update().execution_options(populate_existing=True))
            ).scalar_one()
    identity.channel_user_name = profile.name
    if user.channel != "ACCOUNT":  # 未归并临时人：照旧覆盖（已归并 PC 用户不覆盖）
        user.name = profile.name
        user.dept_name = profile.dept_name
    user.last_login_at = now()
    if user.status != "ACTIVE":
        raise BizError(ErrorCode.CHANNEL_ACCOUNT_UNAVAILABLE)
    return user


async def login_existing(db, wecom_userid: str, name: str) -> User:
    """测试环境手动登录：仅放行用户表中已存在且姓名一致的账号，绝不建档。"""
    user = (await db.execute(select(User).where(User.wecom_userid == wecom_userid)
        .with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
    if user is None or user.name != name:
        raise BizError(ErrorCode.TEST_LOGIN_IDENTITY_INVALID)
    if user.status != "ACTIVE":
        raise BizError(ErrorCode.CHANNEL_ACCOUNT_UNAVAILABLE)
    user.last_login_at = now()
    return user


async def get_active(db, user_id: int):
    return (await db.execute(select(User).where(User.id == user_id, User.status == "ACTIVE"))).scalar_one_or_none()
