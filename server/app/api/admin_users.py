"""P1 用户管理（仅 ADMIN）：分页列表/创建/激活/禁用/重置密码/调整角色；出参脱敏，绝不出 password_hash。

P4 角色扩展：role 放开为 ADMIN/EXECUTIVE/MANAGER/HANDLER/REPORTER 五值；
提单/补充等经办辅助类角色由 /admin/grants 本地授权叠加（有效角色=静态 ∪ 授权）。
2026-10-16 多角色：PUT /{id}/roles 一次保存主角色+兼任角色（兼任落空白授权行，见 role_service.sync_user_roles）。
"""
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import Field
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from app.core.deps import get_db, require_admin
from app.core.errors import BizError, ErrorCode
from app.core.result import ApiModel, ok
from app.core.security import hash_password
from app.db.models import ChannelIdentity, User
from app.services import auth_service, role_service

router = APIRouter(prefix="/admin/users", dependencies=[Depends(require_admin)])

RoleCode = Literal["ADMIN", "EXECUTIVE", "MANAGER", "HANDLER", "REPORTER"]
TypeCode = Literal["TECH", "MATL", "TRAIN"]


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


def user_out(user: User, roles: list[str] | None = None,
             identities: list[dict] | None = None) -> dict:
    """用户出参统一收口：脱敏 + 绝不带 password_hash；roles=主角色+兼任（缺省仅主角色）；
    identities=已挂接渠道身份（OneID 一期，仅列表出参带）。"""
    return {"id": user.id, "loginAccount": user.login_account, "name": user.name,
            "wecomUserid": user.wecom_userid,
            "role": user.role, "roles": roles if roles is not None else [user.role],
            "typeScope": role_service.parse_type_scope(user.type_scope) or None,
            "status": user.status, "channel": user.channel,
            "phone": mask_phone(user.phone), "email": mask_email(user.email),
            "mustChangePwd": user.must_change_pwd, "lastLoginAt": user.last_login_at,
            "createdAt": user.created_at,
            "channelIdentities": identities}


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
                     channel: str | None = Query(None, max_length=32),
                     db=Depends(get_db)):
    statement = select(User)
    if keyword:
        like = f"%{keyword.strip()}%"
        statement = statement.where(or_(User.name.like(like), User.login_account.like(like)))
    if role:
        statement = statement.where(User.role == role)
    if status:
        statement = statement.where(User.status == status)
    # OneID：用户管理只管网内正式用户（传 channel=ACCOUNT）；渠道临时人的可见性由「渠道身份」页承载
    if channel:
        statement = statement.where(User.channel == channel)
    total = (await db.execute(select(func.count()).select_from(statement.subquery()))).scalar_one()
    users = (await db.execute(statement.order_by(User.id).offset((page - 1) * size)
                              .limit(size))).scalars().all()
    roles_map = await role_service.user_roles_map(db, [u.id for u in users])
    # OneID：批量取本页用户已挂接的渠道身份（列表灰字展示「渠道：XX·编号」）
    identity_rows = (await db.execute(
        select(ChannelIdentity).where(ChannelIdentity.user_id.in_([u.id for u in users])))
    ).scalars().all() if users else []
    identity_map: dict[int, list[dict]] = {}
    for item in identity_rows:
        identity_map.setdefault(item.user_id, []).append(
            {"channel": item.channel, "channelUserId": item.channel_user_id,
             "channelUserName": item.channel_user_name})
    return ok({"list": [user_out(u, roles_map[u.id], identity_map.get(u.id, [])) for u in users],
               "total": total, "page": page, "size": size})


class CreateUser(ApiModel):
    login_account: str = Field(min_length=2, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
    name: str = Field(min_length=1, max_length=64)
    initial_password: str = Field(min_length=8, max_length=64, repr=False)
    # 手机号必填：联系方式 + 可作登录账号（uk_user_phone 全表唯一）
    phone: str = Field(pattern=r"^1\d{10}$")
    email: str | None = Field(default=None, max_length=128,
                              pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    role: RoleCode = "HANDLER"
    # 多角色（2026-10-18）：与改角色同口径，主角色+兼任一次落位；缺省回退单 role（向后兼容）
    roles: list[RoleCode] | None = Field(default=None, min_length=1)
    types: list[TypeCode] | None = None


@router.post("")
async def create_user(payload: CreateUser, admin=Depends(require_admin), db=Depends(get_db)):
    async with db.begin():
        exists = (await db.execute(select(User.id).where(User.login_account == payload.login_account))).scalar_one_or_none()
        if exists is not None:
            raise BizError(ErrorCode.LOGIN_ACCOUNT_EXISTS)
        phone_taken = (await db.execute(select(User.id).where(User.phone == payload.phone))).scalar_one_or_none()
        if phone_taken is not None:
            raise BizError(ErrorCode.PHONE_EXISTS)
        roles = payload.roles or [payload.role]
        # 账密用户无企微身份，wecom_userid 落占位值 acct:<login_account>（方案A）
        # 主角色/兼任/类型权限由 sync_user_roles 统一校验落位（与改角色同一口径）
        user = User(name=payload.name, wecom_userid=f"acct:{payload.login_account}",
                    channel="ACCOUNT", role=roles[0], login_account=payload.login_account,
                    password_hash=hash_password(payload.initial_password), must_change_pwd=True,
                    phone=payload.phone, email=payload.email)
        db.add(user)
        try:
            await db.flush()
        except IntegrityError as exc:
            # 并发撞唯一键兜底：解析索引名区分手机号 / 登录账号（预查挡不住并发窗口）
            if "uk_user_phone" in str(exc.orig):
                raise BizError(ErrorCode.PHONE_EXISTS) from exc
            raise BizError(ErrorCode.LOGIN_ACCOUNT_EXISTS) from exc
        roles = await role_service.sync_user_roles(db, user, roles, payload.types, granted_by=admin.id)
    return ok(user_out(user, roles))


@router.put("/{user_id}/activate")
async def activate_user(user_id: int, db=Depends(get_db)):
    async with db.begin():
        user = await get_user_or_404(db, user_id)
        user.status = "ACTIVE"
    return ok(user_out(user))


class UpdateRoles(ApiModel):
    roles: list[RoleCode] = Field(min_length=1)
    types: list[TypeCode] | None = None


@router.put("/{user_id}/roles")
async def update_roles(user_id: int, payload: UpdateRoles,
                       admin=Depends(require_admin), db=Depends(get_db)):
    """多角色保存：主角色落 user.role，兼任角色差量同步空白授权行（JWT 不内嵌角色，逐请求读库即时生效）。

    ADMIN 只能作主角色（is_admin 不认授权）；带范围/期限的手工授权行不参与同步。
    有效角色含业务角色时 types 必填（按人统一的需求类型权限），否则 type_scope 清空。
    """
    if user_id == admin.id:
        raise BizError(ErrorCode.PARAM_INVALID, "不能调整当前登录管理员本人的角色")
    async with db.begin():
        user = await get_user_or_404(db, user_id)
        roles = await role_service.sync_user_roles(db, user, payload.roles, payload.types, granted_by=admin.id)
    return ok(user_out(user, roles))


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
