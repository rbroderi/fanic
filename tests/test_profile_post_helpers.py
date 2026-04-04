from pathlib import Path
from typing import final

from fanic.cylinder_sites.fanicsite.user.profile_post_helpers import (
    parse_display_name_form,
)
from fanic.cylinder_sites.fanicsite.user.profile_post_helpers import (
    parse_preference_form,
)
from fanic.cylinder_sites.fanicsite.user.profile_post_helpers import parse_theme_enabled
from fanic.cylinder_sites.fanicsite.user.profile_post_helpers import (
    profile_action_from_form,
)
from fanic.cylinder_sites.fanicsite.user.profile_post_helpers import read_uploaded_theme


@final
class _FormStub:
    def __init__(self, values: dict[str, str]) -> None:
        self._values: dict[str, str] = values

    def get(self, key: str, default: str = "") -> str:
        return self._values.get(key, default)


@final
class _UploadStub:
    def __init__(self, filename: str, payload: bytes) -> None:
        self.filename: str | None = filename
        self._payload: bytes = payload

    def save(self, dst: str | Path) -> None:
        Path(dst).write_bytes(self._payload)


@final
class _BrokenUploadStub:
    def __init__(self, filename: str) -> None:
        self.filename: str | None = filename

    def save(self, dst: str | Path) -> None:
        _ = dst
        raise OSError("boom")


def test_profile_action_from_form_defaults_preferences() -> None:
    assert profile_action_from_form(_FormStub({})) == "preferences"
    assert profile_action_from_form(_FormStub({"profile_action": " theme "})) == "theme"


def test_parse_display_name_form() -> None:
    parsed = parse_display_name_form(_FormStub({"display_name": " Alice ", "is_over_18": " yes "}))
    assert parsed is not None
    assert parsed.display_name == "Alice"
    assert parsed.is_over_18 is True

    parsed_invalid = parse_display_name_form(_FormStub({"display_name": "Alice", "is_over_18": "maybe"}))
    assert parsed_invalid is None

    parsed_missing_age = parse_display_name_form(_FormStub({"display_name": "Alice"}))
    assert parsed_missing_age is None


def test_parse_theme_enabled_and_preferences() -> None:
    assert parse_theme_enabled(_FormStub({"custom_theme_enabled": "on"})) is True
    assert parse_theme_enabled(_FormStub({"custom_theme_enabled": "off"})) is False

    parsed = parse_preference_form(_FormStub({"view_mature_rated": "on", "view_explicit_rated": ""}))
    assert parsed.view_mature is True
    assert parsed.view_explicit is False


def test_read_uploaded_theme_variants() -> None:
    no_upload = read_uploaded_theme(None)
    assert no_upload.toml_text is None
    assert no_upload.error_code is None

    valid_upload = _UploadStub("theme.toml", b"[dark]\naccent='#268bd2'\n")
    valid = read_uploaded_theme(valid_upload)
    assert valid.error_code is None
    assert valid.toml_text is not None
    assert "[dark]" in valid.toml_text

    invalid_upload = _UploadStub("theme.toml", b"[dark\n")
    invalid = read_uploaded_theme(invalid_upload)
    assert invalid.toml_text is None
    assert invalid.error_code == "theme_parse_error"

    broken_upload = _BrokenUploadStub("theme.toml")
    broken = read_uploaded_theme(broken_upload)
    assert broken.toml_text is None
    assert broken.error_code == "theme_upload_error"
