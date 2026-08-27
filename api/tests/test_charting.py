from datetime import datetime, timedelta

import pytest

from moexcharts.charting.figure import FigureBuilder
from moexcharts.charting.style import ChartStyle, ui_schema
from moexcharts.charting.titles import PLACEHOLDERS, suggest_title, title_context
from moexcharts.charting.watermark import InvalidImageError, build_data_uri
from moexcharts.domain.models import Candle, CandleSeries, EmptySeriesError, Interval

HOUR = Interval(60, 3600, "1 час")
DAY = Interval(24, 86400, "1 день")


def make_series(count=40, interval=HOUR, **kwargs) -> CandleSeries:
    start = datetime(2026, 3, 2, 10, 0)
    candles = tuple(
        Candle(
            begin=start + timedelta(seconds=interval.seconds * i),
            open=100 + i,
            high=102 + i,
            low=98 + i,
            close=101 + i if i % 2 else 99 + i,
            volume=10 * (i + 1),
            value=1000.0 * (i + 1),
        )
        for i in range(count)
    )
    return CandleSeries(
        candles=candles,
        source=kwargs.pop("source", "moex"),
        ticker=kwargs.pop("ticker", "SBER"),
        name=kwargs.pop("name", "Сбербанк"),
        interval=interval,
        period_code=kwargs.pop("period_code", "1m"),
        period_title=kwargs.pop("period_title", "1 месяц"),
    )


class TestTitles:
    def test_default_template_matches_the_notebook_style(self):
        assert suggest_title(make_series(), "<b>{ticker}</b> | {candles}") == (
            "<b>SBER</b> | часовые свечи"
        )

    def test_every_placeholder_resolves(self):
        context = title_context(make_series())
        assert context["ticker"] == "SBER"
        assert context["period_title"] == "1 месяц"
        assert context["from"].count(".") == 2

    def test_empty_parts_do_not_leave_dangling_separators(self):
        series = make_series(ticker="", name="")
        assert suggest_title(series, "<b>{ticker}</b> | {candles}") == "часовые свечи"

    def test_unknown_placeholders_are_left_alone(self):
        assert "{nope}" in suggest_title(make_series(), "{nope}")

    def test_every_offered_placeholder_actually_resolves(self):
        # The UI builds its chips from PLACEHOLDERS; a chip that renders as
        # literal "{foo}" on the chart would be a silent trap.
        context = title_context(make_series())
        for placeholder in PLACEHOLDERS:
            assert placeholder.key in context, placeholder.key
            assert placeholder.token == "{" + placeholder.key + "}"
            assert placeholder.label

    def test_placeholder_labels_are_unique(self):
        labels = [p.label for p in PLACEHOLDERS]
        assert len(labels) == len(set(labels))


