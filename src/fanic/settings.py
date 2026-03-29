import os
import re
import warnings
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any
from typing import ClassVar
from typing import Self
from typing import override

from pydantic import field_validator
from pydantic_settings import BaseSettings
from pydantic_settings import PydanticBaseSettingsSource
from pydantic_settings import SettingsConfigDict
from pydantic_settings import TomlConfigSettingsSource


class BytesUnit(Enum):
    __match_pattern: ClassVar[re.Pattern[str]] = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([A-Za-z]+)?\s*$")

    B = ("B", 1)
    KIB = ("KiB", 1024)
    MIB = ("MiB", 1024 * 1024)
    GIB = ("GiB", 1024 * 1024 * 1024)
    TIB = ("TiB", 1024 * 1024 * 1024 * 1024)

    @property
    def label(self) -> str:
        return self.value[0]

    @property
    def bytes(self) -> int:
        return self.value[1]

    def to_bytes(self, value: float | int) -> int:
        if value < 0:
            raise ValueError("Unit value must be non-negative")
        return int(round(float(value) * self.bytes))

    @classmethod
    def parse_match(cls, raw_value: str) -> re.Match[str] | None:
        return cls.__match_pattern.fullmatch(raw_value)

    @classmethod
    def from_token(cls, token: str | None) -> Self:
        normalized = token.upper() if token else cls.B.label.upper()
        member_name_by_token = {
            "B": "B",
            "BYTE": "B",
            "BYTES": "B",
            "KIB": "KIB",
            "KB": "KIB",
            "MIB": "MIB",
            "MB": "MIB",
            "GIB": "GIB",
            "GB": "GIB",
            "TIB": "TIB",
            "TB": "TIB",
        }
        member_name = member_name_by_token.get(normalized)
        if member_name is None:
            raise ValueError("Unknown size unit. Use one of: B, KiB, MiB, GiB, TiB")
        return cls[member_name]


_SETTINGS_TOML_OVERRIDE = os.getenv("FANIC_SETTINGS_TOML")
_SETTINGS_TOML_PATH = (
    Path(_SETTINGS_TOML_OVERRIDE).expanduser()
    if _SETTINGS_TOML_OVERRIDE
    else Path(__file__).resolve().parents[2] / "settings.toml"
)


