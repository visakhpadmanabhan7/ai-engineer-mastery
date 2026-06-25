"""Password hashing (bcrypt, sha256-prehashed) and JWT issue/verify.

We sha256-prehash before bcrypt so passwords of any length work without the
72-byte bcrypt truncation pitfall, and we avoid the brittle passlib<->bcrypt
version coupling.
"""
from __future__ import annotations

import base64
import hashlib
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from .config import settings


def _prehash(raw: str) -> bytes:
    # 32-byte digest -> base64 (44 bytes), safely under bcrypt's 72-byte limit.
    return base64.b64encode(hashlib.sha256(raw.encode("utf-8")).digest())


def hash_password(raw: str) -> str:
    return bcrypt.hashpw(_prehash(raw), bcrypt.gensalt()).decode("utf-8")


def verify_password(raw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_prehash(raw), hashed.encode("utf-8"))
    except Exception:
        return False


def create_access_token(subject: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": subject, "exp": now + timedelta(minutes=settings.access_token_expire_minutes), "iat": now}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_alg)


def decode_token(token: str) -> str | None:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_alg]).get("sub")
    except jwt.PyJWTError:
        return None
