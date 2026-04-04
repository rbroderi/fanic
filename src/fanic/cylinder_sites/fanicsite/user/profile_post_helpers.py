import tomllib
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from fanic.cylinder_sites.common.protocols import FileUploadLike
from fanic.cylinder_sites.common.protocols import FormLike


@dataclass(frozen=True)
class DisplayNameFormData:
    display_name: str
    is_over_18: bool


@dataclass(frozen=True)
class PreferenceFormData:
    view_mature: bool
    view_explicit: bool


@dataclass(frozen=True)
class ThemeUploadResult:
    toml_text: str | None
    error_code: str | None


def profile_action_from_form(form: FormLike) -> str:
    return form.get("profile_action", "preferences").strip()


def parse_display_name_form(form: FormLike) -> DisplayNameFormData | None:
    display_name = form.get("display_name", "").strip()
    is_over_18_raw = form.get("is_over_18", "").strip().lower()

    match is_over_18_raw:
        case "yes":
            is_over_18 = True
        case "no":
            is_over_18 = False
        case _:
            return None

    return DisplayNameFormData(display_name=display_name, is_over_18=is_over_18)


def parse_theme_enabled(form: FormLike) -> bool:
    return form.get("custom_theme_enabled", "") == "on"


def parse_preference_form(form: FormLike) -> PreferenceFormData:
    view_mature = form.get("view_mature_rated", "") == "on"
    view_explicit = form.get("view_explicit_rated", "") == "on"
    return PreferenceFormData(view_mature=view_mature, view_explicit=view_explicit)


def read_uploaded_theme(theme_upload: FileUploadLike | None) -> ThemeUploadResult:
    if theme_upload is None or not theme_upload.filename:
        return ThemeUploadResult(toml_text=None, error_code=None)

    try:
        with TemporaryDirectory() as temp_dir:
            upload_path = Path(temp_dir) / "theme.toml"
            theme_upload.save(upload_path)
            uploaded_toml_text = upload_path.read_text(encoding="utf-8")
        _ = tomllib.loads(uploaded_toml_text)
    except (OSError, UnicodeDecodeError):
        return ThemeUploadResult(toml_text=None, error_code="theme_upload_error")
    except tomllib.TOMLDecodeError:
        return ThemeUploadResult(toml_text=None, error_code="theme_parse_error")

    return ThemeUploadResult(toml_text=uploaded_toml_text, error_code=None)
