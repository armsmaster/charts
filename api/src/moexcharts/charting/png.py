"""Server-side PNG export via Kaleido.

Optional by design: the browser can already export the same figure with
``Plotly.toImage``. If Kaleido is missing or broken in the container, the API
reports it as unavailable and the UI falls back to the client-side path instead
of failing the whole request.
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)


class KaleidoPngRenderer:
    """Implements :class:`~moexcharts.domain.ports.ImageRenderer`."""

    def __init__(self) -> None:
        self._checked = False
        self._available = False
        self._error = ""

    @property
    def available(self) -> bool:
        self._probe()
        return self._available

    @property
    def error(self) -> str:
        self._probe()
        return self._error

    def _probe(self) -> None:
        if self._checked:
            return
        self._checked = True
        try:
            import plotly.io as pio

            self._install_locale(pio)
            pio.to_image({"data": [], "layout": {"width": 10, "height": 10}}, format="png")
            self._available = True
        except Exception as exc:  # pragma: no cover - environment dependent
            self._error = f"{type(exc).__name__}: {exc}"
            log.warning("Server-side PNG export is unavailable: %s", self._error)

    @staticmethod
    def _install_locale(pio: Any) -> None:
        """Point Kaleido at a plotly.js that renders in the Russian locale.

        ``scope.plotlyjs`` exists in kaleido 0.2.x (the pinned version). If the
        attribute is gone or the bundle cannot be built, the PNG still renders -
        only its month names stay English, and the browser preview and its
        PNG fallback are localised regardless.
        """
        try:
            from .locale import kaleido_plotlyjs

            pio.kaleido.scope.plotlyjs = kaleido_plotlyjs()
        except Exception:  # pragma: no cover - kaleido API / filesystem dependent
            log.warning("Could not localise Kaleido; server PNG keeps English dates", exc_info=True)

    def to_png(self, figure: dict[str, Any], width: int, height: int, scale: float) -> bytes:
        import plotly.io as pio

        return pio.to_image(
            figure, format="png", width=width, height=height, scale=scale, engine="kaleido"
        )
