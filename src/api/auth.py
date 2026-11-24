"""API key authentication dependency."""

from __future__ import annotations

import hashlib
import secrets

from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from src.db.models.auth import APIKey
from src.db.session import get_db

_bearer = HTTPBearer(auto_error=False)


def _sha256(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def active_api_key(db: Session, raw_key: str | None) -> APIKey | None:
    """Return the active ``APIKey`` matching *raw_key*, or ``None`` (missing/unknown/expired/revoked).

    Shared by REST (``require_api_key``) and the WebSocket handlers so both authenticate identically.
    """
    if not raw_key:
        return None
    api_key = db.query(APIKey).filter(APIKey.key_hash == _sha256(raw_key)).first()
    if api_key is None or not api_key.is_active:
        return None
    return api_key


def require_api_key(
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer),
    db: Session = Depends(get_db),
) -> APIKey:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    api_key = active_api_key(db, credentials.credentials)
    if api_key is None:
        raise HTTPException(status_code=401, detail="Invalid or expired API key")
    return api_key


def generate_api_key() -> tuple[str, str]:
    """Return (raw_key, sha256_hash)."""
    raw = secrets.token_urlsafe(32)
    return raw, _sha256(raw)
