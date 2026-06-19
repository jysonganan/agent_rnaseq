"""Reference genome endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from src.api.auth import require_api_key
from src.api.schemas import CreateGenomeIn, GenomeListOut, GenomeOut
from src.db.models.auth import APIKey
from src.db.models.genome import ReferenceGenome
from src.db.session import get_db

router = APIRouter(prefix="/genomes", tags=["genomes"])


@router.get("", response_model=GenomeListOut)
def list_genomes(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: APIKey = Depends(require_api_key),
) -> GenomeListOut:
    total = db.query(ReferenceGenome).count()
    items = db.query(ReferenceGenome).offset(offset).limit(limit).all()
    return GenomeListOut(
        items=[GenomeOut.model_validate(g) for g in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=GenomeOut, status_code=201)
def create_genome(
    body: CreateGenomeIn,
    db: Session = Depends(get_db),
    _: APIKey = Depends(require_api_key),
) -> GenomeOut:
    genome = ReferenceGenome(**body.model_dump())
    db.add(genome)
    db.commit()
    db.refresh(genome)
    return GenomeOut.model_validate(genome)


@router.get("/{genome_id}", response_model=GenomeOut)
def get_genome(
    genome_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: APIKey = Depends(require_api_key),
) -> GenomeOut:
    genome = db.get(ReferenceGenome, genome_id)
    if genome is None:
        raise HTTPException(status_code=404, detail=f"Genome {genome_id!s} not found")
    return GenomeOut.model_validate(genome)
