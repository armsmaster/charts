"""Figure building, PNG export, title suggestion and watermark upload."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from fastapi import APIRouter, File, HTTPException, Response, UploadFile

from ...charting.watermark import build_data_uri, default_watermark_png
from ..deps import FiguresDep, PngFiguresDep, RendererDep, SettingsDep
from ..schemas import ChartRequest, TitleResponse, WatermarkResponse

router = APIRouter(prefix="/charts", tags=["charts"])

_UNSAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")


#: Latin timeframe tokens, so the download name survives a Cyrillic interval
#: title being stripped by the filename sanitiser.
_TIMEFRAME_TOKENS: dict[int, str] = {
    60: "1min",
    600: "10min",
    3_600: "1h",
    86_400: "1d",
    604_800: "1w",
    2_678_400: "1mo",
    8_035_200: "1q",
}


def _timeframe_token(seconds: int | None) -> str:
    if not seconds:
        return ""
    return _TIMEFRAME_TOKENS.get(seconds) or f"{seconds}s"


def _filename(request: ChartRequest) -> str:
    parts = [
        request.series.ticker or request.series.source,
        _timeframe_token(request.series.interval_seconds),
        request.series.period_code,
        datetime.now().strftime("%Y%m%d-%H%M"),
    ]
    stem = "_".join(_UNSAFE_FILENAME.sub("-", p).strip("-") for p in parts if p)
    return f"{stem or 'chart'}.png"


@router.post("/figure")
async def build_figure(request: ChartRequest, figures: FiguresDep) -> dict[str, Any]:
    """Return the Plotly figure spec: the same one used for the PNG export."""
    series = request.series.to_domain()
    return figures.build_spec(series, request.style)


@router.post(
    "/png",
    responses={200: {"content": {"image/png": {}}, "description": "Rendered chart"}},
)
async def render_png(
    request: ChartRequest, figures: PngFiguresDep, renderer: RendererDep
) -> Response:
    if not renderer.available:
        raise HTTPException(
            status_code=503,
            detail="Server-side PNG export is unavailable in this container; "
            "use the browser-side download instead.",
        )
    spec = figures.build_spec(request.series.to_domain(), request.style)
    canvas = request.style.canvas
    png = renderer.to_png(spec, canvas.width, canvas.height, canvas.scale)
    return Response(
        content=png,
        media_type="image/png",
        headers={"Content-Disposition": f'attachment; filename="{_filename(request)}"'},
    )


@router.post("/title", response_model=TitleResponse)
async def build_title(request: ChartRequest) -> TitleResponse:
    """Render the title template against the series - the title suggestion."""
    from ...charting.titles import suggest_title, title_context

    series = request.series.to_domain()
    return TitleResponse(
        title=suggest_title(series, request.style.title.template),
        context=title_context(series),
    )


@router.post("/watermark", response_model=WatermarkResponse)
async def upload_watermark(
    settings: SettingsDep, file: UploadFile = File(description="Logo image")
) -> WatermarkResponse:
    """Normalise an uploaded logo into an inline data URI stored in the preset."""
    raw = await file.read()
    if len(raw) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Файл больше {settings.max_upload_bytes // (1024 * 1024)} МБ.",
        )
    data_uri = build_data_uri(raw, settings.watermark_max_px)
    return WatermarkResponse(data_uri=data_uri, bytes=len(data_uri))


@router.get(
    "/watermark/default.png",
    responses={200: {"content": {"image/png": {}}, "description": "Bundled logo"}},
)
async def default_watermark() -> Response:
    """The bundled logo, referenced by the browser-side figure spec."""
    png = default_watermark_png()
    if not png:
        raise HTTPException(status_code=404, detail="No bundled watermark is installed.")
    return Response(
        content=png,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )
