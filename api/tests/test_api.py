"""HTTP-level tests: status codes, contracts and the full load -> render flow."""

from __future__ import annotations


class TestMeta:
    def test_health(self, client):
        assert client.get("/api/health").json() == {"status": "ok"}

    def test_intervals_are_served_from_iss(self, client):
        body = client.get("/api/meta/intervals").json()
        assert {i["code"] for i in body} == {1, 10, 60, 24, 7, 31, 4}

    def test_period_options_depend_on_the_source(self, client):
        moex = {p["code"] for p in client.get("/api/meta/periods").json()}
        csv = {p["code"] for p in client.get("/api/meta/periods", params={"source": "csv"}).json()}
        assert "max" in moex and "full" in csv

    def test_style_schema_and_defaults_agree(self, client):
        schema = client.get("/api/meta/style-schema").json()
        defaults = client.get("/api/meta/style-defaults").json()
        assert {s["key"] for s in schema} == set(defaults)

    def test_title_placeholders_are_published_for_the_editor(self, client):
        body = client.get("/api/meta/title-placeholders").json()
        keys = {p["key"] for p in body}
        assert {"ticker", "candles", "period_title"} <= keys
        assert all(p["token"] == "{" + p["key"] + "}" and p["label"] for p in body)

    def test_capabilities_describe_the_csv_contract(self, client):
        body = client.get("/api/meta/capabilities").json()
        assert body["required_csv_columns"] == ["open", "high", "low", "close", "begin"]
        assert isinstance(body["server_png"], bool)


class TestInstruments:
    def test_search(self, client):
        body = client.get("/api/instruments/search", params={"q": "SBER"}).json()
        assert body[0]["secid"] == "SBER"

    def test_search_requires_a_query(self, client):
        assert client.get("/api/instruments/search", params={"q": ""}).status_code == 422

    def test_valid_ticker_resolves_to_a_board(self, client):
        body = client.get("/api/instruments/SBER").json()
        assert (body["board"], body["engine"], body["market"]) == ("TQBR", "stock", "shares")

    def test_invalid_ticker_is_a_404(self, client):
        response = client.get("/api/instruments/NOPE")
        assert response.status_code == 404
        assert "NOPE" in response.json()["detail"]

    def test_boards_are_listed(self, client):
        boards = client.get("/api/instruments/SBER/boards").json()
        assert {b["board"] for b in boards} == {"TQBR", "SMAL", "EQBR"}


class TestSeries:
    def test_moex_series_carries_a_suggested_title(self, client):
        body = client.get(
            "/api/series/moex", params={"secid": "SBER", "interval": 24, "period": "1m"}
        ).json()
        assert body["series"]["ticker"] == "SBER"
        assert body["suggested_title"] == "<b>SBER</b> | дневные свечи"
        assert body["stats"]["count"] == len(body["series"]["candles"])

    def test_unknown_ticker_is_a_404(self, client):
        response = client.get(
            "/api/series/moex", params={"secid": "NOPE", "interval": 24, "period": "1m"}
        )
        assert response.status_code == 404

    def test_unknown_interval_is_a_422(self, client):
        response = client.get(
            "/api/series/moex", params={"secid": "SBER", "interval": 999, "period": "1m"}
        )
        assert response.status_code == 422

    def test_absurd_range_is_a_422_with_advice(self, client):
        response = client.get(
            "/api/series/moex", params={"secid": "SBER", "interval": 1, "period": "5y"}
        )
        assert response.status_code == 422
        assert "таймфрейм" in response.json()["detail"]

    def test_csv_upload(self, client, sample_csv):
        response = client.post(
            "/api/series/csv",
            files={"file": ("data.csv", sample_csv, "text/csv")},
            data={"period": "full", "ticker": "imoex", "name": "Индекс МосБиржи"},
        )
        body = response.json()
        assert response.status_code == 200
        assert body["series"]["source"] == "csv"
        assert body["series"]["ticker"] == "IMOEX"
        assert body["series"]["interval_seconds"] == 3600
        assert body["instrument"] is None

    def test_csv_without_required_columns_is_a_422(self, client):
        response = client.post(
            "/api/series/csv",
            files={"file": ("bad.csv", b"a,b\n1,2\n", "text/csv")},
            data={"period": "full"},
        )
        assert response.status_code == 422
        assert "close" in response.json()["detail"]


class TestCharts:
    def _series(self, client):
        return client.get(
            "/api/series/moex", params={"secid": "SBER", "interval": 24, "period": "1m"}
        ).json()["series"]

    def test_figure_is_a_usable_plotly_spec(self, client):
        figure = client.post(
            "/api/charts/figure", json={"series": self._series(client), "style": {}}
        ).json()
        assert figure["data"][0]["type"] == "candlestick"
        assert figure["layout"]["title"]["text"] == "<b>SBER</b> | дневные свечи"

    def test_style_overrides_are_applied(self, client):
        figure = client.post(
            "/api/charts/figure",
            json={
                "series": self._series(client),
                "style": {"candles": {"increasing_fillcolor": "#00ff00"}, "canvas": {"width": 640}},
            },
        ).json()
        assert figure["data"][0]["increasing"]["fillcolor"] == "#00ff00"
        assert figure["layout"]["width"] == 640

    def test_browser_figure_references_the_watermark_by_url(self, client):
        figure = client.post(
            "/api/charts/figure", json={"series": self._series(client), "style": {}}
        ).json()
        assert figure["layout"]["images"][0]["source"] == "/api/charts/watermark/default.png"

    def test_title_endpoint_returns_the_suggestion_and_its_context(self, client):
        body = client.post(
            "/api/charts/title",
            json={
                "series": self._series(client),
                "style": {"title": {"template": "{ticker} за {period_title}"}},
            },
        ).json()
        assert body["title"] == "SBER за 1 месяц"
        assert body["context"]["ticker"] == "SBER"

    def test_default_watermark_is_served_as_png(self, client):
        response = client.get("/api/charts/watermark/default.png")
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"
        assert response.content[:4] == b"\x89PNG"

    def test_watermark_upload_returns_a_data_uri(self, client):
        import io

        from PIL import Image

        buffer = io.BytesIO()
        Image.new("RGBA", (300, 300), (255, 0, 0, 255)).save(buffer, format="PNG")
        response = client.post(
            "/api/charts/watermark",
            files={"file": ("logo.png", buffer.getvalue(), "image/png")},
        )
        assert response.status_code == 200
        assert response.json()["data_uri"].startswith("data:image/png;base64,")

    def test_watermark_upload_rejects_non_images(self, client):
        response = client.post(
            "/api/charts/watermark", files={"file": ("x.txt", b"not an image", "text/plain")}
        )
        assert response.status_code == 422

    def test_png_export(self, client):
        response = client.post(
            "/api/charts/png",
            json={"series": self._series(client), "style": {"canvas": {"width": 500, "height": 320, "scale": 1}}},
        )
        # Kaleido may be absent in a trimmed container: 503 tells the UI to
        # fall back to browser-side export instead of failing the flow.
        assert response.status_code in (200, 503)
        if response.status_code == 200:
            assert response.content[:4] == b"\x89PNG"
            disposition = response.headers["content-disposition"]
            assert "SBER" in disposition and "_1d_1m_" in disposition
            assert disposition.isascii()

    def test_vendored_plotly_is_served(self, client):
        response = client.get("/api/vendor/plotly.min.js")
        assert response.status_code == 200
        assert "plotly" in response.text[:2000].lower()
