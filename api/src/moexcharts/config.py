"""Application settings.

Every knob that differs between a developer laptop and the locked-down work PC
(TLS verification, proxy, ISS base URL, limits) lives here and nowhere else.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ASSETS_DIR = Path(__file__).resolve().parent / "assets"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CHARTS_", env_file=".env", extra="ignore")

    # --- MOEX ISS -----------------------------------------------------------
    moex_base_url: str = "https://iss.moex.com/iss"
    #: Corporate TLS interception on the work PC breaks certificate validation.
    #: Set CHARTS_MOEX_VERIFY_SSL=false there. Prefer moex_ca_bundle when the
    #: corporate root CA is available - it keeps verification on.
    moex_verify_ssl: bool = True
    moex_ca_bundle: str | None = None
    moex_timeout_seconds: float = 30.0
    #: ISS returns at most 500 rows per candles request; we page through.
    moex_page_size: int = 500
    moex_max_pages: int = 200

    # --- Guard rails --------------------------------------------------------
    #: Refuse absurd combinations (e.g. 1-minute candles over 5 years) before
    #: hammering ISS. Also caps the JSON payload the browser has to handle.
    max_candles: int = 20_000
    max_upload_bytes: int = 20 * 1024 * 1024
    #: Uploaded watermarks are re-encoded to PNG and fit inside this box.
    watermark_max_px: int = 512

    # --- Misc ---------------------------------------------------------------
    cors_origins: str = "*"
    intervals_cache_seconds: int = 3600
    timezone: str = "Europe/Moscow"

    @property
    def httpx_verify(self) -> bool | str:
        """Value for httpx's ``verify`` argument."""
        if self.moex_ca_bundle:
            return self.moex_ca_bundle
        return self.moex_verify_ssl

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
