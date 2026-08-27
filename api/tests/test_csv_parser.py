import pytest

from moexcharts.config import Settings
from moexcharts.csvsource.parser import CsvCandleParser
from moexcharts.domain.models import CsvFormatError, EmptySeriesError
from moexcharts.services import CsvSeriesService


@pytest.fixture
def parser() -> CsvCandleParser:
    return CsvCandleParser()


def test_parses_the_real_moex_export(parser, sample_csv):
    parsed = parser.parse(sample_csv)
    assert parsed.candles
    assert {"open", "high", "low", "close", "begin"} <= set(parsed.columns)
    # Rows must come out ascending even though the export is newest-first.
    begins = [c.begin for c in parsed.candles]
    assert begins == sorted(begins)


def test_infers_the_timeframe_from_row_spacing(parser, sample_csv):
    assert parser.parse(sample_csv).inferred_interval_seconds == 3600


def test_missing_required_column_names_what_is_missing(parser):
    with pytest.raises(CsvFormatError) as excinfo:
        parser.parse(b"open,high,low,begin\n1,2,3,2026-01-01\n")
    assert "close" in str(excinfo.value)


def test_accepts_semicolons_decimal_commas_and_cp1251(parser):
    raw = "open;high;low;close;begin\n1,5;2,5;0,5;2,0;01.02.2026 10:00\n".encode("cp1251")
    candle = parser.parse(raw).candles[0]
    assert (candle.open, candle.high, candle.low, candle.close) == (1.5, 2.5, 0.5, 2.0)
    assert candle.begin.day == 1 and candle.begin.month == 2


def test_column_order_and_case_do_not_matter(parser):
    raw = b"BEGIN,Close,LOW,High,Open\n2026-01-05,11,9,12,10\n"
    candle = parser.parse(raw).candles[0]
    assert (candle.open, candle.close) == (10.0, 11.0)


def test_unparseable_rows_are_counted_not_fatal(parser):
    raw = (
        b"open,high,low,close,begin\n"
        b"1,2,0,1,2026-01-01 10:00\n"
        b"x,y,z,w,nonsense\n"
        b"2,3,1,2,2026-01-01 11:00\n"
    )
    parsed = parser.parse(raw)
    assert len(parsed.candles) == 2
    assert parsed.skipped_rows == 1


def test_empty_and_headerless_files_are_rejected(parser):
    with pytest.raises(CsvFormatError):
        parser.parse(b"")
    with pytest.raises(CsvFormatError):
        parser.parse(b"1,2,3,4,5\n")


def test_duplicate_timestamps_are_collapsed(parser):
    raw = (
        b"open,high,low,close,begin\n"
        b"1,2,0,1,2026-01-01 10:00\n"
        b"9,9,9,9,2026-01-01 10:00\n"
    )
    assert len(parser.parse(raw).candles) == 1


class TestCsvSeriesService:
    @pytest.fixture
    def service(self):
        return CsvSeriesService(CsvCandleParser(), Settings(max_candles=1000))

    def test_period_trims_relative_to_the_last_row(self, service, sample_csv):
        full = service.load(sample_csv, "full").series
        month = service.load(sample_csv, "1m").series
        assert len(month.candles) < len(full.candles)
        assert month.end == full.end  # the newest candle is kept

    def test_interval_is_inferred_and_titled(self, service, sample_csv):
        series = service.load(sample_csv, "full", ticker="imoex").series
        assert series.interval.seconds == 3600
        assert series.interval.title == "1 час"
        assert series.ticker == "IMOEX"  # normalised

    def test_max_candles_is_enforced(self, sample_csv):
        service = CsvSeriesService(CsvCandleParser(), Settings(max_candles=50))
        loaded = service.load(sample_csv, "full")
        assert len(loaded.series.candles) == 50
        assert any("50" in w for w in loaded.warnings)

    def test_period_that_excludes_everything_falls_back_to_the_file(self, service, sample_csv):
        # A one-day window at the end of a historical file must not empty it out.
        series = service.load(sample_csv, "1d").series
        assert len(series.candles) >= 1

    def test_rejects_a_file_with_no_usable_rows(self, service):
        with pytest.raises((CsvFormatError, EmptySeriesError)):
            service.load(b"open,high,low,close,begin\n,,,,\n", "full")