class FanicSettings(BaseSettings):
    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        extra="ignore",
        env_prefix="FANIC_",
        env_file=".env",
        populate_by_name=True,
        toml_file=_SETTINGS_TOML_PATH,
    )

    @classmethod
    @override
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        toml_settings = TomlConfigSettingsSource(settings_cls)
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            toml_settings,
            file_secret_settings,
        )

    # Core runtime behavior
    csrf_protect: bool
    enable_beartype: bool
    environment: str
    preload_models: bool
    require_https: bool

    # Storage and paths
    data_dir: str | None
    db_path: str | None
    log_path_template: str
    media_base_url: str
    openclip_cache_dir: str

    # Session, invite gate, and local admin bootstrap
    admin_password_hash: str
    admin_username: str
    alpha_invite_codes_csv: str
    alpha_invite_cookie_max_age: int
    alpha_invite_gate_enabled: bool
    session_cookie_samesite: str
    session_max_age: int
    session_secure: bool
    session_secret: str

    # External auth provider settings
    auth0_audience: str
    auth0_callback_url: str
    auth0_client_id: str
    auth0_client_secret: str
    auth0_connection: str
    auth0_domain: str
    auth0_enabled: bool
    auth0_logout_return_url: str
    auth0_superadmin_email: str

    # Abuse and request controls
    auth_lockout_seconds: int
    auth_max_failures: int
    auth_window_seconds: int
    profile_history_limit: int
    upload_max_concurrent_per_user: int
    upload_rate_max_requests: int
    upload_rate_window_seconds: int

    # Upload and ingest hard limits
    max_cbz_member_uncompressed_bytes: int
    max_cbz_total_uncompressed_bytes: int
    max_cbz_upload_bytes: int
    max_ingest_pages: int
    max_page_upload_bytes: int
    max_upload_image_pixels: int
    user_page_quality_ramp_multiplier: float
    user_page_soft_cap: int

    # Classification and moderation tuning
    explicit_threshold: float
    model_load_logs: bool
    nsfw_logit_scale: float
    photo_block_min_margin: float
    photoreal_min_confidence: float
    style_load_retry_seconds: float
    style_logit_scale: float
    style_min_confidence: float
    style_min_confidence_photorealistic: float
    style_min_top_margin: float
    style_min_top_prob: float

    # Media encoding and type allowlists
    allowed_cbz_content_types_csv: str
    allowed_cbz_extensions_csv: str
    allowed_page_content_types_csv: str
    allowed_page_extensions_csv: str
    image_avif_quality: int
    thumbnail_avif_quality: int

    # Input normalization
    @field_validator("data_dir", "db_path", mode="before")
    @classmethod
    def _empty_string_to_none(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("openclip_cache_dir", mode="after")
    @classmethod
    def _expand_openclip_cache_dir(cls, value: str) -> str:
        return str(Path(value).expanduser())

    @field_validator("session_secret", mode="before")
    @classmethod
    def _session_secret_from_file(cls, value: Any) -> Any:
        return _resolve_value_from_file(value, "FANIC_SESSION_SECRET_FILE")

    @field_validator("admin_password_hash", mode="before")
    @classmethod
    def _admin_password_hash_from_file(cls, value: Any) -> Any:
        return _resolve_value_from_file(value, "FANIC_ADMIN_PASSWORD_HASH_FILE")

    @field_validator("auth0_client_secret", mode="before")
    @classmethod
    def _auth0_client_secret_from_file(cls, value: Any) -> Any:
        return _resolve_value_from_file(value, "FANIC_AUTH0_CLIENT_SECRET_FILE")

    @field_validator("auth0_domain", mode="before")
    @classmethod
    def _auth0_domain_from_file(cls, value: Any) -> Any:
        return _resolve_value_from_file(value, "FANIC_AUTH0_DOMAIN_FILE")

    @field_validator("auth0_client_id", mode="before")
    @classmethod
    def _auth0_client_id_from_file(cls, value: Any) -> Any:
        return _resolve_value_from_file(value, "FANIC_AUTH0_CLIENT_ID_FILE")

    @field_validator("alpha_invite_codes_csv", mode="before")
    @classmethod
    def _alpha_invite_codes_from_file(cls, value: Any) -> Any:
        return _resolve_value_from_file(value, "FANIC_ALPHA_INVITE_CODES_CSV_FILE")

    @field_validator(
        "max_cbz_upload_bytes",
        "max_page_upload_bytes",
        "max_cbz_member_uncompressed_bytes",
        "max_cbz_total_uncompressed_bytes",
        mode="before",
    )
    @classmethod
    def _parse_byte_limit_values(cls, value: Any) -> int:
        if isinstance(value, str | int):
            return parse_byte_size(value)
        raise ValueError("Byte-size setting must be a string like '256 MiB' or an integer")

    # Derived filesystem paths
    @property
    def package_root(self) -> Path:
        return Path(__file__).resolve().parent

    @property
    def data_root(self) -> Path:
        if self.data_dir:
            return Path(self.data_dir)
        return self.package_root / "storage"

    @property
    def database_path(self) -> Path:
        if self.db_path:
            return Path(self.db_path)
        return self.data_root / "fanic.db"

    # Effective runtime behavior
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

    # Production safety checks
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

        if self.auth0_enabled:
            missing: list[str] = []
            if not self.auth0_domain.strip():
                missing.append("FANIC_AUTH0_DOMAIN")
            if not self.auth0_client_id.strip():
                missing.append("FANIC_AUTH0_CLIENT_ID")
            if not self.auth0_client_secret.strip():
                missing.append("FANIC_AUTH0_CLIENT_SECRET")
            if not self.auth0_callback_url.strip():
                missing.append("FANIC_AUTH0_CALLBACK_URL")
            if not self.auth0_logout_return_url.strip():
                missing.append("FANIC_AUTH0_LOGOUT_RETURN_URL")
            if missing:
                raise RuntimeError("Auth0 is enabled but these settings are missing: " + ", ".join(missing))

    # Parsed collections
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
        return {value.strip().lower() for value in self.allowed_cbz_content_types_csv.split(",") if value.strip()}

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
        return {value.strip().lower() for value in self.allowed_page_content_types_csv.split(",") if value.strip()}

    @property
    def alpha_invite_codes(self) -> set[str]:
        return {value.strip() for value in self.alpha_invite_codes_csv.split(",") if value.strip()}

    # Auth feature state
    @property
    def auth0_enabled_effective(self) -> bool:
        return bool(self.auth0_enabled)

    @property
    def auth0_configured(self) -> bool:
        return (
            self.auth0_enabled_effective
            and bool(self.auth0_domain.strip())
            and bool(self.auth0_client_id.strip())
            and bool(self.auth0_client_secret.strip())
            and bool(self.auth0_callback_url.strip())
            and bool(self.auth0_logout_return_url.strip())
        )


def parse_byte_size(value: str | int) -> int:
    if isinstance(value, int):
        if value < 0:
            raise ValueError("Size must be non-negative")
        return value

    raw_value = value.strip()
    if not raw_value:
        raise ValueError("Size value cannot be empty")

    if raw_value.isdigit():
        parsed = int(raw_value)
        if parsed < 0:
            raise ValueError("Size must be non-negative")
        return parsed

    match = BytesUnit.parse_match(raw_value)
    if not match:
        raise ValueError(f"Invalid byte-size value: {value!r}")

    number_raw = match.group(1)
    unit_raw = match.group(2)
    number = float(number_raw)
    if number < 0:
        raise ValueError("Size must be non-negative")

    unit = BytesUnit.from_token(unit_raw)

    return unit.to_bytes(number)


def _resolve_value_from_file(value: Any, file_env_var_name: str) -> Any:
    file_path_raw = os.getenv(file_env_var_name, "").strip()
    if not file_path_raw:
        return value

    file_path = Path(file_path_raw).expanduser()
    try:
        loaded = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Unable to read {file_env_var_name} file at '{file_path}'") from exc
    return loaded.strip()


@lru_cache(maxsize=1)
def get_settings() -> FanicSettings:
    return FanicSettings()  # pyright: ignore[reportCallIssue]


_SETTINGS = get_settings()
DATA_ROOT = _SETTINGS.data_root
DB_PATH = _SETTINGS.database_path
CBZ_DIR = DATA_ROOT / "cbz"
WORKS_DIR = DATA_ROOT / "works"
STATIC_ASSETS_DIR = DATA_ROOT / "static"
FANART_DIR = DATA_ROOT / "fanart"


def ensure_storage_dirs() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    CBZ_DIR.mkdir(parents=True, exist_ok=True)
    WORKS_DIR.mkdir(parents=True, exist_ok=True)
    STATIC_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    FANART_DIR.mkdir(parents=True, exist_ok=True)
