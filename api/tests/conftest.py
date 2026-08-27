"""Test fixtures.

Every test runs offline: a fake httpx transport answers ISS requests from
recorded-shape payloads, so the suite is deterministic and needs no network,
which also makes it runnable on the locked-down deployment host.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from moexcharts.config import Settings  # noqa: E402
from moexcharts.main import create_app  # noqa: E402

FIXTURES = Path(__file__).parent

DURATIONS = {
    "durations": {
        "columns": ["interval", "duration", "days", "title", "hint"],
        "data": [
            [1, 60, None, "1 минута", "1м"],
            [10, 600, None, "10 минут", "10м"],
            [60, 3600, None, "1 час", "1ч"],
            [24, 86400, 1, "1 день", "1д"],
            [7, 604800, 7, "1 неделя", "1н"],
            [31, 2678400, 31, "1 месяц", "1М"],
            [4, 8035200, 93, "1 квартал", "1К"],
        ],
    }
}

SECURITIES_SEARCH = {
    "securities": {
        "columns": ["secid", "shortname", "name", "type", "group", "primary_boardid", "is_traded"],
        "data": [
            ["SBER", "Сбербанк", "Сбербанк России ПАО ао", "common_share", "stock_shares", "TQBR", 1],
            ["SBERP", "Сбербанк-п", "Сбербанк России ПАО ап", "preferred_share", "stock_shares", "TQBR", 1],
            ["SBGB", "RUSFAITH", "Индекс Сбербанка", "index", "stock_index", "SNDX", 0],
        ],
    }
}

SBER_DESCRIPTION = {
    "description": {
        "columns": ["name", "title", "value", "type"],
        "data": [
            ["SECID", "Код", "SBER", "string"],
            ["NAME", "Полное наименование", "Сбербанк России ПАО ао", "string"],
            ["SHORTNAME", "Краткое наименование", "Сбербанк", "string"],
            ["TYPE", "Тип бумаги", "common_share", "string"],
            ["CURRENCYID", "Валюта", "SUR", "string"],
        ],
    },
    "boards": {
        "columns": [
            "secid", "boardid", "title", "board_group_id", "market_id", "market",
            "engine_id", "engine", "is_traded", "is_primary", "currencyid",
        ],
        "data": [
            ["SBER", "TQBR", "Т+ Акции и ДР", 57, 1, "shares", 1, "stock", 1, 1, "SUR"],
            ["SBER", "SMAL", "Т+ Неполные лоты", 267, 1, "shares", 1, "stock", 1, 0, "SUR"],
            ["SBER", "EQBR", "Основной режим", 7, 1, "shares", 1, "stock", 0, 0, "SUR"],
        ],
    },
}


def _candles_page(start: int, total: int = 7) -> dict:
    columns = ["open", "close", "high", "low", "value", "volume", "begin", "end"]
    rows = []
    for index in range(start, min(start + 500, total)):
        day = 1 + index
        base = 100 + index
        rows.append(
            [
                base,
                base + 1,
                base + 2,
                base - 2,
                1000.0 * (index + 1),
                10 * (index + 1),
                f"2026-03-{day:02d} 00:00:00",
                f"2026-03-{day:02d} 23:59:59",
            ]
        )
    return {"candles": {"columns": columns, "data": rows}}


def _handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    query = parse_qs(request.url.query.decode())

    if path.endswith("/index.json"):
        return httpx.Response(200, json=DURATIONS)
    if path.endswith("/securities.json"):
        return httpx.Response(200, json=SECURITIES_SEARCH)
    if path.endswith("/securities/SBER.json"):
        return httpx.Response(200, json=SBER_DESCRIPTION)
    if path.endswith("/securities/NOPE.json"):
        return httpx.Response(200, json={"description": {"columns": [], "data": []},
                                         "boards": {"columns": [], "data": []}})
    if path.endswith("/candles.json"):
        return httpx.Response(200, json=_candles_page(int(query.get("start", ["0"])[0])))
    if path.endswith("/boom.json"):
        return httpx.Response(500, text="boom")
    return httpx.Response(404, json={})


@pytest.fixture
def settings() -> Settings:
    return Settings(moex_base_url="https://iss.example/iss", max_candles=1000)


@pytest.fixture
def transport() -> httpx.MockTransport:
    return httpx.MockTransport(_handler)


@pytest.fixture
def client(settings: Settings, transport: httpx.MockTransport):
    with TestClient(create_app(settings=settings, transport=transport)) as test_client:
        yield test_client


@pytest.fixture
def sample_csv() -> bytes:
    path = FIXTURES / "fixtures_data.csv"
    if path.exists():
        return path.read_bytes()
    header = "﻿open,close,high,low,value,volume,begin,end\n"
    rows = "".join(
        f"{100 + i},{101 + i},{102 + i},{98 + i},{1000 * i},0,"
        f"8/{10 + i}/2026 12:00,8/{10 + i}/2026 12:59\n"
        for i in range(10)
    )
    return (header + rows).encode("utf-8")


def json_of(response: httpx.Response) -> dict:
    return json.loads(response.content)
