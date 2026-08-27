from datetime import date

import httpx
import pytest

from moexcharts.config import Settings
from moexcharts.domain.models import (
    InstrumentNotFoundError,
    SeriesTooLargeError,
    UnknownIntervalError,
    UpstreamError,
)
from moexcharts.moex.candles import IssCandleSource, row_to_candle
from moexcharts.moex.catalog import FALLBACK_INTERVALS, IssInstrumentDirectory, IssIntervalCatalog
from moexcharts.moex.client import IssClient
from moexcharts.services import MoexSeriesService


@pytest.fixture
def iss(settings, transport) -> IssClient:
    return IssClient(settings, transport=transport)


class TestIntervalCatalog:
    async def test_intervals_come_from_iss_durations(self, iss):
        intervals = await IssIntervalCatalog(iss, 0).list_intervals()
        assert [i.code for i in intervals] == [1, 10, 60, 24, 7, 31, 4]  # sorted by duration
        assert intervals[2].title == "1 час"

    async def test_unknown_interval_is_rejected(self, iss):
        with pytest.raises(UnknownIntervalError):
            await IssIntervalCatalog(iss, 0).get_interval(99)

    async def test_falls_back_when_iss_is_unreachable(self, settings):
        def explode(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("no route to host")

        catalog = IssIntervalCatalog(IssClient(settings, transport=httpx.MockTransport(explode)), 0)
        assert await catalog.list_intervals() == sorted(FALLBACK_INTERVALS, key=lambda i: i.seconds)


class TestInstrumentDirectory:
    async def test_search_prefers_traded_and_prefix_matches(self, iss):
        hits = await IssInstrumentDirectory(iss).search("SBER")
        assert hits[0].secid == "SBER"
        assert hits[-1].is_traded is False

    async def test_resolve_picks_the_primary_traded_board(self, iss):
        instrument = await IssInstrumentDirectory(iss).resolve("sber")
        assert (instrument.secid, instrument.board) == ("SBER", "TQBR")
        assert (instrument.engine, instrument.market) == ("stock", "shares")
        assert instrument.shortname == "Сбербанк"

    async def test_resolve_honours_an_explicit_board(self, iss):
        instrument = await IssInstrumentDirectory(iss).resolve("SBER", board="smal")
        assert instrument.board == "SMAL"

    async def test_unknown_board_is_rejected(self, iss):
        with pytest.raises(InstrumentNotFoundError):
            await IssInstrumentDirectory(iss).resolve("SBER", board="ZZZZ")

    async def test_unknown_ticker_is_rejected(self, iss):
        with pytest.raises(InstrumentNotFoundError):
            await IssInstrumentDirectory(iss).resolve("NOPE")

    async def test_empty_ticker_is_rejected(self, iss):
        with pytest.raises(InstrumentNotFoundError):
            await IssInstrumentDirectory(iss).resolve("   ")


class TestClientErrors:
    async def test_http_errors_become_upstream_errors(self, iss):
        with pytest.raises(UpstreamError):
            await iss.get("/boom.json")

    async def test_connection_errors_become_upstream_errors(self, settings):
        def explode(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectTimeout("timed out")

        with pytest.raises(UpstreamError):
            await IssClient(settings, transport=httpx.MockTransport(explode)).get("/index.json")


class TestCandleMapping:
    def test_rows_are_mapped_by_column_name(self):
        candle = row_to_candle(
            {"open": "1", "close": "2", "high": "3", "low": "0.5",
             "value": "10", "volume": "7", "begin": "2026-03-01 00:00:00"}
        )
        assert (candle.open, candle.close, candle.high, candle.low) == (1.0, 2.0, 3.0, 0.5)
        assert candle.begin.isoformat() == "2026-03-01T00:00:00"

    @pytest.mark.parametrize(
        "row",
        [
            {"open": "1", "close": "2", "high": "3", "low": "1", "begin": None},
            {"open": None, "close": "2", "high": "3", "low": "1", "begin": "2026-03-01"},
            {"open": "n/a", "close": "2", "high": "3", "low": "1", "begin": "2026-03-01"},
        ],
    )
    def test_unusable_rows_are_dropped(self, row):
        assert row_to_candle(row) is None


class TestMoexSeriesService:
    def _service(self, iss, settings) -> MoexSeriesService:
        return MoexSeriesService(
            IssInstrumentDirectory(iss),
            IssIntervalCatalog(iss, 0),
            IssCandleSource(iss, settings),
            settings,
        )

    async def test_loads_and_labels_a_series(self, iss, settings):
        loaded = await self._service(iss, settings).load("SBER", 24, "1m")
        series = loaded.series
        assert loaded.instrument.board == "TQBR"
        assert series.ticker == "SBER" and series.name == "Сбербанк"
        assert series.interval.code == 24
        assert series.period_title == "1 месяц"
        assert [c.begin for c in series.candles] == sorted(c.begin for c in series.candles)

    async def test_absurd_combinations_are_refused_before_calling_iss(self, iss, settings):
        with pytest.raises(SeriesTooLargeError):
            await self._service(iss, settings).load("SBER", 1, "5y")

    async def test_unknown_ticker_propagates(self, iss, settings):
        with pytest.raises(InstrumentNotFoundError):
            await self._service(iss, settings).load("NOPE", 24, "1m")


class TestCandleSourcePaging:
    async def test_duplicate_timestamps_across_pages_are_collapsed(self, iss, settings):
        instrument = await IssInstrumentDirectory(iss).resolve("SBER")
        interval = await IssIntervalCatalog(iss, 0).get_interval(24)
        candles = await IssCandleSource(iss, settings).load(
            instrument, interval, date(2026, 3, 1), date(2026, 3, 31)
        )
        begins = [c.begin for c in candles]
        assert len(begins) == len(set(begins))
        assert begins == sorted(begins)
