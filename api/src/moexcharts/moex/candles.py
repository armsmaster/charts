"""Candle loading from MOEX ISS."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from ..config import Settings
from ..domain.models import Candle, Instrument, Interval
from ..domain.periods import chunk_range
from .client import IssClient

#: ISS caps a single candles query; splitting long ranges keeps each request
#: small and lets pagination terminate predictably.
_CHUNK_DAYS = 365 * 3


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def row_to_candle(row: dict[str, Any]) -> Candle | None:
    """Map one ISS ``candles`` row to a domain candle, or ``None`` if unusable."""
    begin = _to_datetime(row.get("begin"))
    values = {k: _to_float(row.get(k)) for k in ("open", "high", "low", "close")}
    if begin is None or any(v is None for v in values.values()):
        return None
    return Candle(
        begin=begin,
        open=values["open"],  # type: ignore[arg-type]
        high=values["high"],  # type: ignore[arg-type]
        low=values["low"],  # type: ignore[arg-type]
        close=values["close"],  # type: ignore[arg-type]
        volume=_to_float(row.get("volume")),
        value=_to_float(row.get("value")),
    )


class IssCandleSource:
    """Implements :class:`~moexcharts.domain.ports.CandleSource` against ISS."""

    def __init__(self, client: IssClient, settings: Settings):
        self._client = client
        self._settings = settings

    async def load(
        self,
        instrument: Instrument,
        interval: Interval,
        start: date | None,
        end: date,
    ) -> list[Candle]:
        params_base: dict[str, Any] = {"interval": interval.code, "iss.only": "candles"}
        windows = (
            chunk_range(start, end, _CHUNK_DAYS) if start is not None else [(None, end)]
        )
        rows: list[dict[str, Any]] = []
        budget = self._settings.max_candles + 1
        for window_start, window_end in windows:
            params = dict(params_base)
            if window_start is not None:
                params["from"] = window_start.isoformat()
            params["till"] = window_end.isoformat()
            rows.extend(
                await self._client.paginate_rows(
                    instrument.candles_path,
                    "candles",
                    params,
                    max_rows=budget - len(rows),
                )
            )
            if len(rows) >= budget:
                break

        candles = [c for c in (row_to_candle(row) for row in rows) if c is not None]
        # ISS returns ascending order, but de-duplicate defensively: chunk
        # boundaries and pagination retries can overlap.
        unique: dict[datetime, Candle] = {c.begin: c for c in candles}
        return [unique[key] for key in sorted(unique)]
