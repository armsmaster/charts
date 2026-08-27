"""Helpers for describing candle durations that did not come from ISS."""

from __future__ import annotations

from .models import Interval

_UNITS: tuple[tuple[int, str, str, str], ...] = (
    (86_400 * 30, "месяц", "месяца", "месяцев"),
    (86_400 * 7, "неделя", "недели", "недель"),
    (86_400, "день", "дня", "дней"),
    (3_600, "час", "часа", "часов"),
    (60, "минута", "минуты", "минут"),
    (1, "секунда", "секунды", "секунд"),
)


def _plural(count: int, one: str, few: str, many: str) -> str:
    if count % 100 in range(11, 15):
        return many
    last = count % 10
    if last == 1:
        return one
    if last in (2, 3, 4):
        return few
    return many


def humanize_seconds(seconds: int) -> str:
    """``3600 -> "1 час"``, ``600 -> "10 минут"``."""
    if seconds <= 0:
        return ""
    for unit_seconds, one, few, many in _UNITS:
        if seconds >= unit_seconds and seconds % unit_seconds == 0:
            count = seconds // unit_seconds
            return f"{count} {_plural(count, one, few, many)}"
    minutes = max(1, round(seconds / 60))
    return f"{minutes} {_plural(minutes, 'минута', 'минуты', 'минут')}"


#: Adjectival forms used in chart titles ("часовые свечи" reads better than
#: "1 час свечи"). Falls back to a generic phrasing for anything unlisted.
_CANDLE_ADJECTIVES: dict[int, str] = {
    60: "минутные",
    300: "5-минутные",
    600: "10-минутные",
    900: "15-минутные",
    1_800: "получасовые",
    3_600: "часовые",
    14_400: "4-часовые",
    86_400: "дневные",
    604_800: "недельные",
    2_678_400: "месячные",
    8_035_200: "квартальные",
}


def candles_phrase(seconds: int) -> str:
    """``3600 -> "часовые свечи"``."""
    if seconds <= 0:
        return ""
    adjective = _CANDLE_ADJECTIVES.get(seconds)
    if adjective:
        return f"{adjective} свечи"
    return f"свечи по {humanize_seconds(seconds)}"


def interval_from_seconds(seconds: int | None) -> Interval | None:
    """Synthesise an interval for data whose timeframe was inferred, not chosen.

    ``code`` is 0 to mark it as "not an ISS interval".
    """
    if not seconds or seconds <= 0:
        return None
    return Interval(code=0, seconds=seconds, title=humanize_seconds(seconds))
