"""Russian locale for Plotly, shared by both render paths.

The pip ``plotly`` package bundles only the English locale dictionary, so the
Russian month and day names that Plotly prints on the datetime axis have to be
supplied separately. :data:`LOCALE_JS_PATH` is the official ``plotly-locale-ru``
module for the bundled plotly.js version, vendored because the deploy host
reaches no CDN.

* **Browser** loads it from ``/api/vendor/plotly-locale-ru.js`` and passes
  ``{locale: "ru"}`` to ``Plotly.newPlot``.
* **Kaleido** renders with its own copy of plotly.js and exposes no locale
  hook, so :func:`kaleido_plotlyjs` hands it the plotly.js bundle with the
  locale module appended and ``Plotly.toImage`` shimmed to pass ``locale: "ru"``
  (that is the entry point Kaleido calls, and it forwards no config of its own).
"""

from __future__ import annotations

import tempfile
from functools import lru_cache
from pathlib import Path

from ..config import ASSETS_DIR

#: Plotly locale name to activate. The UI is Russian-only, so this is fixed
#: rather than a per-preset setting.
LOCALE = "ru"

LOCALE_JS_PATH = ASSETS_DIR / "plotly-locale-ru.js"


@lru_cache(maxsize=1)
def locale_js() -> str:
    """The vendored ``plotly-locale-ru`` module, as served to the browser."""
    return LOCALE_JS_PATH.read_text(encoding="utf-8")


# Kaleido drives the export through ``Plotly.toImage(figure, opts)`` and adds no
# config of its own, so ``setPlotConfig`` defaults do not reach it. Wrapping
# ``toImage`` to fold ``locale`` into ``figure.config`` is what actually lands.
_KALEIDO_LOCALE_SHIM = """
(function () {
  var _toImage = Plotly.toImage;
  Plotly.toImage = function (figure, opts) {
    try {
      if (figure && typeof figure === "object") {
        figure.config = Object.assign({}, figure.config, { locale: %(locale)r });
      }
    } catch (e) {}
    return _toImage.apply(this, arguments);
  };
})();
""" % {"locale": LOCALE}


@lru_cache(maxsize=1)
def kaleido_plotlyjs() -> str:
    """Path to a plotly.js that renders in the Russian locale under Kaleido.

    Written once per process into the temp dir; Kaleido is pointed at it via
    ``plotly.io.kaleido.scope.plotlyjs``. Using the ``plotly`` package's own
    bundle (the same one the browser gets) keeps the two render paths on an
    identical plotly.js.
    """
    from plotly.offline import get_plotlyjs

    payload = "\n".join([get_plotlyjs(), locale_js(), _KALEIDO_LOCALE_SHIM])
    target = Path(tempfile.gettempdir()) / f"moexcharts-plotly-{LOCALE}.js"
    if not target.exists() or target.read_text(encoding="utf-8") != payload:
        target.write_text(payload, encoding="utf-8")
    return str(target)
