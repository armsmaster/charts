"""Watermark image handling.

Uploaded logos are re-encoded to a bounded PNG and returned as a ``data:`` URI,
so a preset stays a single self-contained JSON file and the figure spec renders
identically in the browser and in Kaleido - neither needs to fetch the image.
"""

from __future__ import annotations

import base64
import io
from functools import lru_cache

from PIL import Image, UnidentifiedImageError

from ..config import ASSETS_DIR, get_settings
from ..domain.models import DomainError

DEFAULT_WATERMARK_PATH = ASSETS_DIR / "wm.png"

#: Same-origin URL the browser uses for the bundled logo. Keeping the default
#: watermark out of the figure JSON saves ~230 KB on every re-render.
DEFAULT_WATERMARK_URL = "/api/charts/watermark/default.png"


class InvalidImageError(DomainError):
    pass


def _to_data_uri(png_bytes: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png_bytes).decode("ascii")


def _encode(image: Image.Image, max_px: int) -> bytes:
    image = image.convert("RGBA")
    image.thumbnail((max_px, max_px), Image.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def build_data_uri(raw: bytes, max_px: int | None = None) -> str:
    """Validate, normalise and inline an uploaded logo."""
    max_px = max_px or get_settings().watermark_max_px
    try:
        with Image.open(io.BytesIO(raw)) as image:
            image.load()
            return _to_data_uri(_encode(image, max_px))
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise InvalidImageError(
            "The file is not a readable image (PNG, JPEG, WEBP or GIF expected)."
        ) from exc


def default_watermark_url() -> str:
    return DEFAULT_WATERMARK_URL


@lru_cache(maxsize=1)
def default_watermark_png() -> bytes:
    """The bundled logo as normalised PNG bytes."""
    if not DEFAULT_WATERMARK_PATH.exists():
        return b""
    with Image.open(DEFAULT_WATERMARK_PATH) as image:
        image.load()
        return _encode(image, get_settings().watermark_max_px)


@lru_cache(maxsize=1)
def default_watermark_data_uri() -> str:
    """The bundled logo, used when a preset does not carry its own."""
    if not DEFAULT_WATERMARK_PATH.exists():
        return ""
    try:
        return build_data_uri(DEFAULT_WATERMARK_PATH.read_bytes())
    except InvalidImageError:
        return ""
