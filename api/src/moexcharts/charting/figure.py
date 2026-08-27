"""Builds a Plotly figure from a candle series plus design settings.

The figure is produced once, server-side, and used for both outputs: the
browser renders the returned spec with plotly.js for the live preview and the
PNG download, and :mod:`.png` feeds the same spec to Kaleido for server-side
export. There is therefore exactly one implementation of the chart's look.
"""

from __future__ import annotations

import json
from typing import Any, Callable

import plotly.graph_objects as go
import plotly.io as pio
from plotly.subplots import make_subplots

from ..domain.models import CandleSeries
from .style import AxisStyle, ChartStyle
from .titles import suggest_title
from .watermark import default_watermark_data_uri

_MS_PER_HOUR = 3_600_000


def _axis_layout(axis: AxisStyle, font_family: str) -> dict[str, Any]:
    layout: dict[str, Any] = {
        "showgrid": axis.showgrid,
        "gridcolor": axis.gridcolor,
        "gridwidth": axis.gridwidth,
        "griddash": axis.griddash,
        "showline": axis.showline,
        "linecolor": axis.linecolor,
        "linewidth": axis.linewidth,
        "zeroline": axis.zeroline,
        "tickangle": axis.tickangle,
        "tickfont": {
            "size": axis.tickfont_size,
            "color": axis.tickfont_color,
            "family": font_family,
        },
    }
    if axis.title:
        layout["title"] = {"text": axis.title}
    if axis.tickformat:
        layout["tickformat"] = axis.tickformat
    if axis.nticks:
        layout["nticks"] = axis.nticks
    return layout


def _rangebreaks(style: ChartStyle, series: CandleSeries) -> list[dict[str, Any]]:
    breaks: list[dict[str, Any]] = []
    rb = style.rangebreaks
    if rb.hide_weekends:
        breaks.append({"bounds": ["sat", "mon"]})
    intraday = series.interval.is_intraday if series.interval else False
    if rb.hide_nontrading_hours and intraday and rb.session_end_hour != rb.session_start_hour:
        breaks.append(
            {"bounds": [rb.session_end_hour, rb.session_start_hour], "pattern": "hour"}
        )
    return breaks


def _watermark_images(style: ChartStyle, default_source: str) -> list[dict[str, Any]]:
    wm = style.watermark
    if not wm.visible:
        return []
    source = wm.source.strip() or default_source
    if not source:
        return []
    return [
        {
            "source": source,
            "xref": "paper",
            "yref": "paper",
            "x": wm.x,
            "y": wm.y,
            "sizex": wm.sizex,
            "sizey": wm.sizey,
            "xanchor": wm.xanchor,
            "yanchor": wm.yanchor,
            "opacity": wm.opacity,
            "layer": wm.layer,
            "sizing": "contain",
        }
    ]


def _annotations(style: ChartStyle) -> list[dict[str, Any]]:
    note = style.note
    if not note.visible or not note.text.strip():
        return []
    return [
        {
            "text": note.text,
            "xref": "paper",
            "yref": "paper",
            "x": note.x,
            "y": note.y,
            "xanchor": note.xanchor,
            "yanchor": "bottom",
            "showarrow": False,
            "font": {
                "size": note.font_size,
                "color": note.color,
                "family": style.font.family,
            },
        }
    ]


