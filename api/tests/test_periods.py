from datetime import date, datetime

import pytest

from moexcharts.domain.intervals import candles_phrase, humanize_seconds, interval_from_seconds
from moexcharts.domain.models import UnknownPeriodError
from moexcharts.domain.periods import (
    chunk_range,
    cutoff_for,
    estimate_candles,
    get_period,
    resolve_range,
    selectable_periods,
)


def test_relative_periods_resolve_against_the_anchor():
    anchor = datetime(2026, 8, 27, 15, 0)
    start, till = resolve_range(get_period("3m"), anchor)
    assert (start, till) == (date(2026, 5, 27), date(2026, 8, 27))


def test_ytd_starts_on_the_first_of_january():
    start, _ = resolve_range(get_period("ytd"), datetime(2026, 8, 27))
    assert start == date(2026, 1, 1)


def test_max_has_no_lower_bound():
    start, till = resolve_range(get_period("max"), datetime(2026, 8, 27))
    assert start is None and till == date(2026, 8, 27)


def test_unknown_period_is_rejected():
    with pytest.raises(UnknownPeriodError):
        get_period("17y")


def test_csv_and_moex_offer_different_period_lists():
    moex = {p.code for p in selectable_periods(for_csv=False)}
    csv = {p.code for p in selectable_periods(for_csv=True)}
    assert "max" in moex and "full" not in moex
    assert "full" in csv and "max" not in csv


def test_csv_cutoff_is_anchored_on_the_last_candle_not_today():
    cutoff = cutoff_for(get_period("1m"), datetime(2020, 6, 15, 12, 0))
    assert cutoff == datetime(2020, 5, 15, 12, 0)


def test_full_period_keeps_every_row():
    assert cutoff_for(get_period("full"), datetime(2026, 1, 1)) is None


def test_estimate_flags_absurd_combinations():
    minute_over_five_years = estimate_candles(get_period("5y"), 60)
    hour_over_three_months = estimate_candles(get_period("3m"), 3600)
    assert minute_over_five_years > 2_000_000
    assert hour_over_three_months < 3_000


def test_long_ranges_are_split_into_windows():
    windows = chunk_range(date(2016, 1, 1), date(2026, 1, 1), max_days=365 * 3)
    assert len(windows) == 4
    assert windows[0][0] == date(2016, 1, 1)
    assert windows[-1][1] == date(2026, 1, 1)
    # windows must be contiguous and non-overlapping
    for (_, end), (next_start, _) in zip(windows, windows[1:]):
        assert (next_start - end).days == 1


@pytest.mark.parametrize(
    "seconds,expected",
    [(60, "1 минута"), (600, "10 минут"), (3600, "1 час"), (86400, "1 день"), (604800, "1 неделя")],
)
def test_humanize_seconds(seconds, expected):
    assert humanize_seconds(seconds) == expected


@pytest.mark.parametrize(
    "seconds,expected",
    [(3600, "часовые свечи"), (86400, "дневные свечи"), (600, "10-минутные свечи")],
)
def test_candles_phrase_reads_naturally(seconds, expected):
    assert candles_phrase(seconds) == expected


def test_interval_from_seconds_marks_synthetic_intervals():
    interval = interval_from_seconds(3600)
    assert interval.code == 0 and interval.seconds == 3600
    assert interval_from_seconds(None) is None
