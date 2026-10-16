from functools import lru_cache

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.deps import get_current_user, get_db, is_admin
from app.core.errors import BizError, ErrorCode
from app.core.result import ApiModel, ok
from app.core.security import issue_token
from app.db.models import User
from app.services import auth_service, role_service, whitelist_service
from app.services.user_service import login_existing, upsert_from_sso
from app.sso.chuangjin_ls import ChuangjinLsSsoClient
from app.sso.schemas import ChannelSsoConfig, SsoProfile

router = APIRouter(prefix="/auth")
dev_router = APIRouter(prefix="/auth")
test_router = APIRouter(prefix="/auth")
parameters_router = APIRouter(prefix="/auth")


@lru_cache
def get_sso_client():
    settings = get_settings()
    return ChuangjinLsSsoClient(ChannelSsoConfig(base_url=settings.channel_ls_base_url,
        app_key=settings.channel_ls_app_key, app_secret=settings.channel_ls_app_secret,
        timeout_ms=settings.channel_ls_timeout_ms))


def user_info(user: User, roles: frozenset[str] | set[str] | None = None) -> dict:
    """登录态用户出参；roles=有效角色（静态 ∪ 授权），按 ROLE_CODES 定义顺序排序，缺省仅静态角色。"""
    effective = roles if roles is not None else {user.role}
    ordered = [code for code in role_service.ROLE_CODES if code in effective]
    return {"id": user.id, "userId": user.wecom_userid, "name": user.name,
            "deptName": user.dept_name, "deptPath": user.dept_path,
            "channel": user.channel, "isAdmin": is_admin(user),
            "role": user.role, "roles": ordered, "mustChangePwd": user.must_change_pwd}


async def login_response(db: AsyncSession, user: User):
    token, expires_in = issue_token(user)
    roles = await role_service.effective_roles(db, user)
    return ok({"accessToken": token, "tokenType": "Bearer", "expiresIn": expires_in,
               "user": user_info(user, roles)})


class ChannelParameters(BaseModel):
    """仅用于测试参数联调；宿主 Token 不参与身份真实性验证。"""
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    userid: str = Field(min_length=1, max_length=64)
    auth_token: str = Field(alias="authToken", min_length=1, max_length=4096, repr=False)
    user_name: str = Field(alias="userName", min_length=1, max_length=64)
    department: str | None = Field(default=None, max_length=128)

    @field_validator("userid", "user_name")
    @classmethod
    def trim_identity(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("身份字段不能为空")
        return value

    @field_validator("auth_token")
    @classmethod
    def require_token_shape(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("宿主 Token 不能为空")
        return value

    @field_validator("department")
    @classmethod
    def trim_department(cls, value: str | None) -> str | None:
        return (value.strip() or None) if value is not None else None


@parameters_router.post("/channel-parameters")
async def channel_parameters(payload: ChannelParameters, db: AsyncSession = Depends(get_db)):
    # auth_token 只完成 DTO 非空/长度检查，绝不传给持久化、JWT或日志。
    profile = SsoProfile(user_id=payload.userid, name=payload.user_name,
                         dept_name=payload.department)
    async with db.begin():
        await whitelist_service.assert_allowed(db, "CHUANGJIN_LS", profile.user_id)
        user = await upsert_from_sso(db, profile)
    return await login_response(db, user)


@router.get("/channel-sso")
async def channel_sso(channel: str = Query(...), ticket: str = Query(..., max_length=2048),
                      state: str | None = None, db: AsyncSession = Depends(get_db)):
    if channel not in {"chuangjinls", "CHUANGJIN_LS"}:
        raise BizError(ErrorCode.CHANNEL_DISABLED)
    profile = await get_sso_client().verify(ticket)
    async with db.begin():
        await whitelist_service.assert_allowed(db, "CHUANGJIN_LS", profile.user_id)
        user = await upsert_from_sso(db, profile)
    return await login_response(db, user)


@router.get("/whitelist-contact")
async def whitelist_contact(db: AsyncSession = Depends(get_db)):
    """拦截页联系引导（公开接口：被拦用户无登录态，拿不到鉴权接口）。"""
    return ok({"contact": await whitelist_service.get_contact(db, "CHUANGJIN_LS")})


class DevLogin(ApiModel):
    name: str = Field(min_length=1, max_length=64)
    wecom_userid: str = Field(min_length=1, max_length=64)


@dev_router.post("/dev-login")
async def dev_login(payload: DevLogin, db: AsyncSession = Depends(get_db)):
    async with db.begin():
        user = await upsert_from_sso(db, SsoProfile(user_id=payload.wecom_userid, name=payload.name))
    return await login_response(db, user)


class TestLogin(ApiModel):
    name: str = Field(min_length=1, max_length=64)
    wecom_userid: str = Field(min_length=1, max_length=64)

    @field_validator("name", "wecom_userid")
    @classmethod
    def trim_identity(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("身份字段不能为空")
        return value


@test_router.post("/test-login")
async def test_login(payload: TestLogin, db: AsyncSession = Depends(get_db)):
    async with db.begin():
        user = await login_existing(db, payload.wecom_userid, payload.name)
    return await login_response(db, user)


@router.get("/me")
async def me(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return ok(user_info(user, await role_service.effective_roles(db, user)))


# ---------- P1 账密登录（仅管理后台使用，与 H5 渠道 SSO 完全独立） ----------

class AccountLogin(ApiModel):
    login_account: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=64, repr=False)

    @field_validator("login_account")
    @classmethod
    def trim_account(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("登录账号不能为空")
        return value


@router.post("/login")
async def account_login(payload: AccountLogin, db: AsyncSession = Depends(get_db)):
    # 失败计数/锁定也随事务提交（业务错误照常入库），错误在事务提交后再抛出
    error = None
    async with db.begin():
        try:
            user = await auth_service.login_with_password(db, payload.login_account, payload.password)
            refresh_token = await auth_service.issue_refresh(db, user)
        except BizError as exc:
            error = exc
    if error is not None:
        raise error
    token, expires_in = issue_token(user)
    roles = await role_service.effective_roles(db, user)
    return ok({"accessToken": token, "refreshToken": refresh_token, "tokenType": "Bearer",
               "expiresIn": expires_in, "mustChangePwd": user.must_change_pwd,
               "user": user_info(user, roles)})


class ChangePassword(ApiModel):
    old_password: str = Field(min_length=1, max_length=64, repr=False)
    new_password: str = Field(min_length=8, max_length=64, repr=False)


@router.post("/change-password")
async def change_password(payload: ChangePassword, user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    async with db.begin():
        fresh = await db.get(User, user.id)
        await auth_service.change_password(db, fresh, payload.old_password, payload.new_password)
    return ok({"success": True})


class RefreshPayload(ApiModel):
    refresh_token: str = Field(min_length=1, max_length=512, repr=False)


@router.post("/refresh")
async def refresh(payload: RefreshPayload, db: AsyncSession = Depends(get_db)):
    async with db.begin():
        user, new_refresh = await auth_service.rotate_refresh(db, payload.refresh_token)
    token, expires_in = issue_token(user)
    return ok({"accessToken": token, "refreshToken": new_refresh,
               "tokenType": "Bearer", "expiresIn": expires_in})


@router.post("/logout")
async def logout(payload: RefreshPayload, db: AsyncSession = Depends(get_db)):
    async with db.begin():
        await auth_service.revoke_refresh(db, payload.refresh_token)
    return ok({"success": True})
