import hashlib
import hmac

VERIFY_PATH = "/openapi/demandhub/sso/verify"


def string_to_sign(path: str, app_key: str, timestamp: str, nonce: str, body: str) -> str:
    return "\n".join(("POST", path, app_key, timestamp, nonce, body or ""))


def hmac_sha256_hex(secret: str, data: str) -> str:
    return hmac.new(secret.encode(), data.encode(), hashlib.sha256).hexdigest()


def mask_ticket(ticket: str | None) -> str:
    return ticket[:4] + "***" if ticket and len(ticket) > 4 else "***"


def mask_phone(phone: str | None) -> str | None:
    if phone is None:
        return None
    return phone[:3] + "****" + phone[-4:] if len(phone) >= 7 else "***"
