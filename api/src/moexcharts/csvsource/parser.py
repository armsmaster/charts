"""CSV import.

Required columns: ``open``, ``high``, ``low``, ``close``, ``begin``.
Everything else (``value``, ``volume``, ``end``, ...) is optional and ignored.

Tolerant on purpose, because these files arrive from Excel, from the ISS web
export and from analysts' own scripts: UTF-8 BOM, ``,`` / ``;`` / tab
delimiters, decimal comma, thousands separators, arbitrary column order and
either ascending or descending row order.
"""

from __future__ import annotations

import csv
import io
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Sequence

from dateutil import parser as date_parser

from ..domain.models import Candle, CsvFormatError

REQUIRED_COLUMNS = ("open", "high", "low", "close", "begin")
OPTIONAL_COLUMNS = ("volume", "value")

_DATE_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
    "%d.%m.%Y %H:%M:%S",
    "%d.%m.%Y %H:%M",
    "%d.%m.%Y",
    "%m/%d/%Y %H:%M:%S",
    "%m/%d/%Y %H:%M",
    "%m/%d/%Y",
)


@dataclass(frozen=True, slots=True)
class ParsedCsv:
    candles: tuple[Candle, ...]
    #: Median spacing between candles, in seconds. ``None`` for a single row.
    inferred_interval_seconds: int | None
    #: Rows that could not be parsed and were skipped.
    skipped_rows: int
    columns: tuple[str, ...]


def _decode(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise CsvFormatError("Could not decode the file. Save it as UTF-8 or Windows-1251.")


def _sniff_delimiter(sample: str) -> str:
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        header = sample.splitlines()[0] if sample.splitlines() else ""
        counts = {d: header.count(d) for d in ",;\t|"}
        best = max(counts, key=lambda d: counts[d])
        return best if counts[best] else ","


def _normalise_header(name: str) -> str:
    return name.strip().lstrip("﻿").strip('"').lower()


def _parse_number(raw: str | None) -> float | None:
    if raw is None:
        return None
    text = raw.strip().replace(" ", "").replace(" ", "")
    if not text:
        return None
    # "1 234,56" -> "1234.56"; "1,234.56" -> "1234.56"
    if "," in text and "." in text:
        text = text.replace(",", "") if text.rfind(".") > text.rfind(",") else text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def _parse_datetime(raw: str | None) -> datetime | None:
    if not raw:
        return None
    text = raw.strip().strip('"').replace("T", " ")
    if not text:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    try:
        return date_parser.parse(text, dayfirst=False)
    except (ValueError, OverflowError):
        return None


def _median_delta_seconds(moments: Sequence[datetime]) -> int | None:
    if len(moments) < 2:
        return None
    deltas = [
        int((b - a).total_seconds())
        for a, b in zip(moments, moments[1:])
        if (b - a).total_seconds() > 0
    ]
    if not deltas:
        return None
    # The mode is more robust than the median here: weekend and holiday gaps are
    # large but rare, while the true bar spacing is by far the most common value.
    return Counter(deltas).most_common(1)[0][0]


class CsvCandleParser:
    """Parses an uploaded OHLC file into domain candles."""

    def parse(self, raw: bytes) -> ParsedCsv:
        text = _decode(raw)
        if not text.strip():
            raise CsvFormatError("The file is empty.")
        reader = csv.DictReader(
            io.StringIO(text, newline=""), delimiter=_sniff_delimiter(text[:4096])
        )
        if not reader.fieldnames:
            raise CsvFormatError("The file has no header row.")

        header_map = {_normalise_header(name): name for name in reader.fieldnames if name}
        missing = [c for c in REQUIRED_COLUMNS if c not in header_map]
        if missing:
            raise CsvFormatError(
                "Missing required column(s): "
                + ", ".join(missing)
                + ". Expected at least: "
                + ", ".join(REQUIRED_COLUMNS)
                + f". Found: {', '.join(sorted(header_map)) or '(none)'}."
            )

        candles, skipped = self._read_rows(reader, header_map)
        if not candles:
            raise CsvFormatError(
                "No valid rows found: every row had an unparseable date or price."
            )
        candles.sort(key=lambda c: c.begin)
        deduped = list({c.begin: c for c in candles}.values())
        deduped.sort(key=lambda c: c.begin)
        return ParsedCsv(
            candles=tuple(deduped),
            inferred_interval_seconds=_median_delta_seconds([c.begin for c in deduped]),
            skipped_rows=skipped,
            columns=tuple(sorted(header_map)),
        )

    @staticmethod
    def _read_rows(
        rows: Iterable[dict[str, str | None]], header_map: dict[str, str]
    ) -> tuple[list[Candle], int]:
        out: list[Candle] = []
        skipped = 0
        for row in rows:
            begin = _parse_datetime(row.get(header_map["begin"]))
            prices = {
                key: _parse_number(row.get(header_map[key]))
                for key in ("open", "high", "low", "close")
            }
            if begin is None or any(v is None for v in prices.values()):
                skipped += 1
                continue
            extras = {
                key: _parse_number(row.get(header_map[key]))
                for key in OPTIONAL_COLUMNS
                if key in header_map
            }
            out.append(
                Candle(
                    begin=begin,
                    open=prices["open"],  # type: ignore[arg-type]
                    high=prices["high"],  # type: ignore[arg-type]
                    low=prices["low"],  # type: ignore[arg-type]
                    close=prices["close"],  # type: ignore[arg-type]
                    volume=extras.get("volume"),
                    value=extras.get("value"),
                )
            )
        return out, skipped
