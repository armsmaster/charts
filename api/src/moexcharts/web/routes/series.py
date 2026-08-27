"""Loading candle data - from MOEX ISS or from an uploaded CSV."""

from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile

from ...charting.style import TitleStyle
from ...charting.titles import suggest_title
from ...services import LoadedSeries
from ..deps import CsvSeriesDep, MoexSeriesDep, SettingsDep
from ..schemas import InstrumentOut, SeriesPayload, SeriesResponse

router = APIRouter(prefix="/series", tags=["series"])


def _to_response(loaded: LoadedSeries) -> SeriesResponse:
    series = loaded.series
    return SeriesResponse(
        series=SeriesPayload.from_domain(series),
        suggested_title=suggest_title(series, TitleStyle().template),
        instrument=InstrumentOut.from_domain(loaded.instrument) if loaded.instrument else None,
        warnings=list(loaded.warnings),
        stats={
            "count": len(series.candles),
            "from": series.begin.isoformat(),
            "till": series.end.isoformat(),
            "last_close": series.last_close,
        },
    )


@router.get("/moex", response_model=SeriesResponse)
async def load_moex(
    service: MoexSeriesDep,
    secid: str = Query(min_length=1, description="MOEX ticker, e.g. SBER or IMOEX"),
    interval: int = Query(description="ISS interval code, see /api/meta/intervals"),
    period: str = Query("3m", description="Period code, see /api/meta/periods"),
    board: str | None = Query(None, description="Override the auto-picked trading board"),
) -> SeriesResponse:
    return _to_response(await service.load(secid, interval, period, board))


@router.post("/csv", response_model=SeriesResponse)
async def load_csv(
    service: CsvSeriesDep,
    settings: SettingsDep,
    file: UploadFile = File(description="CSV with open, high, low, close, begin"),
    period: str = Form("full"),
    ticker: str = Form(""),
    name: str = Form(""),
) -> SeriesResponse:
    raw = await file.read()
    if len(raw) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Файл больше {settings.max_upload_bytes // (1024 * 1024)} МБ.",
        )
    return _to_response(service.load(raw, period, ticker, name))
