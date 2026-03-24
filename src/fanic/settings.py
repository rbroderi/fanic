from __future__ import annotations

import hashlib
import math
import mimetypes
import warnings
from functools import lru_cache
from pathlib import Path
from typing import ClassVar
from typing import Literal

import pillow_avif  # noqa: F401  # pyright: ignore[reportUnusedImport]
from dotenv import load_dotenv
from PIL import Image
from pydantic import Field
from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict

load_dotenv()


ByteUnit = Literal["B", "KiB", "MiB", "GiB", "TiB"]


def from_unit(unit: ByteUnit, value: float | int) -> int:
    unit_multiplier_by_name: dict[ByteUnit, int] = {
        "B": 1,
        "KiB": 1024,
        "MiB": 1024 * 1024,
        "GiB": 1024 * 1024 * 1024,
        "TiB": 1024 * 1024 * 1024 * 1024,
    }

    multiplier = unit_multiplier_by_name[unit]
    if not math.isfinite(value):
        raise ValueError("Unit value must be finite")
    if value < 0:
        raise ValueError("Unit value must be non-negative")
    return int(round(value * multiplier))


def _default_allowed_page_extensions_csv() -> str:
    Image.init()
    values = {
        extension.lower()
        for extension, format_name in Image.registered_extensions().items()
        if format_name in Image.OPEN
    }
    if not values:
        values = {
            ".avif",
            ".bmp",
            ".gif",
            ".jpeg",
            ".jpg",
            ".png",
            ".tif",
            ".tiff",
            ".webp",
        }
    return ",".join(sorted(values))


def _default_allowed_page_content_types_csv() -> str:
    Image.init()
    content_types: set[str] = set()
    for format_name in Image.OPEN:
        mime = Image.MIME.get(format_name)
        if mime:
            content_types.add(str(mime).lower())
    for extension in _default_allowed_page_extensions_csv().split(","):
        guessed, _ = mimetypes.guess_type(f"placeholder{extension}")
        if guessed:
            content_types.add(guessed.lower())
    content_types.add("application/octet-stream")
    return ",".join(sorted(content_types))


