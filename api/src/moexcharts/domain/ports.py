"""Ports (interfaces) the HTTP layer depends on.

The route handlers are typed against these Protocols, never against the MOEX or
Plotly implementations, so a different exchange or renderer can be dropped in
without touching the HTTP layer. Each port is deliberately narrow.
"""

from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable

from .models import Candle, Instrument, Interval, InstrumentSummary


@runtime_checkable
class IntervalCatalog(Protocol):
    """Where the list of selectable timeframes comes from."""

    async def list_intervals(self) -> list[Interval]: ...

    async def get_interval(self, code: int) -> Interval: ...


@runtime_checkable
class InstrumentDirectory(Protocol):
    """Instrument lookup and existence validation."""

    async def search(self, query: str, limit: int) -> list[InstrumentSummary]: ...

    async def resolve(self, secid: str, board: str | None = None) -> Instrument: ...


@runtime_checkable
class CandleSource(Protocol):
    """Historical OHLC for a resolved instrument."""

    async def load(
        self,
        instrument: Instrument,
        interval: Interval,
        start: date | None,
        end: date,
    ) -> list[Candle]: ...


@runtime_checkable
class ImageRenderer(Protocol):
    """Turns a Plotly figure dict into raster bytes."""

    @property
    def available(self) -> bool: ...

    def to_png(self, figure: dict, width: int, height: int, scale: float) -> bytes: ...
