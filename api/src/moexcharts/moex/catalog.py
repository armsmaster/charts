"""Instrument directory and interval catalog backed by MOEX ISS."""

from __future__ import annotations

import time
from typing import Any

from ..domain.models import (
    Instrument,
    InstrumentNotFoundError,
    InstrumentSummary,
    Interval,
    UnknownIntervalError,
    UpstreamError,
)
from .client import IssClient

#: Used when ISS cannot be reached at startup. Mirrors /iss/index.json durations.
FALLBACK_INTERVALS: tuple[Interval, ...] = (
    Interval(1, 60, "1 минута"),
    Interval(10, 600, "10 минут"),
    Interval(60, 3600, "1 час"),
    Interval(24, 86_400, "1 день"),
    Interval(7, 604_800, "1 неделя"),
    Interval(31, 2_678_400, "1 месяц"),
    Interval(4, 8_035_200, "1 квартал"),
)


class IssIntervalCatalog:
    """Timeframe options, sourced from ISS ``/index.json`` durations block.

    Cached in-process: the list changes roughly never, and the UI asks for it on
    every page load.
    """

    def __init__(self, client: IssClient, cache_seconds: int = 3600):
        self._client = client
        self._cache_seconds = cache_seconds
        self._cache: list[Interval] | None = None
        self._cached_at = 0.0

    async def list_intervals(self) -> list[Interval]:
        if self._cache is not None and time.monotonic() - self._cached_at < self._cache_seconds:
            return self._cache
        try:
            rows = await self._client.get_rows(
                "/index.json", "durations", {"iss.only": "durations"}
            )
            intervals = [
                Interval(
                    code=int(row["interval"]),
                    seconds=int(row["duration"]),
                    title=str(row.get("title") or f"{row['interval']}"),
                )
                for row in rows
                if row.get("interval") is not None and row.get("duration")
            ]
        except (UpstreamError, KeyError, TypeError, ValueError):
            intervals = []
        if not intervals:
            intervals = list(FALLBACK_INTERVALS)
        intervals.sort(key=lambda i: i.seconds)
        self._cache = intervals
        self._cached_at = time.monotonic()
        return intervals

    async def get_interval(self, code: int) -> Interval:
        for interval in await self.list_intervals():
            if interval.code == code:
                return interval
        known = ", ".join(str(i.code) for i in await self.list_intervals())
        raise UnknownIntervalError(f"Unknown interval {code}. Known intervals: {known}.")


def _describe(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Flatten the ISS ``description`` block into ``{NAME: value}``."""
    return {str(row.get("name", "")).upper(): row.get("value") for row in rows}


def _pick_board(boards: list[dict[str, Any]], wanted: str | None) -> dict[str, Any]:
    if wanted:
        for board in boards:
            if str(board.get("boardid", "")).upper() == wanted.upper():
                return board
        raise InstrumentNotFoundError(f"Board {wanted!r} is not available for this instrument.")
    traded = [b for b in boards if b.get("is_traded")]
    for candidate in (traded, boards):
        primary = [b for b in candidate if b.get("is_primary")]
        if primary:
            return primary[0]
        if candidate:
            return candidate[0]
    raise InstrumentNotFoundError("Instrument has no trading boards with candle history.")


class IssInstrumentDirectory:
    """Search and existence-validation for MOEX instruments.

    ``resolve`` is the validation entry point: it raises
    :class:`InstrumentNotFoundError` for anything ISS does not know, and returns
    an :class:`Instrument` pinned to a concrete engine/market/board otherwise.
    """

    def __init__(self, client: IssClient):
        self._client = client

    async def search(self, query: str, limit: int = 20) -> list[InstrumentSummary]:
        query = query.strip()
        if not query:
            return []
        rows = await self._client.get_rows(
            "/securities.json",
            "securities",
            {"q": query, "limit": min(max(limit, 1), 100), "iss.only": "securities"},
        )
        summaries = [
            InstrumentSummary(
                secid=str(row.get("secid") or ""),
                shortname=str(row.get("shortname") or ""),
                name=str(row.get("name") or ""),
                type=str(row.get("type") or ""),
                group=str(row.get("group") or ""),
                primary_board=str(row.get("primary_boardid") or ""),
                is_traded=bool(row.get("is_traded")),
            )
            for row in rows
            if row.get("secid")
        ]
        # Currently traded instruments first, then exact-prefix matches.
        upper = query.upper()
        summaries.sort(
            key=lambda s: (
                not s.is_traded,
                not s.secid.upper().startswith(upper),
                s.secid,
            )
        )
        return summaries[:limit]

    async def resolve(self, secid: str, board: str | None = None) -> Instrument:
        secid = secid.strip().upper()
        if not secid:
            raise InstrumentNotFoundError("Ticker is empty.")
        payload = await self._client.get(
            f"/securities/{secid}.json", {"iss.only": "description,boards"}
        )
        from .client import iter_block_rows

        description = _describe(list(iter_block_rows(payload, "description")))
        boards = list(iter_block_rows(payload, "boards"))
        if not description and not boards:
            raise InstrumentNotFoundError(f"Instrument {secid!r} was not found on MOEX.")
        if not boards:
            raise InstrumentNotFoundError(
                f"Instrument {secid!r} exists but has no trading board with candle history."
            )
        chosen = _pick_board(boards, board)
        return Instrument(
            secid=str(chosen.get("secid") or secid).upper(),
            shortname=str(description.get("SHORTNAME") or chosen.get("secid") or secid),
            name=str(description.get("NAME") or description.get("SHORTNAME") or secid),
            engine=str(chosen.get("engine") or ""),
            market=str(chosen.get("market") or ""),
            board=str(chosen.get("boardid") or ""),
            board_title=str(chosen.get("title") or ""),
            type=str(description.get("TYPE") or ""),
            group=str(chosen.get("board_group_id") or ""),
            currency=str(description.get("CURRENCYID") or chosen.get("currencyid") or ""),
            is_traded=bool(chosen.get("is_traded")),
        )

    async def list_boards(self, secid: str) -> list[dict[str, Any]]:
        from .client import iter_block_rows

        payload = await self._client.get(
            f"/securities/{secid.strip().upper()}.json", {"iss.only": "boards"}
        )
        return [
            {
                "board": str(row.get("boardid") or ""),
                "title": str(row.get("title") or ""),
                "engine": str(row.get("engine") or ""),
                "market": str(row.get("market") or ""),
                "is_primary": bool(row.get("is_primary")),
                "is_traded": bool(row.get("is_traded")),
            }
            for row in iter_block_rows(payload, "boards")
        ]
