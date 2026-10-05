from sqlalchemy import select
from sqlalchemy.dialects.mysql import insert

from app.core.errors import BizError, ErrorCode
from app.db.models import User, now


async def upsert_from_sso(db, profile, channel="CHUANGJIN_LS") -> User:
    values = profile.model_dump(exclude={"user_id"})
    values.update(wecom_userid=profile.user_id, channel=channel, last_login_at=now())
    statement = insert(User).values(**values, status="ACTIVE")
    await db.execute(statement.on_duplicate_key_update(**{key: statement.inserted[key] for key in values if key != "wecom_userid"}))
    user = (await db.execute(select(User).where(User.wecom_userid == profile.user_id).with_for_update().execution_options(populate_existing=True))).scalar_one()
    if user.status != "ACTIVE":
        raise BizError(ErrorCode.CHANNEL_ACCOUNT_UNAVAILABLE)
    return user


async def get_active(db, user_id: int):
    return (await db.execute(select(User).where(User.id == user_id, User.status == "ACTIVE"))).scalar_one_or_none()
