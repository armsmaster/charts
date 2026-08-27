"""Relative period presets ("last 3 months") and their resolution to dates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from dateutil.relativedelta import relativedelta

from .models import UnknownPeriodError

FULL = "full"  # CSV only: keep every row in the file


@dataclass(frozen=True, slots=True)
class Period:
    code: str
    title: str
    #: ``None`` means "everything available" (no lower bound).
    delta: relativedelta | None
    #: Approximate length in seconds, used only to pre-flight candle counts.
    approx_seconds: int

    def start_for(self, anchor: date) -> date | None:
        if self.delta is None:
            return None
        if self.code == "ytd":
            return date(anchor.year, 1, 1)
        return anchor - self.delta


def _p(code: str, title: str, delta: relativedelta | None, days: float) -> Period:
    return Period(code=code, title=title, delta=delta, approx_seconds=int(days * 86400))


#: Ordered as they should appear in the UI.
PERIODS: tuple[Period, ...] = (
    _p("1d", "1 день", relativedelta(days=1), 1),
    _p("3d", "3 дня", relativedelta(days=3), 3),
    _p("1w", "1 неделя", relativedelta(weeks=1), 7),
    _p("2w", "2 недели", relativedelta(weeks=2), 14),
    _p("1m", "1 месяц", relativedelta(months=1), 31),
    _p("3m", "3 месяца", relativedelta(months=3), 92),
    _p("6m", "6 месяцев", relativedelta(months=6), 183),
    _p("ytd", "с начала года", relativedelta(years=1), 366),
    _p("1y", "1 год", relativedelta(years=1), 366),
    _p("2y", "2 года", relativedelta(years=2), 731),
    _p("3y", "3 года", relativedelta(years=3), 1096),
    _p("5y", "5 лет", relativedelta(years=5), 1827),
    _p("max", "весь период", None, 365 * 30),
    _p(FULL, "весь файл", None, 365 * 30),
)

_BY_CODE = {p.code: p for p in PERIODS}


def get_period(code: str) -> Period:
    try:
        return _BY_CODE[code]
    except KeyError:
        raise UnknownPeriodError(
            f"Unknown period {code!r}. Known: {', '.join(_BY_CODE)}."
        ) from None


def selectable_periods(*, for_csv: bool) -> tuple[Period, ...]:
    """``full`` only makes sense for an imported file; ``max`` only for ISS."""
    skip = "max" if for_csv else FULL
    return tuple(p for p in PERIODS if p.code != skip)


def resolve_range(period: Period, anchor: datetime) -> tuple[date | None, date]:
    """Return ``(from, till)`` dates for an ISS query anchored at *anchor*."""
    till = anchor.date()
    return period.start_for(till), till


def cutoff_for(period: Period, anchor: datetime) -> datetime | None:
    """Lower bound used when trimming an imported CSV.

    Anchored on the newest row of the file rather than on "today", so importing
    a historical export and asking for "1 month" yields the file's last month.
    """
    if period.delta is None:
        return None
    if period.code == "ytd":
        return anchor.replace(
            month=1, day=1, hour=0, minute=0, second=0, microsecond=0
        )
    return anchor - period.delta


def estimate_candles(period: Period, interval_seconds: int) -> int:
    """Rough upper bound on the number of candles a request would return.

    Intentionally generous: it exists to catch "1 minute over 5 years", not to
    be accurate. Trading calendars are ignored, which biases it upwards.
    """
    if interval_seconds <= 0:
        return 0
    return max(1, int(period.approx_seconds / interval_seconds))


def chunk_range(start: date, end: date, max_days: int) -> list[tuple[date, date]]:
    """Split ``[start, end]`` into consecutive windows of at most *max_days*."""
    if max_days <= 0 or (end - start).days <= max_days:
        return [(start, end)]
    out: list[tuple[date, date]] = []
    cursor = start
    while cursor <= end:
        stop = min(cursor + timedelta(days=max_days), end)
        out.append((cursor, stop))
        cursor = stop + timedelta(days=1)
    return out
