"""API key management endpoints."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.api.auth import generate_api_key, require_api_key
from src.api.schemas import APIKeyCreateOut, APIKeyListOut, APIKeyOut, CreateAPIKeyIn
from src.db.models.auth import APIKey
from src.db.session import get_db

router = APIRouter(prefix="/api-keys", tags=["api-keys"])


@router.post("", response_model=APIKeyCreateOut, status_code=201)
def create_api_key(
    body: CreateAPIKeyIn,
    db: Session = Depends(get_db),
    issuer: APIKey = Depends(require_api_key),
) -> APIKeyCreateOut:
    raw, key_hash = generate_api_key()
    api_key = APIKey(
        key_hash=key_hash,
        name=body.name,
        created_by=issuer.name,
        expires_at=body.expires_at,
    )
    db.add(api_key)
    db.commit()
    db.refresh(api_key)
    out = APIKeyOut.model_validate(api_key)
    return APIKeyCreateOut(**out.model_dump(), raw_key=raw)


@router.get("", response_model=APIKeyListOut)
def list_api_keys(
    db: Session = Depends(get_db),
    _: APIKey = Depends(require_api_key),
) -> APIKeyListOut:
    items = db.query(APIKey).all()
    return APIKeyListOut(
        items=[APIKeyOut.model_validate(k) for k in items], total=len(items)
    )


@router.delete("/{key_id}", status_code=204)
def revoke_api_key(
    key_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: APIKey = Depends(require_api_key),
) -> None:
    api_key = db.get(APIKey, key_id)
    if api_key is None:
        raise HTTPException(status_code=404, detail=f"API key {key_id!s} not found")
    if api_key.revoked_at is not None:
        raise HTTPException(status_code=409, detail="API key already revoked")
    api_key.revoked_at = datetime.now(UTC)
    db.commit()