class FigureBuilder:
    """Turns ``(series, style)`` into a Plotly figure. Pure and side-effect free.

    *default_watermark* supplies the logo to use when a preset carries none. The
    browser gets a same-origin URL (small payload, cacheable); Kaleido gets an
    inline ``data:`` URI, because it cannot fetch anything.
    """

    def __init__(
        self, default_watermark: Callable[[], str] = default_watermark_data_uri
    ) -> None:
        self._default_watermark = default_watermark

    def build(self, series: CandleSeries, style: ChartStyle) -> go.Figure:
        x = [c.begin for c in series.candles]
        with_volume = style.volume.visible and self._has_volume(series, style.volume.field)

        figure = self._make_canvas(style, with_volume)
        # row/col are only valid on a subplot grid, so pass them only when there is one.
        placement = {"row": 1, "col": 1} if with_volume else {}
        figure.add_trace(self._candlestick(series, x, style), **placement)
        if with_volume:
            figure.add_trace(self._volume_bars(series, x, style), row=2, col=1)

        self._apply_layout(figure, series, style, with_volume)
        return figure

    def build_spec(self, series: CandleSeries, style: ChartStyle) -> dict[str, Any]:
        """JSON-safe figure dict, ready for ``Plotly.newPlot`` or Kaleido."""
        return json.loads(pio.to_json(self.build(series, style)))

    # -- pieces --------------------------------------------------------------

    @staticmethod
    def _has_volume(series: CandleSeries, field: str) -> bool:
        return any(getattr(c, field, None) for c in series.candles)

    @staticmethod
    def _make_canvas(style: ChartStyle, with_volume: bool) -> go.Figure:
        if not with_volume:
            return go.Figure()
        ratio = style.volume.height_ratio
        return make_subplots(
            rows=2,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=style.volume.spacing,
            row_heights=[1 - ratio, ratio],
        )

    @staticmethod
    def _candlestick(series: CandleSeries, x: list, style: ChartStyle) -> go.Candlestick:
        c = style.candles
        return go.Candlestick(
            x=x,
            open=[k.open for k in series.candles],
            high=[k.high for k in series.candles],
            low=[k.low for k in series.candles],
            close=[k.close for k in series.candles],
            increasing={
                "line": {"color": c.increasing_line_color, "width": c.line_width},
                "fillcolor": c.increasing_fillcolor,
            },
            decreasing={
                "line": {"color": c.decreasing_line_color, "width": c.line_width},
                "fillcolor": c.decreasing_fillcolor,
            },
            whiskerwidth=c.whisker_width,
            opacity=c.opacity,
            name=series.ticker or "OHLC",
            showlegend=style.misc.showlegend,
        )

    @staticmethod
    def _volume_bars(series: CandleSeries, x: list, style: ChartStyle) -> go.Bar:
        v = style.volume
        values = [getattr(k, v.field, None) or 0 for k in series.candles]
        if v.color_mode == "candle":
            colors = [
                style.candles.increasing_fillcolor
                if k.close >= k.open
                else style.candles.decreasing_fillcolor
                for k in series.candles
            ]
        else:
            colors = [v.color] * len(values)
        return go.Bar(
            x=x,
            y=values,
            marker={"color": colors, "line": {"width": 0}},
            opacity=v.opacity,
            name=v.title or "Объём",
            showlegend=False,
            hovertemplate="%{y:,.0f}<extra></extra>",
        )

    # -- layout --------------------------------------------------------------

    def _apply_layout(
        self,
        figure: go.Figure,
        series: CandleSeries,
        style: ChartStyle,
        with_volume: bool,
    ) -> None:
        canvas, font, misc = style.canvas, style.font, style.misc

        layout: dict[str, Any] = {
            "width": canvas.width,
            "height": canvas.height,
            "paper_bgcolor": canvas.paper_bgcolor,
            "plot_bgcolor": canvas.plot_bgcolor,
            "font": {"family": font.family, "size": font.size, "color": font.color},
            "margin": {
                "l": canvas.margin_l,
                "r": canvas.margin_r,
                "t": canvas.margin_t,
                "b": canvas.margin_b,
            },
            "showlegend": misc.showlegend,
            "hovermode": False if misc.hovermode == "false" else misc.hovermode,
            "images": _watermark_images(style, self._default_watermark()),
            "annotations": _annotations(style),
            "dragmode": "pan",
        }
        if canvas.template and canvas.template != "none":
            layout["template"] = canvas.template
        if style.title.visible:
            layout["title"] = self._title_layout(series, style)

        figure.update_layout(**layout)
        self._apply_axes(figure, series, style, with_volume)

    @staticmethod
    def _title_layout(series: CandleSeries, style: ChartStyle) -> dict[str, Any]:
        t = style.title
        text = t.text if t.mode == "manual" else suggest_title(series, t.template)
        return {
            "text": text,
            "x": t.x,
            "y": t.y,
            "xanchor": t.xanchor,
            "yanchor": "top",
            "font": {"size": t.font_size, "color": t.font_color, "family": style.font.family},
        }

    def _apply_axes(
        self,
        figure: go.Figure,
        series: CandleSeries,
        style: ChartStyle,
        with_volume: bool,
    ) -> None:
        family = style.font.family

        x_layout = _axis_layout(style.xaxis, family)
        x_layout["rangeslider"] = {"visible": style.misc.rangeslider}
        x_layout["showspikes"] = style.misc.spikes
        breaks = _rangebreaks(style, series)
        if breaks:
            x_layout["rangebreaks"] = breaks
        if style.xaxis.tickmode == "linear":
            x_layout["tickmode"] = "linear"
            x_layout["dtick"] = style.xaxis.dtick_hours * _MS_PER_HOUR
            x_layout["tick0"] = series.begin.isoformat()

        y_layout = _axis_layout(style.yaxis, family)
        y_layout["side"] = style.yaxis.side
        y_layout["showspikes"] = style.misc.spikes
        if style.yaxis.tickprefix:
            y_layout["tickprefix"] = style.yaxis.tickprefix
        if style.yaxis.ticksuffix:
            y_layout["ticksuffix"] = style.yaxis.ticksuffix
        if not style.yaxis.autorange and style.yaxis.range_min is not None and style.yaxis.range_max is not None:
            y_layout["autorange"] = False
            y_layout["range"] = [style.yaxis.range_min, style.yaxis.range_max]

        if with_volume:
            # Time labels belong under the bottom-most panel only.
            figure.update_xaxes(**{**x_layout, "showticklabels": False, "rangeslider": {"visible": False}}, row=1, col=1)
            figure.update_xaxes(**x_layout, row=2, col=1)
            figure.update_yaxes(**y_layout, row=1, col=1)
            volume_axis = _axis_layout(style.yaxis, family)
            volume_axis["side"] = style.yaxis.side
            volume_axis["title"] = {"text": style.volume.title} if style.volume.title else None
            figure.update_yaxes(**volume_axis, row=2, col=1)
        else:
            figure.update_xaxes(**x_layout)
            figure.update_yaxes(**y_layout)
