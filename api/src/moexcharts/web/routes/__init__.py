from fastapi import APIRouter

from . import charts, instruments, meta, series, vendor

api_router = APIRouter()
api_router.include_router(meta.router)
api_router.include_router(instruments.router)
api_router.include_router(series.router)
api_router.include_router(charts.router)
api_router.include_router(vendor.router)

__all__ = ["api_router"]
