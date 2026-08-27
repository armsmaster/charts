"""Maps domain errors onto HTTP status codes in one place."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ..charting.watermark import InvalidImageError
from ..domain.models import (
    CsvFormatError,
    DomainError,
    EmptySeriesError,
    InstrumentNotFoundError,
    SeriesTooLargeError,
    UnknownIntervalError,
    UnknownPeriodError,
    UpstreamError,
)

_STATUS_BY_ERROR: tuple[tuple[type[DomainError], int], ...] = (
    (InstrumentNotFoundError, 404),
    (EmptySeriesError, 404),
    (UnknownIntervalError, 422),
    (UnknownPeriodError, 422),
    (SeriesTooLargeError, 422),
    (CsvFormatError, 422),
    (InvalidImageError, 422),
    (UpstreamError, 502),
)


def _status_for(error: DomainError) -> int:
    for error_type, status in _STATUS_BY_ERROR:
        if isinstance(error, error_type):
            return status
    return 400


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _handle_domain_error(_: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=_status_for(exc),
            content={"detail": str(exc), "error": type(exc).__name__},
        )
