"""Composition root wiring and FastAPI dependency providers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

import httpx
from fastapi import Depends, Request

from ..charting.figure import FigureBuilder
from ..charting.watermark import default_watermark_data_uri, default_watermark_url
from ..charting.png import KaleidoPngRenderer
from ..config import Settings, get_settings
from ..csvsource.parser import CsvCandleParser
from ..domain.ports import ImageRenderer, InstrumentDirectory, IntervalCatalog
from ..moex.candles import IssCandleSource
from ..moex.catalog import IssInstrumentDirectory, IssIntervalCatalog
from ..moex.client import IssClient
from ..services import CsvSeriesService, MoexSeriesService


@dataclass
class Container:
    """Every collaborator built once per process and shared by the routes."""

    settings: Settings
    client: IssClient
    directory: IssInstrumentDirectory
    intervals: IssIntervalCatalog
    moex_series: MoexSeriesService
    csv_series: CsvSeriesService
    #: Emits a same-origin URL for the bundled logo - small JSON for the browser.
    figures: FigureBuilder
    #: Inlines the logo as a data URI - Kaleido cannot fetch anything.
    png_figures: FigureBuilder
    renderer: KaleidoPngRenderer

    @classmethod
    def build(
        cls, settings: Settings, transport: httpx.AsyncBaseTransport | None = None
    ) -> "Container":
        client = IssClient(settings, transport=transport)
        directory = IssInstrumentDirectory(client)
        intervals = IssIntervalCatalog(client, settings.intervals_cache_seconds)
        candles = IssCandleSource(client, settings)
        return cls(
            settings=settings,
            client=client,
            directory=directory,
            intervals=intervals,
            moex_series=MoexSeriesService(directory, intervals, candles, settings),
            csv_series=CsvSeriesService(CsvCandleParser(), settings),
            figures=FigureBuilder(default_watermark=default_watermark_url),
            png_figures=FigureBuilder(default_watermark=default_watermark_data_uri),
            renderer=KaleidoPngRenderer(),
        )

    async def aclose(self) -> None:
        await self.client.aclose()


def get_container(request: Request) -> Container:
    return request.app.state.container


ContainerDep = Annotated[Container, Depends(get_container)]


def get_directory(container: ContainerDep) -> InstrumentDirectory:
    return container.directory


def get_intervals(container: ContainerDep) -> IntervalCatalog:
    return container.intervals


def get_moex_series(container: ContainerDep) -> MoexSeriesService:
    return container.moex_series


def get_csv_series(container: ContainerDep) -> CsvSeriesService:
    return container.csv_series


def get_figures(container: ContainerDep) -> FigureBuilder:
    return container.figures


def get_png_figures(container: ContainerDep) -> FigureBuilder:
    return container.png_figures


def get_renderer(container: ContainerDep) -> ImageRenderer:
    return container.renderer


def get_app_settings(container: ContainerDep) -> Settings:
    return container.settings


DirectoryDep = Annotated[InstrumentDirectory, Depends(get_directory)]
IntervalsDep = Annotated[IntervalCatalog, Depends(get_intervals)]
MoexSeriesDep = Annotated[MoexSeriesService, Depends(get_moex_series)]
CsvSeriesDep = Annotated[CsvSeriesService, Depends(get_csv_series)]
FiguresDep = Annotated[FigureBuilder, Depends(get_figures)]
PngFiguresDep = Annotated[FigureBuilder, Depends(get_png_figures)]
RendererDep = Annotated[ImageRenderer, Depends(get_renderer)]
SettingsDep = Annotated[Settings, Depends(get_app_settings)]

__all__ = [
    "Container",
    "ContainerDep",
    "CsvSeriesDep",
    "DirectoryDep",
    "FiguresDep",
    "IntervalsDep",
    "MoexSeriesDep",
    "PngFiguresDep",
    "RendererDep",
    "SettingsDep",
    "get_settings",
]
