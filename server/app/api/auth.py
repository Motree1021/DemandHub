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
from app.services.user_service import upsert_from_sso
from app.sso.chuangjin_ls import ChuangjinLsSsoClient
from app.sso.schemas import ChannelSsoConfig, SsoProfile

router = APIRouter(prefix="/auth")
dev_router = APIRouter(prefix="/auth")
parameters_router = APIRouter(prefix="/auth")


@lru_cache
def get_sso_client():
    settings = get_settings()
    return ChuangjinLsSsoClient(ChannelSsoConfig(base_url=settings.channel_ls_base_url,
        app_key=settings.channel_ls_app_key, app_secret=settings.channel_ls_app_secret,
        timeout_ms=settings.channel_ls_timeout_ms))


def user_info(user: User) -> dict:
    return {"id": user.id, "userId": user.wecom_userid, "name": user.name,
            "deptName": user.dept_name, "deptPath": user.dept_path,
            "channel": user.channel, "isAdmin": is_admin(user)}


def login_response(user: User):
    token, expires_in = issue_token(user)
    return ok({"accessToken": token, "tokenType": "Bearer", "expiresIn": expires_in, "user": user_info(user)})


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
        user = await upsert_from_sso(db, profile)
    return login_response(user)


@router.get("/channel-sso")
async def channel_sso(channel: str = Query(...), ticket: str = Query(..., max_length=2048),
                      state: str | None = None, db: AsyncSession = Depends(get_db)):
    if channel not in {"chuangjinls", "CHUANGJIN_LS"}:
        raise BizError(ErrorCode.CHANNEL_DISABLED)
    profile = await get_sso_client().verify(ticket)
    async with db.begin():
        user = await upsert_from_sso(db, profile)
    return login_response(user)


class DevLogin(ApiModel):
    name: str = Field(min_length=1, max_length=64)
    wecom_userid: str = Field(min_length=1, max_length=64)


@dev_router.post("/dev-login")
async def dev_login(payload: DevLogin, db: AsyncSession = Depends(get_db)):
    async with db.begin():
        user = await upsert_from_sso(db, SsoProfile(user_id=payload.wecom_userid, name=payload.name))
    return login_response(user)


@router.get("/me")
async def me(user: User = Depends(get_current_user)):
    return ok(user_info(user))
