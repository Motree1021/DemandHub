from datetime import datetime, timedelta, timezone
from hashlib import sha256
from secrets import token_urlsafe
from uuid import uuid4

import jwt
from fastapi import HTTPException
from passlib.context import CryptContext

from app.config import get_settings
from app.db.models import User

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """BCrypt 打"指纹"：只存哈希，绝不明文入库/入日志。"""
    return _pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _pwd_context.verify(password, password_hash)


def new_refresh_token() -> tuple[str, str]:
    """生成续期凭证：返回（明文 token 给前端，sha256 哈希入库）。原文绝不落库。"""
    raw = token_urlsafe(48)
    return raw, hash_refresh_token(raw)


def hash_refresh_token(raw: str) -> str:
    return sha256(raw.encode()).hexdigest()


def issue_token(user: User) -> tuple[str, int]:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    expires_in = settings.jwt_access_ttl_hours * 3600
    token = jwt.encode({"sub": str(user.id), "uid": user.wecom_userid, "name": user.name,
                        "channel": user.channel, "iat": now, "exp": now + timedelta(seconds=expires_in),
                        "jti": str(uuid4())}, settings.jwt_secret, algorithm="HS256")
    return token, expires_in


def decode_token(token: str) -> dict:
    try:
        claims = jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"],
                            options={"require": ["sub", "uid", "channel", "iat", "exp", "jti"]})
        int(claims["sub"])
        return claims
    except (jwt.PyJWTError, ValueError, TypeError):
        raise HTTPException(401, "未登录或登录已过期") from None
