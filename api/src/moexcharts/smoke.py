"""Connectivity check: ``python -m moexcharts.smoke [TICKER]``.

Run it inside the api container after deploying to confirm that iss.moex.com is
reachable with the current proxy and TLS settings, before blaming the UI.
"""

from __future__ import annotations

import asyncio
import sys

from .config import get_settings
from .domain.models import DomainError
from .moex.candles import IssCandleSource
from .moex.catalog import IssInstrumentDirectory, IssIntervalCatalog
from .moex.client import IssClient
from .services import MoexSeriesService


async def _run(secid: str) -> int:
    settings = get_settings()
    print(f"ISS base URL     : {settings.moex_base_url}")
    print(f"TLS verification : {settings.httpx_verify}")

    client = IssClient(settings)
    try:
        intervals = IssIntervalCatalog(client, cache_seconds=0)
        available = await intervals.list_intervals()
        print(f"Intervals        : {', '.join(f'{i.code}={i.title}' for i in available)}")

        directory = IssInstrumentDirectory(client)
        service = MoexSeriesService(directory, intervals, IssCandleSource(client, settings), settings)
        loaded = await service.load(secid, 24, "1m")
        series = loaded.series
        print(f"Instrument       : {series.ticker} — {series.name}")
        print(f"Candles          : {len(series.candles)} ({series.begin} .. {series.end})")
        print(f"Last close       : {series.last_close}")
        print("\nOK — MOEX ISS is reachable.")
        return 0
    except DomainError as exc:
        print(f"\nFAILED: {exc}", file=sys.stderr)
        return 1
    finally:
        await client.aclose()


def main() -> int:
    secid = sys.argv[1] if len(sys.argv) > 1 else "SBER"
    return asyncio.run(_run(secid))


if __name__ == "__main__":
    raise SystemExit(main())
