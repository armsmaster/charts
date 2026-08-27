"""Core domain types.

Deliberately free of HTTP, Plotly, CSV and pydantic concerns: everything else in
the codebase depends on these, and they depend on nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Candle:
    begin: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None
    value: float | None = None


@dataclass(frozen=True, slots=True)
class Interval:
    """A MOEX ISS candle duration (``interval`` query parameter)."""

    code: int
    seconds: int
    title: str

    @property
    def is_intraday(self) -> bool:
        return self.seconds < 24 * 3600


@dataclass(frozen=True, slots=True)
class Instrument:
    """A security resolved against ISS, pinned to a concrete trading board."""

    secid: str
    shortname: str
    name: str
    engine: str
    market: str
    board: str
    board_title: str = ""
    type: str = ""
    group: str = ""
    currency: str = ""
    is_traded: bool = True

    @property
    def candles_path(self) -> str:
        return (
            f"/engines/{self.engine}/markets/{self.market}"
            f"/boards/{self.board}/securities/{self.secid}/candles.json"
        )


@dataclass(frozen=True, slots=True)
class InstrumentSummary:
    """A search hit. Not yet resolved to a board - cheap to produce in bulk."""

    secid: str
    shortname: str
    name: str
    type: str = ""
    group: str = ""
    primary_board: str = ""
    is_traded: bool = True


@dataclass(frozen=True, slots=True)
class CandleSeries:
    """Candles plus enough context to title and format a chart."""

    candles: tuple[Candle, ...]
    source: str  # "moex" | "csv"
    ticker: str = ""
    name: str = ""
    interval: Interval | None = None
    period_code: str = ""
    period_title: str = ""

    def __post_init__(self) -> None:
        if not self.candles:
            raise EmptySeriesError("No candles for the requested instrument and period.")

    @property
    def begin(self) -> datetime:
        return self.candles[0].begin

    @property
    def end(self) -> datetime:
        return self.candles[-1].begin

    @property
    def last_close(self) -> float:
        return self.candles[-1].close


class DomainError(Exception):
    """Base class for errors that map to a 4xx response."""


class InstrumentNotFoundError(DomainError):
    pass


class UnknownIntervalError(DomainError):
    pass


class UnknownPeriodError(DomainError):
    pass


class EmptySeriesError(DomainError):
    pass


class SeriesTooLargeError(DomainError):
    pass


class CsvFormatError(DomainError):
    pass


class UpstreamError(DomainError):
    """ISS is unreachable or answered with an error."""
