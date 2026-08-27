"""Instrument search and validation."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from ..deps import ContainerDep
from ..schemas import InstrumentOut, InstrumentSummaryOut

router = APIRouter(prefix="/instruments", tags=["instruments"])


@router.get("/search", response_model=list[InstrumentSummaryOut])
async def search(
    container: ContainerDep,
    q: str = Query(min_length=1, description="Ticker, ISIN or part of the name"),
    limit: int = Query(20, ge=1, le=100),
    traded_only: bool = Query(True),
) -> list[InstrumentSummaryOut]:
    hits = await container.directory.search(q, limit)
    if traded_only:
        traded = [h for h in hits if h.is_traded]
        hits = traded or hits
    return [InstrumentSummaryOut.from_domain(h) for h in hits]


@router.get("/{secid}", response_model=InstrumentOut)
async def resolve(
    container: ContainerDep, secid: str, board: str | None = None
) -> InstrumentOut:
    """Validate a ticker. 404 means "no such instrument on MOEX"."""
    return InstrumentOut.from_domain(await container.directory.resolve(secid, board))


@router.get("/{secid}/boards")
async def boards(container: ContainerDep, secid: str) -> list[dict[str, Any]]:
    return await container.directory.list_boards(secid)
