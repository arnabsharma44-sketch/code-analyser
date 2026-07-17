import base64
import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.config import settings


def create_access_token(user_id: int, ttl_seconds: int | None = None) -> str:
    expires_in = ttl_seconds or settings.auth_session_ttl_seconds
    issued_at = datetime.now(timezone.utc)
    expires_at = issued_at + timedelta(seconds=expires_in)

    payload = {
        "sub": str(user_id),
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
        "jti": uuid.uuid4().hex,
        "type": "access",
    }
    encoded_payload = _b64encode_json(payload)
    signature = hmac.new(
        settings.get_auth_secret_key().encode("utf-8"),
        encoded_payload.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return f"{encoded_payload}.{_b64encode_bytes(signature)}"


def verify_access_token(token: str) -> dict[str, Any] | None:
    try:
        encoded_payload, encoded_signature = token.split(".", 1)
    except ValueError:
        return None

    expected_signature = hmac.new(
        settings.get_auth_secret_key().encode("utf-8"),
        encoded_payload.encode("utf-8"),
        hashlib.sha256,
    ).digest()

    if not hmac.compare_digest(encoded_signature, _b64encode_bytes(expected_signature)):
        return None

    try:
        payload = json.loads(_b64decode(encoded_payload))
    except (ValueError, json.JSONDecodeError):
        return None

    if payload.get("type") != "access":
        return None

    exp = payload.get("exp")
    if isinstance(exp, int) and exp <= int(datetime.now(timezone.utc).timestamp()):
        return None

    return payload


def _b64encode_json(payload: dict[str, Any]) -> str:
    return _b64encode_bytes(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))


def _b64encode_bytes(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii")


def _b64decode(value: str) -> str:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding).decode("utf-8")
