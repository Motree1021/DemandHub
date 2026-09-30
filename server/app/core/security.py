from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
from fastapi import HTTPException

from app.config import get_settings
from app.db.models import User


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
