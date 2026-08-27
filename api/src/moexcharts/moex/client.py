"""Thin transport layer over the MOEX ISS REST API.

Knows about HTTP, TLS and the ISS "blocks" envelope. Knows nothing about
candles, instruments or charts - that is :mod:`.catalog` and :mod:`.candles`.
"""

from __future__ import annotations

import logging
import ssl
import warnings
from typing import Any, Iterator

import httpx

from ..config import Settings
from ..domain.models import UpstreamError

log = logging.getLogger(__name__)


def _build_ssl_context(settings: Settings) -> ssl.SSLContext | bool | str:
    if settings.moex_ca_bundle:
        return settings.moex_ca_bundle
    if settings.moex_verify_ssl:
        return True
    # Corporate TLS interception: verification is switched off on purpose.
    # Warn once at startup rather than on every request.
    warnings.filterwarnings("ignore", message="Unverified HTTPS request")
    log.warning(
        "TLS verification for %s is DISABLED (CHARTS_MOEX_VERIFY_SSL=false).",
        settings.moex_base_url,
    )
    return False


def iter_block_rows(payload: dict[str, Any], block: str) -> Iterator[dict[str, Any]]:
    """Yield an ISS block as dicts.

    ISS answers ``{"<block>": {"columns": [...], "data": [[...], ...]}}``. We
    zip by the declared column order instead of by position constants, so ISS
    adding a column does not silently shift our fields.
    """
    section = payload.get(block)
    if not section:
        return
    columns: list[str] = section.get("columns", [])
    for row in section.get("data", []):
        yield dict(zip(columns, row))


class IssClient:
    """Async ISS client. One instance per application, reused across requests."""

    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self._settings = settings
        self._client = httpx.AsyncClient(
            base_url=settings.moex_base_url.rstrip("/"),
            timeout=settings.moex_timeout_seconds,
            verify=_build_ssl_context(settings) if transport is None else True,
            transport=transport,
            headers={"User-Agent": "moex-charts/1.0"},
            follow_redirects=True,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        query: dict[str, Any] = {"iss.meta": "off"}
        query.update(params or {})
        try:
            response = await self._client.get(path, params=query)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            raise UpstreamError(
                f"MOEX ISS returned {exc.response.status_code} for {path}."
            ) from exc
        except httpx.HTTPError as exc:
            raise UpstreamError(f"MOEX ISS is unreachable: {exc}") from exc
        except ValueError as exc:  # malformed JSON
            raise UpstreamError(f"MOEX ISS returned a malformed response for {path}.") from exc

    async def get_rows(
        self, path: str, block: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        payload = await self.get(path, params)
        return list(iter_block_rows(payload, block))

    async def paginate_rows(
        self,
        path: str,
        block: str,
        params: dict[str, Any] | None = None,
        *,
        page_size: int | None = None,
        max_rows: int | None = None,
    ) -> list[dict[str, Any]]:
        """Follow ISS ``start`` pagination until the server runs out of rows."""
        page_size = page_size or self._settings.moex_page_size
        rows: list[dict[str, Any]] = []
        start = 0
        for _ in range(self._settings.moex_max_pages):
            page = await self.get_rows(path, block, {**(params or {}), "start": start})
            if not page:
                break
            rows.extend(page)
            if max_rows is not None and len(rows) >= max_rows:
                break
            if len(page) < page_size:
                break
            start += len(page)
        return rows
