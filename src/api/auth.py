"""API key authentication and admin authorization."""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets

from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.db.models.auth import APIKey
from src.db.session import get_db

logger = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False)

BOOTSTRAP_KEY_NAME = "bootstrap"
_BOOTSTRAP_MIN_LENGTH = 16
_BOOTSTRAP_PLACEHOLDER = "change-me-before-use"  # value shipped in .env.example


def _sha256(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _bootstrap_hash() -> str | None:
    """SHA-256 of ``API_KEY_BOOTSTRAP`` when it is usable, else ``None`` (bootstrap disabled)."""
    from src.config import get_settings

    raw = get_settings().api_key_bootstrap or ""
    if len(raw) < _BOOTSTRAP_MIN_LENGTH or raw == _BOOTSTRAP_PLACEHOLDER:
        return None
    return _sha256(raw)


def _is_bootstrap_row(key: APIKey) -> bool:
    return key.name == BOOTSTRAP_KEY_NAME and key.created_by == BOOTSTRAP_KEY_NAME


def _ensure_bootstrap_row(db: Session, key_hash: str) -> APIKey:
    """Store the bootstrap key as an admin ``APIKey`` row on first use (rows need an id for FKs)."""
    from src.config import get_settings

    key = APIKey(
        key_hash=key_hash,
        name=BOOTSTRAP_KEY_NAME,
        created_by=BOOTSTRAP_KEY_NAME,
        principal=get_settings().bootstrap_principal,
        is_admin=True,
    )
    db.add(key)
    try:
        db.commit()
    except IntegrityError:  # a concurrent first request stored it already
        db.rollback()
        return db.query(APIKey).filter(APIKey.key_hash == key_hash).one()
    db.refresh(key)
    logger.info("Stored bootstrap admin API key (principal=%s)", key.principal)
    return key


def active_api_key(db: Session, raw_key: str | None) -> APIKey | None:
    """Return the active ``APIKey`` matching *raw_key*, or ``None`` (missing/unknown/expired/revoked).

    Shared by REST (``require_api_key``) and the WebSocket handlers so both authenticate
    identically. The bootstrap key (``API_KEY_BOOTSTRAP``) is accepted as an admin key and stored
    on first use; a stored bootstrap row stops working once ``API_KEY_BOOTSTRAP`` changes.
    """
    if not raw_key:
        return None
    key_hash = _sha256(raw_key)
    bootstrap_hash = _bootstrap_hash()
    api_key = db.query(APIKey).filter(APIKey.key_hash == key_hash).first()
    if api_key is None:
        if bootstrap_hash is not None and hmac.compare_digest(key_hash, bootstrap_hash):
            return _ensure_bootstrap_row(db, key_hash)
        return None
    if not api_key.is_active:
        return None
    if _is_bootstrap_row(api_key) and (
        bootstrap_hash is None or not hmac.compare_digest(api_key.key_hash, bootstrap_hash)
    ):
        return None  # a previous API_KEY_BOOTSTRAP value
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


def require_admin(api_key: APIKey = Depends(require_api_key)) -> APIKey:
    """Allow only admin keys (API-key management)."""
    if not api_key.is_admin:
        raise HTTPException(status_code=403, detail="Admin API key required")
    return api_key


def generate_api_key() -> tuple[str, str]:
    """Return (raw_key, sha256_hash)."""
    raw = secrets.token_urlsafe(32)
    return raw, _sha256(raw)
