"""Options and capabilities the UI builds itself from."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ...charting.style import ChartStyle, ui_schema
from ...charting.titles import PLACEHOLDERS
from ...csvsource.parser import OPTIONAL_COLUMNS, REQUIRED_COLUMNS
from ...domain.periods import selectable_periods
from ..deps import IntervalsDep, RendererDep, SettingsDep
from ..schemas import CapabilitiesResponse, IntervalOut, PeriodOut, PlaceholderOut

router = APIRouter(prefix="/meta", tags=["meta"])


@router.get("/intervals", response_model=list[IntervalOut])
async def list_intervals(intervals: IntervalsDep) -> list[IntervalOut]:
    """Timeframe options, sourced from iss.moex.com (`/iss/index.json` durations)."""
    return [IntervalOut.from_domain(i) for i in await intervals.list_intervals()]


@router.get("/periods", response_model=list[PeriodOut])
async def list_periods(source: str = "moex") -> list[PeriodOut]:
    return [
        PeriodOut(code=p.code, title=p.title)
        for p in selectable_periods(for_csv=source == "csv")
    ]


@router.get("/style-schema")
async def style_schema() -> list[dict[str, Any]]:
    """Field-by-field description of the design settings, for the settings panel."""
    return ui_schema()


@router.get("/title-placeholders", response_model=list[PlaceholderOut])
async def title_placeholders() -> list[PlaceholderOut]:
    """Tokens the title editor offers as one-click chips."""
    return [PlaceholderOut(key=p.key, token=p.token, label=p.label) for p in PLACEHOLDERS]


@router.get("/style-defaults", response_model=ChartStyle)
async def style_defaults() -> ChartStyle:
    return ChartStyle()


@router.get("/capabilities", response_model=CapabilitiesResponse)
async def capabilities(renderer: RendererDep, settings: SettingsDep) -> CapabilitiesResponse:
    return CapabilitiesResponse(
        server_png=renderer.available,
        server_png_error=getattr(renderer, "error", ""),
        max_candles=settings.max_candles,
        required_csv_columns=list(REQUIRED_COLUMNS),
        optional_csv_columns=list(OPTIONAL_COLUMNS),
    )
