"""Request/response models for the HTTP API.

Kept separate from the domain types so that wire-format concerns (JSON shape,
optional fields, examples) never leak into the domain.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..charting.style import ChartStyle
from ..domain.models import Candle, CandleSeries, Instrument, Interval, InstrumentSummary


class CandleOut(BaseModel):
    begin: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None
    value: float | None = None

    @classmethod
    def from_domain(cls, candle: Candle) -> "CandleOut":
        return cls(
            begin=candle.begin,
            open=candle.open,
            high=candle.high,
            low=candle.low,
            close=candle.close,
            volume=candle.volume,
            value=candle.value,
        )

    def to_domain(self) -> Candle:
        return Candle(
            begin=self.begin,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=self.volume,
            value=self.value,
        )


class SeriesPayload(BaseModel):
    """A candle series as it travels between the API and the browser.

    The browser holds it after loading and posts it back when re-rendering with
    changed design settings, so restyling never re-hits ISS.
    """

    model_config = ConfigDict(extra="ignore")

    source: str = "moex"
    ticker: str = ""
    name: str = ""
    interval_code: int | None = None
    interval_seconds: int | None = None
    interval_title: str = ""
    period_code: str = ""
    period_title: str = ""
    candles: list[CandleOut] = Field(default_factory=list)

    @classmethod
    def from_domain(cls, series: CandleSeries) -> "SeriesPayload":
        return cls(
            source=series.source,
            ticker=series.ticker,
            name=series.name,
            interval_code=series.interval.code if series.interval else None,
            interval_seconds=series.interval.seconds if series.interval else None,
            interval_title=series.interval.title if series.interval else "",
            period_code=series.period_code,
            period_title=series.period_title,
            candles=[CandleOut.from_domain(c) for c in series.candles],
        )

    def to_domain(self) -> CandleSeries:
        interval = (
            Interval(
                code=self.interval_code or 0,
                seconds=self.interval_seconds or 0,
                title=self.interval_title,
            )
            if self.interval_seconds
            else None
        )
        return CandleSeries(
            candles=tuple(c.to_domain() for c in self.candles),
            source=self.source,
            ticker=self.ticker,
            name=self.name,
            interval=interval,
            period_code=self.period_code,
            period_title=self.period_title,
        )


class InstrumentOut(BaseModel):
    secid: str
    shortname: str
    name: str
    engine: str
    market: str
    board: str
    board_title: str = ""
    type: str = ""
    currency: str = ""
    is_traded: bool = True

    @classmethod
    def from_domain(cls, instrument: Instrument) -> "InstrumentOut":
        return cls(**{k: getattr(instrument, k) for k in cls.model_fields})


class InstrumentSummaryOut(BaseModel):
    secid: str
    shortname: str
    name: str
    type: str = ""
    group: str = ""
    primary_board: str = ""
    is_traded: bool = True

    @classmethod
    def from_domain(cls, summary: InstrumentSummary) -> "InstrumentSummaryOut":
        return cls(**{k: getattr(summary, k) for k in cls.model_fields})


class IntervalOut(BaseModel):
    code: int
    seconds: int
    title: str

    @classmethod
    def from_domain(cls, interval: Interval) -> "IntervalOut":
        return cls(code=interval.code, seconds=interval.seconds, title=interval.title)


class PeriodOut(BaseModel):
    code: str
    title: str


class PlaceholderOut(BaseModel):
    key: str
    token: str
    label: str


class SeriesResponse(BaseModel):
    series: SeriesPayload
    suggested_title: str
    instrument: InstrumentOut | None = None
    warnings: list[str] = Field(default_factory=list)
    stats: dict[str, Any] = Field(default_factory=dict)


class ChartRequest(BaseModel):
    series: SeriesPayload
    style: ChartStyle = Field(default_factory=ChartStyle)


class TitleResponse(BaseModel):
    title: str
    context: dict[str, str]


class WatermarkResponse(BaseModel):
    data_uri: str
    bytes: int


class CapabilitiesResponse(BaseModel):
    server_png: bool
    server_png_error: str = ""
    max_candles: int
    required_csv_columns: list[str]
    optional_csv_columns: list[str]
