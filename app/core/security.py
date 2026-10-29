import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import jwt
from pwdlib import PasswordHash

from app.config import settings
from app.core.exceptions import UnauthorizedError

password_hasher = PasswordHash.recommended()  # argon2

TokenType = Literal["access", "refresh"]


def hash_password(plain_password: str) -> str:
    return password_hasher.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return password_hasher.verify(plain_password, hashed_password)
    except Exception:
        return False


def _create_token(subject: str, token_type: TokenType, expires_in_seconds: int) -> tuple[str, str, datetime]:
    """Returns (token_string, jti, expires_at)."""
    now = datetime.now(timezone.utc)
    jti = str(uuid.uuid4())
    expires_at = now + timedelta(seconds=expires_in_seconds)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "exp": expires_at,
        "jti": jti,
    }
    token = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return token, jti, expires_at


def create_access_token(user_id: uuid.UUID) -> str:
    token, _, _ = _create_token(str(user_id), "access", settings.JWT_EXPIRATION_DELTA)
    return token


def token_issued_before(token_payload: dict[str, Any], changed_at: datetime) -> bool:
    issued_at = token_payload.get("iat")
    if issued_at is None:
        return True
    issued_at_datetime = datetime.fromtimestamp(float(issued_at), tz=timezone.utc)
    return issued_at_datetime < changed_at


def create_refresh_token(user_id: uuid.UUID) -> tuple[str, str, datetime]:
    """Returns (token_string, jti, expires_at) so the caller can persist it."""
    return _create_token(str(user_id), "refresh", settings.REFRESH_TOKEN_EXPIRATION_DELTA)


def decode_token(token: str, expected_type: TokenType, *, verify_exp: bool = True) -> dict[str, Any]:
    """
    Verifies signature and token type. `verify_exp=False` still checks the
    signature but accepts expired tokens (used by logout, so an expired
    refresh token doesn't prevent signing out).
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
            options={"verify_exp": verify_exp},
        )
    except jwt.ExpiredSignatureError:
        raise UnauthorizedError(f"{expected_type.capitalize()} token has expired.")
    except jwt.InvalidTokenError:
        raise UnauthorizedError(f"Invalid {expected_type} token.")

    if payload.get("type") != expected_type:
        raise UnauthorizedError(f"Expected a {expected_type} token.")

    return payload