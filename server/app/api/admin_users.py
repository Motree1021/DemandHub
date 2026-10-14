"""P1 用户管理（仅 ADMIN）：分页列表/创建/激活/禁用/重置密码/调整角色；出参脱敏，绝不出 password_hash。

P4 角色扩展：role 放开为 ADMIN/EXECUTIVE/MANAGER/HANDLER 四值；
提单/补充等经办辅助类角色由 /admin/grants 本地授权叠加（有效角色=静态 ∪ 授权）。
"""
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import Field
from sqlalchemy import func, or_, select

from app.core.deps import get_db, require_admin
from app.core.errors import BizError, ErrorCode
from app.core.result import ApiModel, ok
from app.core.security import hash_password
from app.db.models import User
from app.services import auth_service

router = APIRouter(prefix="/admin/users", dependencies=[Depends(require_admin)])

RoleCode = Literal["ADMIN", "EXECUTIVE", "MANAGER", "HANDLER"]


def mask_phone(phone: str | None) -> str | None:
    """手机脱敏：138****1234；短号保底全掩。"""
    if not phone:
        return phone
    return phone[:3] + "****" + phone[-4:] if len(phone) >= 8 else "****"


def mask_email(email: str | None) -> str | None:
    """邮箱脱敏：a***@example.com。"""
    if not email or "@" not in email:
        return email
    local, domain = email.split("@", 1)
    return local[:1] + "***@" + domain


def user_out(user: User) -> dict:
    """用户出参统一收口：脱敏 + 绝不带 password_hash。"""
    return {"id": user.id, "loginAccount": user.login_account, "name": user.name,
            "wecomUserid": user.wecom_userid,
            "role": user.role, "status": user.status, "channel": user.channel,
            "phone": mask_phone(user.phone), "email": mask_email(user.email),
            "mustChangePwd": user.must_change_pwd, "lastLoginAt": user.last_login_at,
            "createdAt": user.created_at}


async def get_user_or_404(db, user_id: int) -> User:
    user = (await db.execute(select(User).where(User.id == user_id)
                             .with_for_update())).scalar_one_or_none()
    if user is None:
        raise BizError(ErrorCode.USER_NOT_FOUND)
    return user


@router.get("")
async def list_users(page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
                     keyword: str | None = Query(None, max_length=64),
                     role: RoleCode | None = None,
                     status: Literal["ACTIVE", "DISABLED"] | None = None,
                     db=Depends(get_db)):
    statement = select(User)
    if keyword:
        like = f"%{keyword.strip()}%"
        statement = statement.where(or_(User.name.like(like), User.login_account.like(like)))
    if role:
        statement = statement.where(User.role == role)
    if status:
        statement = statement.where(User.status == status)
    total = (await db.execute(select(func.count()).select_from(statement.subquery()))).scalar_one()
    users = (await db.execute(statement.order_by(User.id).offset((page - 1) * size)
                              .limit(size))).scalars().all()
    return ok({"list": [user_out(u) for u in users], "total": total, "page": page, "size": size})


class CreateUser(ApiModel):
    login_account: str = Field(min_length=2, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
    name: str = Field(min_length=1, max_length=64)
    initial_password: str = Field(min_length=8, max_length=64, repr=False)
    role: RoleCode = "HANDLER"


@router.post("")
async def create_user(payload: CreateUser, db=Depends(get_db)):
    async with db.begin():
        exists = (await db.execute(select(User.id).where(User.login_account == payload.login_account))).scalar_one_or_none()
        if exists is not None:
            raise BizError(ErrorCode.LOGIN_ACCOUNT_EXISTS)
        # 账密用户无企微身份，wecom_userid 落占位值 acct:<login_account>（方案A）
        user = User(name=payload.name, wecom_userid=f"acct:{payload.login_account}",
                    channel="ACCOUNT", role=payload.role, login_account=payload.login_account,
                    password_hash=hash_password(payload.initial_password), must_change_pwd=True)
        db.add(user)
        await db.flush()
    return ok(user_out(user))


@router.put("/{user_id}/activate")
async def activate_user(user_id: int, db=Depends(get_db)):
    async with db.begin():
        user = await get_user_or_404(db, user_id)
        user.status = "ACTIVE"
    return ok(user_out(user))


class UpdateRole(ApiModel):
    role: RoleCode


@router.put("/{user_id}/role")
async def update_role(user_id: int, payload: UpdateRole,
                      admin=Depends(require_admin), db=Depends(get_db)):
    """调整静态角色（JWT 不内嵌角色，逐请求读库即时生效，无需强制重登）。"""
    if user_id == admin.id:
        raise BizError(ErrorCode.PARAM_INVALID, "不能调整当前登录管理员本人的角色")
    async with db.begin():
        user = await get_user_or_404(db, user_id)
        user.role = payload.role
    return ok(user_out(user))


@router.put("/{user_id}/disable")
async def disable_user(user_id: int, admin=Depends(require_admin), db=Depends(get_db)):
    if user_id == admin.id:
        raise BizError(ErrorCode.PARAM_INVALID, "不能禁用当前登录的管理员账号")
    async with db.begin():
        user = await get_user_or_404(db, user_id)
        user.status = "DISABLED"
        await auth_service.revoke_all_refresh(db, user.id)  # 禁用即刻下线
    return ok(user_out(user))


class ResetPassword(ApiModel):
    new_password: str = Field(min_length=8, max_length=64, repr=False)


@router.post("/{user_id}/reset-password")
async def reset_password(user_id: int, payload: ResetPassword,
                         admin=Depends(require_admin), db=Depends(get_db)):
    if user_id == admin.id:
        raise BizError(ErrorCode.PARAM_INVALID, "修改本人密码请走 /auth/change-password")
    async with db.begin():
        user = await get_user_or_404(db, user_id)
        user.password_hash = hash_password(payload.new_password)
        user.must_change_pwd = True
        user.fail_count = 0
        user.locked_until = None
        await auth_service.revoke_all_refresh(db, user.id)  # 重置后旧登录态强制下线
    return ok({"success": True})
