"""Chart design settings.

This module is the single source of truth for chart formatting: the API
validates against it, the figure builder reads from it, presets are just its
JSON dump, and the browser renders its settings panel from the UI schema
derived here (``ui_schema``) - so there is no second copy of the field list to
drift out of sync.

Defaults reproduce the look of ``chart.ipynb``.
"""

from __future__ import annotations

from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

Widget = Literal["text", "textarea", "number", "color", "select", "checkbox", "image"]


def ui(
    default: Any,
    label: str,
    widget: Widget = "text",
    *,
    help: str = "",
    options: list[dict[str, Any]] | None = None,
    minimum: float | None = None,
    maximum: float | None = None,
    step: float | None = None,
    hidden: bool = False,
    **kwargs: Any,
) -> Any:
    """Declare a style field together with the metadata the UI needs.

    ``hidden`` keeps the field out of the generic settings panel while leaving
    it in the model and in saved presets - for settings that a purpose-built
    editor owns instead (the title text is edited in its own card).
    """
    extra: dict[str, Any] = {"label": label, "widget": widget}
    if hidden:
        extra["hidden"] = True
    if help:
        extra["help"] = help
    if options is not None:
        extra["options"] = options
    if minimum is not None:
        extra["min"] = minimum
    if maximum is not None:
        extra["max"] = maximum
    if step is not None:
        extra["step"] = step
    return Field(default, json_schema_extra=extra, **kwargs)


def _opts(*pairs: tuple[str, str]) -> list[dict[str, str]]:
    return [{"value": value, "label": label} for value, label in pairs]


class Section(BaseModel):
    """Base for a group of settings rendered as one collapsible panel."""

    model_config = ConfigDict(extra="ignore")

    #: Panel heading in the settings UI. ClassVar so it never lands in presets.
    UI_TITLE: ClassVar[str] = ""


class CanvasStyle(Section):
    UI_TITLE: ClassVar[str] = "Холст"

    width: int = ui(1200, "Ширина, px", "number", minimum=320, maximum=4000, step=10)
    height: int = ui(900, "Высота, px", "number", minimum=240, maximum=4000, step=10)
    scale: float = ui(
        2.0, "Множитель PNG", "number", minimum=1, maximum=4, step=0.5,
        help="Итоговый PNG = ширина x множитель. 2 подходит для соцсетей.",
    )
    template: str = ui(
        "plotly_dark",
        "Тема Plotly",
        "select",
        options=_opts(
            ("plotly_dark", "plotly_dark"),
            ("plotly", "plotly"),
            ("plotly_white", "plotly_white"),
            ("simple_white", "simple_white"),
            ("ggplot2", "ggplot2"),
            ("seaborn", "seaborn"),
            ("none", "без темы"),
        ),
        help="Базовая тема; настройки ниже переопределяют её.",
    )
    paper_bgcolor: str = ui("#f4effa", "Фон подложки", "color")
    plot_bgcolor: str = ui("#2f184b", "Фон области графика", "color")
    margin_l: int = ui(80, "Отступ слева", "number", minimum=0, maximum=400)
    margin_r: int = ui(40, "Отступ справа", "number", minimum=0, maximum=400)
    margin_t: int = ui(90, "Отступ сверху", "number", minimum=0, maximum=400)
    margin_b: int = ui(60, "Отступ снизу", "number", minimum=0, maximum=400)


class FontStyle(Section):
    UI_TITLE: ClassVar[str] = "Шрифт"

    family: str = ui(
        "Inter, 'Segoe UI', Arial, sans-serif", "Гарнитура", "text",
        help="Шрифт должен быть установлен в контейнере, иначе будет подставлен запасной.",
    )
    size: int = ui(14, "Базовый размер", "number", minimum=6, maximum=48)
    color: str = ui("#2f184b", "Цвет текста", "color")


class CandleStyle(Section):
    UI_TITLE: ClassVar[str] = "Свечи"

    increasing_line_color: str = ui("#b8d0eb", "Растущая: контур", "color")
    increasing_fillcolor: str = ui("#b9faf8", "Растущая: заливка", "color")
    decreasing_line_color: str = ui("#b5179e", "Падающая: контур", "color")
    decreasing_fillcolor: str = ui("#f72585", "Падающая: заливка", "color")
    line_width: float = ui(1.0, "Толщина контура", "number", minimum=0.1, maximum=6, step=0.1)
    whisker_width: float = ui(
        0.0, "Ширина засечек тени", "number", minimum=0, maximum=1, step=0.05,
        help="0 — тень тонкой линией (как в ноутбуке), 1 — засечки во всю ширину свечи.",
    )
    opacity: float = ui(1.0, "Непрозрачность", "number", minimum=0.1, maximum=1, step=0.05)


