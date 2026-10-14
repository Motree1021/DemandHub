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
    """过渡兼容：role=='ADMIN' 或命中企微白名单，满足其一即管理员（P4 白名单退役）。"""
    return user.role == "ADMIN" or user.wecom_userid in get_settings().admin_ids


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if not is_admin(user):
        raise BizError(ErrorCode.FORBIDDEN)
    return user


def require_role(*roles: str):
    """角色守卫工厂：require_role("MANAGER") 返回 Depends。

    有效角色 = 静态 role ∪ 生效授权（demand_role_grant）；任一命中即放行，否则 403。
    ADMIN 直通（is_admin 兼容企微白名单过渡期）。
    """
    allowed = set(roles)

    async def checker(user: User = Depends(get_current_user)) -> User:
        if is_admin(user):
            return user
        # 延迟导入避免 core→services 循环依赖；角色查询同 get_current_user 用独立短事务，
        # 避免在请求级 session 上 autobegin 与端点 db.begin() 撞事务
        from app.services import role_service

        async with get_session_factory()() as db:
            user_roles = await role_service.effective_roles(db, user)
        if allowed.isdisjoint(user_roles):
            raise BizError(ErrorCode.FORBIDDEN)
        return user

    return checker


__all__ = ["get_db", "get_current_user", "require_admin", "require_role", "is_admin"]
