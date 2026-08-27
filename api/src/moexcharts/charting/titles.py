"""Chart title suggestion."""

from __future__ import annotations

from dataclasses import dataclass
from string import Formatter

from ..domain.intervals import candles_phrase
from ..domain.models import CandleSeries

_DATE_FMT = "%d.%m.%Y"


@dataclass(frozen=True, slots=True)
class Placeholder:
    """A template token offered as a one-click chip in the title editor."""

    key: str
    label: str

    @property
    def token(self) -> str:
        return "{" + self.key + "}"


#: Offered in the UI, in the order they appear there. Every key must exist in
#: :func:`title_context` - a test enforces that.
PLACEHOLDERS: tuple[Placeholder, ...] = (
    Placeholder("ticker", "тикер"),
    Placeholder("name", "название"),
    Placeholder("candles", "тип свечей"),
    Placeholder("interval_title", "таймфрейм"),
    Placeholder("period_title", "период"),
    Placeholder("from", "дата начала"),
    Placeholder("till", "дата конца"),
    Placeholder("last_close", "последняя цена"),
    Placeholder("count", "число свечей"),
)


class _SafeFormatter(Formatter):
    """Leaves unknown placeholders untouched instead of raising."""

    def get_value(self, key, args, kwargs):  # type: ignore[override]
        if isinstance(key, str):
            return kwargs.get(key, "{" + key + "}")
        return super().get_value(key, args, kwargs)


_FORMATTER = _SafeFormatter()


def title_context(series: CandleSeries) -> dict[str, str]:
    """Placeholders available in a title template."""
    interval = series.interval
    return {
        "ticker": series.ticker,
        "name": series.name,
        "shortname": series.name,
        "interval": str(interval.code) if interval else "",
        "interval_title": interval.title if interval else "",
        "candles": candles_phrase(interval.seconds) if interval else "",
        "period": series.period_code,
        "period_title": series.period_title,
        "from": series.begin.strftime(_DATE_FMT),
        "till": series.end.strftime(_DATE_FMT),
        "last_close": f"{series.last_close:,.2f}".replace(",", " "),
        "count": str(len(series.candles)),
    }


def suggest_title(series: CandleSeries, template: str) -> str:
    """Render *template* against *series*, collapsing gaps left by empty fields.

    Empty placeholders (e.g. no ticker for a CSV import) would otherwise leave
    dangling separators like ``"<b></b> | "``.
    """
    rendered = _FORMATTER.vformat(template, (), title_context(series))
    parts = [part.strip() for part in rendered.split("|")]
    kept = [p for p in parts if _has_text(p)]
    return " | ".join(kept).strip(" |·,-")


def _has_text(fragment: str) -> bool:
    """True if the fragment contains anything other than markup and separators."""
    stripped = fragment
    for tag in ("<b>", "</b>", "<i>", "</i>", "<span>", "</span>", "<br>"):
        stripped = stripped.replace(tag, "")
    return bool(stripped.strip(" ·,-—"))