class TitleStyle(Section):
    UI_TITLE: ClassVar[str] = "Заголовок"

    # The first four are edited in the dedicated title card at the top of the
    # panel, not in this section - hence hidden here. They are ordinary model
    # fields otherwise, and are saved in presets like everything else.
    visible: bool = ui(True, "Показывать заголовок", "checkbox", hidden=True)
    mode: str = ui(
        "auto", "Режим", "select", hidden=True,
        options=_opts(("auto", "автоматически из шаблона"), ("manual", "вручную")),
    )
    template: str = ui("<b>{ticker}</b> | {candles}", "Шаблон", "text", hidden=True)
    text: str = ui("", "Текст (для режима «вручную»)", "text", hidden=True)
    font_size: int = ui(22, "Размер", "number", minimum=8, maximum=72)
    font_color: str = ui("#2f184b", "Цвет", "color")
    x: float = ui(0.02, "Позиция по X", "number", minimum=0, maximum=1, step=0.01)
    y: float = ui(0.96, "Позиция по Y", "number", minimum=0, maximum=1, step=0.01)
    xanchor: str = ui(
        "left", "Привязка", "select",
        options=_opts(("left", "слева"), ("center", "по центру"), ("right", "справа")),
    )


class NoteStyle(Section):
    UI_TITLE: ClassVar[str] = "Подпись"

    visible: bool = ui(False, "Показывать подпись", "checkbox")
    text: str = ui("Источник: Московская Биржа", "Текст", "text")
    font_size: int = ui(12, "Размер", "number", minimum=6, maximum=40)
    color: str = ui("#6b5a86", "Цвет", "color")
    x: float = ui(0.99, "Позиция по X", "number", minimum=0, maximum=1, step=0.01)
    y: float = ui(0.01, "Позиция по Y", "number", minimum=-0.2, maximum=1.2, step=0.01)
    xanchor: str = ui(
        "right", "Привязка", "select",
        options=_opts(("left", "слева"), ("center", "по центру"), ("right", "справа")),
    )


class AxisStyle(Section):
    """Shared shape for both axes; instances differ only in their defaults."""

    title: str = ui("", "Название оси", "text")
    showgrid: bool = ui(True, "Сетка", "checkbox")
    gridcolor: str = ui("#3c096c", "Цвет сетки", "color")
    gridwidth: float = ui(1.0, "Толщина сетки", "number", minimum=0.1, maximum=5, step=0.1)
    griddash: str = ui(
        "solid", "Штрих сетки", "select",
        options=_opts(("solid", "сплошная"), ("dot", "точки"), ("dash", "штрих"), ("longdash", "длинный штрих")),
    )
    showline: bool = ui(False, "Линия оси", "checkbox")
    linecolor: str = ui("#3c096c", "Цвет линии оси", "color")
    linewidth: float = ui(1.0, "Толщина линии оси", "number", minimum=0.1, maximum=6, step=0.1)
    zeroline: bool = ui(False, "Нулевая линия", "checkbox")
    tickfont_size: int = ui(12, "Размер подписей", "number", minimum=6, maximum=40)
    tickfont_color: str = ui("#2f184b", "Цвет подписей", "color")
    tickangle: int = ui(0, "Угол подписей", "number", minimum=-90, maximum=90, step=5)
    tickformat: str = ui("", "Формат подписей", "text", help="d3-format / strftime, например %d.%m или .2f")
    nticks: int = ui(0, "Максимум делений", "number", minimum=0, maximum=100, help="0 — автоматически")


class XAxisStyle(AxisStyle):
    UI_TITLE: ClassVar[str] = "Ось X (время)"

    tickmode: str = ui(
        "auto", "Шаг делений", "select",
        options=_opts(("auto", "автоматически"), ("linear", "фиксированный шаг")),
    )
    dtick_hours: float = ui(
        24.0, "Шаг, часов", "number", minimum=0.25, maximum=8760, step=0.25,
        help="Используется только при фиксированном шаге.",
    )


class YAxisStyle(AxisStyle):
    UI_TITLE: ClassVar[str] = "Ось Y (цена)"

    side: str = ui(
        "left", "Сторона", "select", options=_opts(("left", "слева"), ("right", "справа"))
    )
    tickprefix: str = ui("", "Префикс", "text")
    ticksuffix: str = ui("", "Суффикс", "text", help="Например « ₽»")
    autorange: bool = ui(True, "Авто-диапазон", "checkbox")
    range_min: float | None = ui(None, "Минимум", "number")
    range_max: float | None = ui(None, "Максимум", "number")


class RangeBreakStyle(Section):
    UI_TITLE: ClassVar[str] = "Пропуски (нерабочее время)"

    hide_weekends: bool = ui(True, "Скрывать выходные", "checkbox")
    hide_nontrading_hours: bool = ui(
        True, "Скрывать нерабочие часы", "checkbox",
        help="Применяется только к внутридневным таймфреймам.",
    )
    session_start_hour: int = ui(9, "Начало торгов, час", "number", minimum=0, maximum=23)
    session_end_hour: int = ui(20, "Конец торгов, час", "number", minimum=1, maximum=24)


