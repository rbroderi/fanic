from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import ClassVar

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict

load_dotenv()


class FanicSettings(BaseSettings):
    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(extra="ignore")

    data_dir: str | None = Field(
        default=None,
        alias="FANIC_DATA_DIR",
    )

    enable_beartype: bool = Field(
        default=True,
        alias="FANIC_ENABLE_BEARTYPE",
    )

    explicit_threshold: float = Field(
        default=0.7,
        alias="FANIC_EXPLICIT_THRESHOLD",
    )

    openclip_cache_dir: str = Field(
        default_factory=lambda: str(Path.home() / ".cache" / "clip"),
        alias="FANIC_OPENCLIP_CACHE_DIR",
    )

    nsfw_logit_scale: float = Field(
        default=100.0,
        alias="FANIC_NSFW_LOGIT_SCALE",
    )

    thumbnail_avif_quality: int = Field(
        default=30,
        alias="FANIC_THUMBNAIL_AVIF_QUALITY",
    )

    image_avif_quality: int = Field(
        default=60,
        alias="FANIC_IMAGE_AVIF_QUALITY",
    )

    style_min_confidence: float = Field(
        default=0.6,
        alias="FANIC_STYLE_MIN_CONFIDENCE",
    )
    photoreal_min_confidence: float = Field(
        default=0.6,
        alias="FANIC_PHOTOREAL_MIN_CONFIDENCE",
    )
    style_min_confidence_photorealistic: float = Field(
        default=0.90,
        alias="FANIC_STYLE_MIN_CONFIDENCE_PHOTOREALISTIC",
    )
    photo_block_min_margin: float = Field(
        default=0.01,
        alias="FANIC_PHOTO_BLOCK_MIN_MARGIN",
    )
    style_min_top_prob: float = Field(
        default=0.34,
        alias="FANIC_STYLE_MIN_TOP_PROB",
    )
    style_min_top_margin: float = Field(
        default=0.05,
        alias="FANIC_STYLE_MIN_TOP_MARGIN",
    )
    style_logit_scale: float = Field(
        default=100.0,
        alias="FANIC_STYLE_LOGIT_SCALE",
    )
    style_load_retry_seconds: float = Field(
        default=5.0,
        alias="FANIC_STYLE_LOAD_RETRY_SECONDS",
    )
    model_load_logs: bool = Field(
        default=True,
        alias="FANIC_MODEL_LOAD_LOGS",
    )
    preload_models: bool = Field(
        default=True,
        alias="FANIC_PRELOAD_MODELS",
    )

    session_secret: str = Field(
        default="fanic-dev-secret-change-me",
        alias="FANIC_SESSION_SECRET",
    )
    session_max_age: int = Field(
        default=43200,
        alias="FANIC_SESSION_MAX_AGE",
    )
    session_secure: bool = Field(
        default=False,
        alias="FANIC_SESSION_SECURE",
    )
    admin_username: str = Field(
        default="admin",
        alias="FANIC_ADMIN_USERNAME",
    )
    admin_password: str = Field(
        default="admin",
        alias="FANIC_ADMIN_PASSWORD",
    )

    @property
    def package_root(self) -> Path:
        return Path(__file__).resolve().parent

    @property
    def data_root(self) -> Path:
        if self.data_dir:
            return Path(self.data_dir)
        return self.package_root / "storage"

    @property
    def style_min_confidence_effective(self) -> float:
        if "style_min_confidence" in self.model_fields_set:
            return self.style_min_confidence
        if "photoreal_min_confidence" in self.model_fields_set:
            return self.photoreal_min_confidence
        return self.style_min_confidence


@lru_cache(maxsize=1)
def get_settings() -> FanicSettings:
    return FanicSettings()