class TestFigureBuilder:
    @pytest.fixture
    def builder(self):
        return FigureBuilder(default_watermark=lambda: "/logo.png")

    def test_style_reaches_the_candlestick_trace(self, builder):
        style = ChartStyle()
        spec = builder.build_spec(make_series(), style)
        trace = spec["data"][0]
        assert trace["type"] == "candlestick"
        assert trace["increasing"]["fillcolor"] == style.candles.increasing_fillcolor
        assert trace["decreasing"]["line"]["color"] == style.candles.decreasing_line_color

    def test_layout_honours_canvas_and_background_settings(self, builder):
        style = ChartStyle(canvas={"width": 640, "height": 480, "paper_bgcolor": "#ffffff"})
        layout = builder.build_spec(make_series(), style)["layout"]
        assert (layout["width"], layout["height"]) == (640, 480)
        assert layout["paper_bgcolor"] == "#ffffff"

    def test_intraday_hides_nights_and_weekends(self, builder):
        breaks = builder.build_spec(make_series(interval=HOUR), ChartStyle())["layout"]["xaxis"][
            "rangebreaks"
        ]
        assert {"bounds": ["sat", "mon"]} in breaks
        assert any(b.get("pattern") == "hour" for b in breaks)

    def test_daily_candles_keep_hours_visible(self, builder):
        breaks = builder.build_spec(make_series(interval=DAY), ChartStyle())["layout"]["xaxis"][
            "rangebreaks"
        ]
        assert all(b.get("pattern") != "hour" for b in breaks)

    def test_rangebreaks_can_be_switched_off(self, builder):
        style = ChartStyle(rangebreaks={"hide_weekends": False, "hide_nontrading_hours": False})
        assert "rangebreaks" not in builder.build_spec(make_series(), style)["layout"]["xaxis"]

    def test_volume_pane_is_added_only_when_asked_and_populated(self, builder):
        assert len(builder.build_spec(make_series(), ChartStyle())["data"]) == 1
        with_volume = builder.build_spec(make_series(), ChartStyle(volume={"visible": True}))
        assert [t["type"] for t in with_volume["data"]] == ["candlestick", "bar"]

    def test_volume_pane_is_skipped_when_the_field_is_empty(self, builder):
        series = make_series()
        blank = CandleSeries(
            candles=tuple(
                Candle(c.begin, c.open, c.high, c.low, c.close, volume=0, value=0)
                for c in series.candles
            ),
            source="csv",
            interval=HOUR,
        )
        assert len(builder.build_spec(blank, ChartStyle(volume={"visible": True}))["data"]) == 1

    def test_default_watermark_is_used_when_the_preset_has_none(self, builder):
        images = builder.build_spec(make_series(), ChartStyle())["layout"]["images"]
        assert images[0]["source"] == "/logo.png"
        assert images[0]["xref"] == "paper"

    def test_preset_watermark_wins_over_the_default(self, builder):
        style = ChartStyle(watermark={"source": "data:image/png;base64,AAAA"})
        images = builder.build_spec(make_series(), style)["layout"]["images"]
        assert images[0]["source"].startswith("data:image/png")

    def test_watermark_can_be_hidden(self, builder):
        style = ChartStyle(watermark={"visible": False})
        assert builder.build_spec(make_series(), style)["layout"].get("images", []) == []

    def test_manual_title_overrides_the_template(self, builder):
        style = ChartStyle(title={"mode": "manual", "text": "Свой заголовок"})
        assert builder.build_spec(make_series(), style)["layout"]["title"]["text"] == "Свой заголовок"

    def test_hidden_title_is_absent(self, builder):
        style = ChartStyle(title={"visible": False})
        assert "title" not in builder.build_spec(make_series(), style)["layout"]

    def test_note_annotation_is_optional(self, builder):
        assert builder.build_spec(make_series(), ChartStyle())["layout"].get("annotations", []) == []
        style = ChartStyle(note={"visible": True, "text": "Источник"})
        assert builder.build_spec(make_series(), style)["layout"]["annotations"][0]["text"] == "Источник"

    def test_fixed_tick_step_is_expressed_in_milliseconds(self, builder):
        style = ChartStyle(xaxis={"tickmode": "linear", "dtick_hours": 8})
        xaxis = builder.build_spec(make_series(), style)["layout"]["xaxis"]
        assert xaxis["tickmode"] == "linear" and xaxis["dtick"] == 8 * 3_600_000

    def test_spec_is_json_serialisable(self, builder):
        import json

        json.dumps(builder.build_spec(make_series(), ChartStyle()))


class TestStyleSchema:
    def test_schema_covers_every_section_of_chart_style(self):
        assert {s["key"] for s in ui_schema()} == set(ChartStyle.model_fields)

    def test_every_field_carries_what_the_ui_needs(self):
        for section in ui_schema():
            assert section["title"]
            for field in section["fields"]:
                assert field["key"] and field["label"] and field["widget"]
                assert "default" in field
                if field["widget"] == "select":
                    assert field["options"]

    def test_defaults_in_the_schema_round_trip_through_the_model(self):
        rebuilt = {
            section["key"]: {f["key"]: f["default"] for f in section["fields"]}
            for section in ui_schema()
        }
        assert ChartStyle(**rebuilt).model_dump() == ChartStyle().model_dump()

    def test_internal_ui_title_is_not_a_preset_field(self):
        assert "UI_TITLE" not in ChartStyle().model_dump()["canvas"]

    def test_title_text_fields_are_hidden_from_the_generic_panel(self):
        # They are owned by the dedicated title editor, but must still be in
        # the schema (so defaults round-trip) and in the model (so presets
        # carry them).
        title = next(s for s in ui_schema() if s["key"] == "title")
        hidden = {f["key"] for f in title["fields"] if f.get("hidden")}
        assert hidden == {"visible", "mode", "template", "text"}
        assert hidden <= set(ChartStyle().model_dump()["title"])

    def test_styling_fields_stay_visible(self):
        title = next(s for s in ui_schema() if s["key"] == "title")
        visible = {f["key"] for f in title["fields"] if not f.get("hidden")}
        assert {"font_size", "font_color", "x", "y", "xanchor"} <= visible

    def test_no_section_is_left_without_visible_fields(self):
        # A section whose fields are all hidden would render as an empty,
        # un-openable accordion panel.
        for section in ui_schema():
            assert any(not f.get("hidden") for f in section["fields"]), section["key"]


class TestWatermark:
    def test_rejects_files_that_are_not_images(self):
        with pytest.raises(InvalidImageError):
            build_data_uri(b"definitely not a png")

    def test_encodes_and_shrinks_an_uploaded_logo(self):
        import io

        from PIL import Image

        buffer = io.BytesIO()
        Image.new("RGB", (2000, 2000), "purple").save(buffer, format="PNG")
        uri = build_data_uri(buffer.getvalue(), max_px=64)
        assert uri.startswith("data:image/png;base64,")
        assert len(uri) < 20_000


def test_empty_series_is_rejected_at_construction():
    with pytest.raises(EmptySeriesError):
        CandleSeries(candles=(), source="csv")