class VolumeStyle(Section):
    UI_TITLE: ClassVar[str] = "Объём"

    visible: bool = ui(False, "Показывать объём", "checkbox")
    field: str = ui(
        "volume", "Источник", "select",
        options=_opts(("volume", "volume (лоты)"), ("value", "value (оборот)")),
    )
    height_ratio: float = ui(
        0.22, "Доля высоты", "number", minimum=0.1, maximum=0.5, step=0.01
    )
    spacing: float = ui(0.03, "Отступ между панелями", "number", minimum=0, maximum=0.2, step=0.01)
    color_mode: str = ui(
        "candle", "Раскраска", "select",
        options=_opts(("candle", "по направлению свечи"), ("single", "одним цветом")),
    )
    color: str = ui("#7b6ba8", "Цвет (одним цветом)", "color")
    opacity: float = ui(0.6, "Непрозрачность", "number", minimum=0.1, maximum=1, step=0.05)
    title: str = ui("", "Название панели", "text")


class WatermarkStyle(Section):
    UI_TITLE: ClassVar[str] = "Водяной знак"

    visible: bool = ui(True, "Показывать", "checkbox")
    source: str = ui(
        "", "Изображение", "image",
        help="Пусто — используется логотип по умолчанию. Загрузите свой файл, "
        "он сохранится внутри пресета.",
    )
    x: float = ui(0.95, "Позиция по X", "number", minimum=0, maximum=1, step=0.01)
    y: float = ui(0.925, "Позиция по Y", "number", minimum=0, maximum=1, step=0.01)
    sizex: float = ui(0.1, "Ширина (доля)", "number", minimum=0.01, maximum=1, step=0.01)
    sizey: float = ui(0.1, "Высота (доля)", "number", minimum=0.01, maximum=1, step=0.01)
    xanchor: str = ui(
        "center", "Привязка по X", "select",
        options=_opts(("left", "слева"), ("center", "по центру"), ("right", "справа")),
    )
    yanchor: str = ui(
        "middle", "Привязка по Y", "select",
        options=_opts(("top", "сверху"), ("middle", "по центру"), ("bottom", "снизу")),
    )
    opacity: float = ui(0.8, "Непрозрачность", "number", minimum=0.05, maximum=1, step=0.05)
    layer: str = ui(
        "above", "Слой", "select",
        options=_opts(("above", "поверх графика"), ("below", "под графиком")),
    )


class MiscStyle(Section):
    UI_TITLE: ClassVar[str] = "Прочее"

    rangeslider: bool = ui(False, "Полоса прокрутки снизу", "checkbox")
    showlegend: bool = ui(False, "Легенда", "checkbox")
    hovermode: str = ui(
        "x unified", "Подсказки", "select",
        options=_opts(("x unified", "объединённые"), ("x", "по оси X"), ("closest", "ближайшая"), ("false", "выключены")),
    )
    spikes: bool = ui(False, "Перекрестие", "checkbox")


class ChartStyle(BaseModel):
    """The complete design settings object. Presets are this model, as JSON."""

    model_config = ConfigDict(extra="ignore")

    canvas: CanvasStyle = Field(default_factory=CanvasStyle)
    font: FontStyle = Field(default_factory=FontStyle)
    candles: CandleStyle = Field(default_factory=CandleStyle)
    title: TitleStyle = Field(default_factory=TitleStyle)
    note: NoteStyle = Field(default_factory=NoteStyle)
    xaxis: XAxisStyle = Field(default_factory=XAxisStyle)
    yaxis: YAxisStyle = Field(default_factory=YAxisStyle)
    rangebreaks: RangeBreakStyle = Field(default_factory=RangeBreakStyle)
    volume: VolumeStyle = Field(default_factory=VolumeStyle)
    watermark: WatermarkStyle = Field(default_factory=WatermarkStyle)
    misc: MiscStyle = Field(default_factory=MiscStyle)


def ui_schema() -> list[dict[str, Any]]:
    """Describe :class:`ChartStyle` for the browser settings panel.

    Returns one entry per section, each with its fields' widget metadata and
    default value. The UI renders this generically, so adding a setting means
    adding one field above and nothing else.
    """
    sections: list[dict[str, Any]] = []
    for section_key, section_field in ChartStyle.model_fields.items():
        section_model = section_field.annotation
        if not (isinstance(section_model, type) and issubclass(section_model, Section)):
            continue
        fields: list[dict[str, Any]] = []
        for name, field in section_model.model_fields.items():
            extra = dict(field.json_schema_extra or {})  # type: ignore[arg-type]
            fields.append(
                {
                    "key": name,
                    "label": extra.pop("label", name),
                    "widget": extra.pop("widget", "text"),
                    "default": field.get_default(call_default_factory=True),
                    **extra,
                }
            )
        sections.append(
            {
                "key": section_key,
                "title": section_model.UI_TITLE or section_key,
                "fields": fields,
            }
        )
    return sections
