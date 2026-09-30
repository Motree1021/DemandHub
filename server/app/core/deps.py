from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import get_settings
from app.core.errors import BizError, ErrorCode
from app.core.security import decode_token
from app.db.models import User
from app.db.session import get_db, get_session_factory

bearer = HTTPBearer(auto_error=False)


async def get_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(401, "未登录或登录已过期")
    claims = decode_token(credentials.credentials)
    # 身份查询使用独立短事务，避免业务 autobegin 与模型等待期间占用连接。
    async with get_session_factory()() as db:
        user = await db.get(User, int(claims["sub"]))
        if user is None or user.status != "ACTIVE":
            raise HTTPException(401, "未登录或登录已过期")
        db.expunge(user)
        return user


def is_admin(user: User) -> bool:
    return user.wecom_userid in get_settings().admin_ids


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if not is_admin(user):
        raise BizError(ErrorCode.FORBIDDEN)
    return user


__all__ = ["get_db", "get_current_user", "require_admin", "is_admin"]
