"""账密登录与续期凭证服务：登录锁定、双 token 签发/旋转/吊销、改密联动吊销。"""
from datetime import timedelta

from sqlalchemy import select, update

from app.config import get_settings
from app.core.errors import BizError, ErrorCode
from app.core.security import (
    hash_password,
    hash_refresh_token,
    new_refresh_token,
    verify_password,
)
from app.db.models import RefreshToken, User, now

MAX_FAIL_COUNT = 5
LOCK_MINUTES = 15


async def login_with_password(db, login_account: str, password: str) -> User:
    """账密登录：账号不存在与密码错误同一文案（防探测）；连续 5 次失败锁 15 分钟。
    登录账号未命中时按手机号查（uk_user_phone 全表唯一保证至多一条；
    账号优先——手机号与他人登录账号撞串时进入登录账号的主人，无歧义）。"""
    user = (await db.execute(select(User).where(User.login_account == login_account)
                             .with_for_update())).scalar_one_or_none()
    if user is None:
        user = (await db.execute(select(User).where(User.phone == login_account)
                                 .with_for_update())).scalar_one_or_none()
    if user is None or user.password_hash is None:
        raise BizError(ErrorCode.AUTH_LOGIN_FAILED)
    if user.status != "ACTIVE":
        raise BizError(ErrorCode.CHANNEL_ACCOUNT_UNAVAILABLE)
    current = now()
    if user.locked_until and user.locked_until > current:
        raise BizError(ErrorCode.AUTH_ACCOUNT_LOCKED)
    if not verify_password(password, user.password_hash):
        user.fail_count += 1
        if user.fail_count >= MAX_FAIL_COUNT:
            user.locked_until = current + timedelta(minutes=LOCK_MINUTES)
            user.fail_count = 0  # 锁定后归零，解锁即恢复 5 次机会
        raise BizError(ErrorCode.AUTH_LOGIN_FAILED)
    user.fail_count = 0
    user.locked_until = None
    user.last_login_at = current
    return user


async def issue_refresh(db, user: User) -> str:
    """签发续期凭证：明文返回给前端，库里只存 sha256 哈希。"""
    raw, token_hash = new_refresh_token()
    db.add(RefreshToken(user_id=user.id, token_hash=token_hash,
                        expires_at=now() + timedelta(days=get_settings().refresh_token_ttl_days)))
    return raw


async def rotate_refresh(db, raw_token: str) -> tuple[User, str]:
    """旋转续期：旧票即时吊销换发新票；过期/已吊销/不存在的票一律拒绝。"""
    row = (await db.execute(select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(raw_token))
                            .with_for_update())).scalar_one_or_none()
    if row is None or row.revoked or row.expires_at <= now():
        raise BizError(ErrorCode.AUTH_REFRESH_INVALID)
    user = (await db.execute(select(User).where(User.id == row.user_id))).scalar_one_or_none()
    if user is None or user.status != "ACTIVE":
        raise BizError(ErrorCode.AUTH_REFRESH_INVALID)
    row.revoked = True
    return user, await issue_refresh(db, user)


async def revoke_refresh(db, raw_token: str) -> None:
    """登出吊销：幂等，票不存在也视为成功（不泄露票据状态）。"""
    await db.execute(update(RefreshToken)
                     .where(RefreshToken.token_hash == hash_refresh_token(raw_token))
                     .values(revoked=True))


async def revoke_all_refresh(db, user_id: int) -> None:
    """改密/禁用/重置密码后吊销该用户全部续期凭证，旧登录态强制下线。"""
    await db.execute(update(RefreshToken)
                     .where(RefreshToken.user_id == user_id, RefreshToken.revoked.is_(False))
                     .values(revoked=True))


async def change_password(db, user: User, old_password: str, new_password: str) -> None:
    """本人改密：校验旧密码，改后解除强制改密标记并吊销全部续期凭证。"""
    if not user.password_hash or not verify_password(old_password, user.password_hash):
        raise BizError(ErrorCode.AUTH_OLD_PASSWORD_WRONG)
    user.password_hash = hash_password(new_password)
    user.must_change_pwd = False
    await revoke_all_refresh(db, user.id)
