"""Application services: the use cases, expressed in terms of ports only.

Route handlers stay thin (parse -> call -> serialise) and these classes hold the
orchestration, so the same use cases could be driven from a CLI or a scheduled
job without touching HTTP code.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from .config import Settings
from .csvsource.parser import CsvCandleParser
from .domain.intervals import interval_from_seconds
from .domain.models import (
    CandleSeries,
    EmptySeriesError,
    Instrument,
    SeriesTooLargeError,
)
from .domain.periods import cutoff_for, estimate_candles, get_period, resolve_range
from .domain.ports import CandleSource, InstrumentDirectory, IntervalCatalog


@dataclass(frozen=True, slots=True)
class LoadedSeries:
    series: CandleSeries
    instrument: Instrument | None = None
    warnings: tuple[str, ...] = ()


class MoexSeriesService:
    """Use case: "give me candles for <ticker> over <period> at <timeframe>"."""

    def __init__(
        self,
        directory: InstrumentDirectory,
        intervals: IntervalCatalog,
        candles: CandleSource,
        settings: Settings,
    ):
        self._directory = directory
        self._intervals = intervals
        self._candles = candles
        self._settings = settings

    def _now(self) -> datetime:
        return datetime.now(ZoneInfo(self._settings.timezone)).replace(tzinfo=None)

    async def load(
        self, secid: str, interval_code: int, period_code: str, board: str | None = None
    ) -> LoadedSeries:
        instrument = await self._directory.resolve(secid, board)  # validates existence
        interval = await self._intervals.get_interval(interval_code)
        period = get_period(period_code)

        expected = estimate_candles(period, interval.seconds)
        if expected > self._settings.max_candles:
            raise SeriesTooLargeError(
                f"«{period.title}» на таймфрейме «{interval.title}» — это примерно "
                f"{expected:,} свечей (лимит {self._settings.max_candles:,}). "
                "Выберите больший таймфрейм или меньший период.".replace(",", " ")
            )

        start, end = resolve_range(period, self._now())
        candles = await self._candles.load(instrument, interval, start, end)
        if not candles:
            raise EmptySeriesError(
                f"MOEX не вернула свечей для {instrument.secid} "
                f"({instrument.board}) за выбранный период."
            )

        warnings: list[str] = []
        if len(candles) > self._settings.max_candles:
            candles = candles[-self._settings.max_candles :]
            warnings.append(
                f"Показаны последние {self._settings.max_candles} свечей из выборки."
            )

        return LoadedSeries(
            series=CandleSeries(
                candles=tuple(candles),
                source="moex",
                ticker=instrument.secid,
                name=instrument.shortname,
                interval=interval,
                period_code=period.code,
                period_title=period.title,
            ),
            instrument=instrument,
            warnings=tuple(warnings),
        )


class CsvSeriesService:
    """Use case: "here is a CSV export, chart the last <period> of it".

    The timeframe is not chosen but inferred from the spacing of the rows, and
    the period is anchored on the newest row rather than on today - so importing
    a historical file and picking "1 month" gives that file's final month.
    """

    def __init__(self, parser: CsvCandleParser, settings: Settings):
        self._parser = parser
        self._settings = settings

    def load(
        self, raw: bytes, period_code: str, ticker: str = "", name: str = ""
    ) -> LoadedSeries:
        parsed = self._parser.parse(raw)
        period = get_period(period_code)
        interval = interval_from_seconds(parsed.inferred_interval_seconds)

        candles = list(parsed.candles)
        cutoff = cutoff_for(period, candles[-1].begin)
        if cutoff is not None:
            trimmed = [c for c in candles if c.begin >= cutoff]
            if trimmed:
                candles = trimmed

        warnings: list[str] = []
        if parsed.skipped_rows:
            warnings.append(f"Пропущено строк с ошибками: {parsed.skipped_rows}.")
        if len(candles) > self._settings.max_candles:
            candles = candles[-self._settings.max_candles :]
            warnings.append(
                f"Показаны последние {self._settings.max_candles} свечей из файла."
            )
        if interval is None:
            warnings.append("Не удалось определить таймфрейм по файлу.")

        if not candles:
            raise EmptySeriesError("После фильтрации по периоду в файле не осталось строк.")

        return LoadedSeries(
            series=CandleSeries(
                candles=tuple(candles),
                source="csv",
                ticker=ticker.strip().upper(),
                name=name.strip(),
                interval=interval,
                period_code=period.code,
                period_title=period.title,
            ),
            warnings=tuple(warnings),
        )