class FanicSettings(BaseSettings):
    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(extra="ignore")

    environment: str = Field(
        default="development",
        alias="FANIC_ENV",
    )

    require_https: bool = Field(
        default=True,
        alias="FANIC_REQUIRE_HTTPS",
    )

    csrf_protect: bool = Field(
        default=True,
        alias="FANIC_CSRF_PROTECT",
    )

    data_dir: str | None = Field(
        default=None,
        alias="FANIC_DATA_DIR",
    )

    media_base_url: str = Field(
        default="http://127.0.0.1:8080",
        alias="FANIC_MEDIA_BASE_URL",
    )

    enable_beartype: bool = Field(
        default=True,
        alias="FANIC_ENABLE_BEARTYPE",
    )

    log_path_template: str = Field(
        default="logs/%TIMESTAMP%.log",
        alias="FANIC_LOG_PATH_TEMPLATE",
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
    session_cookie_samesite: str = Field(
        default="Lax",
        alias="FANIC_SESSION_COOKIE_SAMESITE",
    )
    admin_username: str = Field(
        default="admin",
        alias="FANIC_ADMIN_USERNAME",
    )
    admin_password_hash: str = Field(
        default=f"sha256${hashlib.sha256(b'admin').hexdigest()}",
        alias="FANIC_ADMIN_PASSWORD_HASH",
    )

    auth_max_failures: int = Field(
        default=5,
        alias="FANIC_AUTH_MAX_FAILURES",
    )
    auth_window_seconds: int = Field(
        default=300,
        alias="FANIC_AUTH_WINDOW_SECONDS",
    )
    auth_lockout_seconds: int = Field(
        default=900,
        alias="FANIC_AUTH_LOCKOUT_SECONDS",
    )
    upload_rate_window_seconds: int = Field(
        default=60,
        alias="FANIC_UPLOAD_RATE_WINDOW_SECONDS",
    )
    upload_rate_max_requests: int = Field(
        default=20,
        alias="FANIC_UPLOAD_RATE_MAX_REQUESTS",
    )
    upload_max_concurrent_per_user: int = Field(
        default=1,
        alias="FANIC_UPLOAD_MAX_CONCURRENT_PER_USER",
    )
    profile_history_limit: int = Field(
        default=100,
        alias="FANIC_PROFILE_HISTORY_LIMIT",
    )

    max_cbz_upload_bytes: int = Field(
        default=from_unit("MiB", 256.0),
        alias="FANIC_MAX_CBZ_UPLOAD_BYTES",
    )
    max_page_upload_bytes: int = Field(
        default=from_unit("MiB", 20.0),
        alias="FANIC_MAX_PAGE_UPLOAD_BYTES",
    )
    max_ingest_pages: int = Field(
        default=2000,
        alias="FANIC_MAX_INGEST_PAGES",
    )
    max_cbz_member_uncompressed_bytes: int = Field(
        default=from_unit("MiB", 128.0),
        alias="FANIC_MAX_CBZ_MEMBER_UNCOMPRESSED_BYTES",
    )
    max_cbz_total_uncompressed_bytes: int = Field(
        default=from_unit("GiB", 2.0),
        alias="FANIC_MAX_CBZ_TOTAL_UNCOMPRESSED_BYTES",
    )
    max_upload_image_pixels: int = Field(
        default=100_000_000,
        alias="FANIC_MAX_UPLOAD_IMAGE_PIXELS",
    )
    user_page_soft_cap: int = Field(
        default=2000,
        alias="FANIC_USER_PAGE_SOFT_CAP",
    )
    user_page_quality_ramp_multiplier: float = Field(
        default=1.5,
        alias="FANIC_USER_PAGE_QUALITY_RAMP_MULTIPLIER",
    )
    allowed_cbz_extensions_csv: str = Field(
        default=".cbz",
        alias="FANIC_ALLOWED_CBZ_EXTENSIONS",
    )
    allowed_cbz_content_types_csv: str = Field(
        default="application/zip,application/x-cbz,application/octet-stream",
        alias="FANIC_ALLOWED_CBZ_CONTENT_TYPES",
    )
    allowed_page_extensions_csv: str = Field(
        default_factory=_default_allowed_page_extensions_csv,
        alias="FANIC_ALLOWED_PAGE_EXTENSIONS",
    )
    allowed_page_content_types_csv: str = Field(
        default_factory=_default_allowed_page_content_types_csv,
        alias="FANIC_ALLOWED_PAGE_CONTENT_TYPES",
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

    @property
    def is_production(self) -> bool:
        normalized = self.environment.strip().lower()
        return normalized in {"prod", "production"}

    def validate_production_settings(self) -> None:
        """Emit warnings for insecure defaults that must be overridden in production."""
        if not self.is_production:
            return

        if self.session_secret == "fanic-dev-secret-change-me":
            raise RuntimeError(
                "FANIC_SESSION_SECRET must be set to a strong random value "
                "in production (e.g. python -c 'import secrets; print(secrets.token_hex(32))')."
            )

        if self.admin_password_hash.startswith("sha256$"):
            warnings.warn(
                "FANIC_ADMIN_PASSWORD_HASH uses bare SHA256 which is unsuitable for "
                "production. Generate a strong hash with: fanic hash-admin-password",
                stacklevel=1,
            )

        if not self.data_dir:
            warnings.warn(
                "FANIC_DATA_DIR is not set; data will be stored inside the package "
                "directory. Set an absolute path for production deployments.",
                stacklevel=1,
            )

    @property
    def session_secure_effective(self) -> bool:
        return self.session_secure if self.session_secure else self.is_production

    @property
    def csrf_protect_effective(self) -> bool:
        if not self.is_production:
            return False
        return self.csrf_protect if self.csrf_protect else False

    @property
    def require_https_effective(self) -> bool:
        if not self.is_production:
            return False
        return self.require_https if self.require_https else False

    @property
    def allowed_cbz_extensions(self) -> set[str]:
        values: set[str] = set()
        for raw in self.allowed_cbz_extensions_csv.split(","):
            value = raw.strip().lower()
            if not value:
                continue
            if not value.startswith("."):
                value = f".{value}"
            values.add(value)
        return values

    @property
    def allowed_cbz_content_types(self) -> set[str]:
        return {
            value.strip().lower()
            for value in self.allowed_cbz_content_types_csv.split(",")
            if value.strip()
        }

    @property
    def allowed_page_extensions(self) -> set[str]:
        values: set[str] = set()
        for raw in self.allowed_page_extensions_csv.split(","):
            value = raw.strip().lower()
            if not value:
                continue
            if not value.startswith("."):
                value = f".{value}"
            values.add(value)
        return values

    @property
    def allowed_page_content_types(self) -> set[str]:
        return {
            value.strip().lower()
            for value in self.allowed_page_content_types_csv.split(",")
            if value.strip()
        }


@lru_cache(maxsize=1)
def get_settings() -> FanicSettings:
    return FanicSettings()


_SETTINGS = get_settings()
DATA_ROOT = _SETTINGS.data_root
DB_PATH = DATA_ROOT / "fanic.db"
CBZ_DIR = DATA_ROOT / "cbz"
WORKS_DIR = DATA_ROOT / "works"
STATIC_ASSETS_DIR = DATA_ROOT / "static"
FANART_DIR = DATA_ROOT / "fanart"


def ensure_storage_dirs() -> None:
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    CBZ_DIR.mkdir(parents=True, exist_ok=True)
    WORKS_DIR.mkdir(parents=True, exist_ok=True)
    STATIC_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    FANART_DIR.mkdir(parents=True, exist_ok=True)
