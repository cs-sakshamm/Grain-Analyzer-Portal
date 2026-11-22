"""Password, access-token and refresh-token primitives.

Human and device tokens share the JWT implementation but are distinguished by the
``typ`` claim, and every decoder requires the type it expects. A device token can
therefore never be replayed on a human route (or the reverse).
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from argon2.low_level import Type

HUMAN_TOKEN_TYPE = "user_access"
DEVICE_TOKEN_TYPE = "device_access"
JWT_ALGORITHM = "HS256"

# Argon2id per the security architecture: 64 MiB, 3 iterations, parallelism 2.
_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=64 * 1024,
    parallelism=2,
    hash_len=32,
    salt_len=16,
    type=Type.ID,
)

# Verifying against this hash for unknown accounts keeps the failure path expensive
# and roughly constant-time, so response timing does not reveal account existence.
DUMMY_PASSWORD_HASH = _hasher.hash("rice-age-timing-equalisation-placeholder")


class TokenError(Exception):
    """Raised when a bearer token is missing, malformed, expired or the wrong type."""


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(encoded_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(encoded_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(encoded_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(encoded_hash)
    except InvalidHashError:
        return True


def create_access_token(
    *,
    secret: str,
    issuer: str,
    audience: str,
    ttl_minutes: int,
    subject: uuid.UUID | str,
    token_type: str,
    claims: dict[str, Any] | None = None,
) -> tuple[str, int]:
    """Return ``(encoded_token, expires_in_seconds)``."""

    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=ttl_minutes)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "typ": token_type,
        "iss": issuer,
        "aud": audience,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "jti": uuid.uuid4().hex,
    }
    if claims:
        payload.update(claims)
    encoded = jwt.encode(payload, secret, algorithm=JWT_ALGORITHM)
    return encoded, int(timedelta(minutes=ttl_minutes).total_seconds())


def decode_access_token(
    *,
    token: str,
    secret: str,
    issuer: str,
    audience: str,
    expected_type: str,
) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[JWT_ALGORITHM],
            audience=audience,
            issuer=issuer,
            options={"require": ["exp", "iat", "sub", "typ"]},
        )
    except jwt.PyJWTError as exc:
        raise TokenError("invalid token") from exc
    if payload.get("typ") != expected_type:
        raise TokenError("wrong token type for this route")
    return payload


def generate_refresh_token() -> str:
    """Opaque 384-bit refresh secret. Only its SHA-256 is stored."""

    return secrets.token_urlsafe(48)


def hash_refresh_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def generate_device_secret() -> str:
    """Opaque 256-bit device secret, returned exactly once at issuance."""

    return secrets.token_urlsafe(32)


def generate_client_id() -> str:
    return "dev_" + secrets.token_hex(12)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
