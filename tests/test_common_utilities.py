from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any
from typing import Protocol

import pytest


class ResponseLike(Protocol):
    status_code: int
    content_type: str
    headers: dict[str, str]
    data: bytes

    def set_data(self, data: str | bytes) -> None: ...


class RequestLike(Protocol):
    path: str
    cookies: dict[str, str]


class UploadLike:
    def __init__(self, filename: str, content: str) -> None:
        self.filename: str | None = filename
        self._content: str = content

    def save(self, dst: str | Path) -> None:
        Path(dst).write_text(self._content, encoding="utf-8")


def _role_for_alice_or_guest(username: str | None) -> str:
    return "user" if username == "alice" else "guest"


def _role_superadmin(_: str | None) -> str:
    return "superadmin"


def _role_guest(_: str | None) -> str:
    return "guest"


def test_json_and_text_helpers(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_response: Callable[[], ResponseLike],
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/common.py", "common_helpers_test"
    )

    json_result = module.json_response(dummy_response(), {"ok": True}, 201)
    assert json_result.status_code == 201
    assert json_result.content_type == "application/json; charset=utf-8"
    assert b'"ok": true' in json_result.data

    text_result = module.text_error(dummy_response(), "bad", 400)
    assert text_result.status_code == 400
    assert text_result.content_type == "text/plain; charset=utf-8"
    assert text_result.data == b"bad"


def test_send_file_and_safe_static_path(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_response: Callable[[], ResponseLike],
    tmp_path: Path,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/common.py", "common_send_file_test"
    )

    missing = module.send_file(dummy_response(), tmp_path / "missing.txt")
    assert missing.status_code == 404
    assert missing.data == b"Not found"

    test_file = tmp_path / "demo.txt"
    test_file.write_text("hello", encoding="utf-8")
    sent = module.send_file(dummy_response(), test_file, filename="download.txt")
    assert sent.status_code == 200
    assert sent.data == b"hello"
    assert sent.headers["Content-Disposition"] == 'attachment; filename="download.txt"'

    safe_path = module.safe_static_path("styles.css")
    assert safe_path is not None
    assert safe_path.name == "styles.css"
    assert module.safe_static_path("../../escape.txt") is None


def test_route_helpers_and_user_menu(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/common.py", "common_route_helpers_test"
    )

    def fake_current_user_logged_in(req: Any) -> str:
        _ = req
        return "alice"

    def fake_current_user_admin(req: Any) -> str:
        _ = req
        return "admin"

    def fake_current_user_logged_out(req: Any) -> None:
        _ = req
        return None

    request = dummy_request(path="/works/abc", args={})
    assert module.path_parts(request) == ["works", "abc"]
    assert module.route_tail(request, ["works"]) == ["abc"]
    assert module.route_tail(request, ["works", "abc", "extra"]) is None
    assert module.route_tail(request, ["reader"]) is None

    monkeypatch.setattr(module, "current_user", fake_current_user_logged_in)
    monkeypatch.setattr(
        module,
        "role_for_user",
        _role_for_alice_or_guest,
    )
    logged_in = module.user_menu_replacements(request)
    assert logged_in["__USER_MENU_LOGIN_HIDDEN_ATTR__"] == "hidden"
    assert logged_in["__USER_MENU_PROFILE_HIDDEN_ATTR__"] == ""
    assert logged_in["__ADMIN_REPORTS_LINK__"] == ""

    monkeypatch.setattr(module, "current_user", fake_current_user_admin)
    monkeypatch.setattr(module, "role_for_user", _role_superadmin)
    logged_in_admin = module.user_menu_replacements(request)
    assert (
        logged_in_admin["__ADMIN_REPORTS_LINK__"]
        == '<a href="/admin/reports">Reports</a><a href="/admin/users">Users</a>'
    )

    monkeypatch.setattr(module, "current_user", fake_current_user_logged_out)
    monkeypatch.setattr(module, "role_for_user", _role_guest)
    logged_out = module.user_menu_replacements(request)
    assert logged_out["__USER_MENU_LOGIN_HIDDEN_ATTR__"] == ""
    assert logged_out["__USER_MENU_PROFILE_HIDDEN_ATTR__"] == "hidden"
    assert logged_out["__ADMIN_REPORTS_LINK__"] == ""


def test_theme_override_parsing_and_style_tag(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/common.py", "common_theme_parse_test"
    )

    def fake_current_user(req: Any) -> str:
        _ = req
        return "alice"

    def fake_get_theme_preference_valid(username: str) -> dict[str, Any]:
        _ = username
        return {
            "enabled": True,
            "toml_text": '[light]\naccent="#268bd2"\n[dark]\naccent="#b58900"\n',
        }

    def fake_get_theme_preference_invalid(username: str) -> dict[str, Any]:
        _ = username
        return {"enabled": True, "toml_text": "not=valid=toml"}

    assert module._theme_value_is_safe("#268bd2") is True
    assert module._theme_value_is_safe("bad;value") is False
    assert module._normalize_theme_var_name("--accent_soft") == "accent-soft"

    overrides = module._extract_theme_overrides(
        '[light]\naccent="#268bd2"\nunknown="skip"\n[dark]\naccent="bad;value"\n'
    )
    assert overrides["light"]["accent"] == "#268bd2"
    assert "unknown" not in overrides["light"]
    assert "accent" not in overrides["dark"]

    req = dummy_request(path="/", args={})
    monkeypatch.setattr(module, "current_user", fake_current_user)
    monkeypatch.setattr(
        module,
        "get_user_theme_preference",
        fake_get_theme_preference_valid,
    )
    style_tag = module._custom_theme_style_tag(req)
    assert "customThemeOverrides" in style_tag
    assert "--accent: #268bd2;" in style_tag
    assert "--accent: #b58900;" in style_tag

    monkeypatch.setattr(
        module,
        "get_user_theme_preference",
        fake_get_theme_preference_invalid,
    )
    assert module._custom_theme_style_tag(req) == ""


def test_session_and_upload_helpers(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/common.py", "common_session_upload_test"
    )

    def fake_jwt_encode(header: object, payload: object, secret: object) -> bytes:
        _ = (header, payload, secret)
        return b"tok"

    def fake_jwt_decode_ok(token: str | bytes, secret: object) -> dict[str, object]:
        _ = (token, secret)
        return {"exp": 1_100, "sub": "alice"}

    def fake_jwt_decode_bad_exp(
        token: str | bytes, secret: object
    ) -> dict[str, object]:
        _ = (token, secret)
        return {"exp": "x", "sub": "alice"}

    def fake_jwt_decode_expired(
        token: str | bytes, secret: object
    ) -> dict[str, object]:
        _ = (token, secret)
        return {"exp": 900, "sub": "alice"}

    def fake_jwt_decode_missing_sub(
        token: str | bytes, secret: object
    ) -> dict[str, object]:
        _ = (token, secret)
        return {"exp": 1_100}

    def fake_decode_session(token: str) -> str:
        _ = token
        return "alice"

    monkeypatch.setattr(module.time, "time", lambda: 1_000)
    monkeypatch.setattr(module, "JWT_ENCODE", fake_jwt_encode)
    monkeypatch.setattr(
        module,
        "JWT_DECODE",
        fake_jwt_decode_ok,
    )

    token = module.encode_session("alice")
    assert token == "tok"
    assert module.decode_session(token) == "alice"

    monkeypatch.setattr(module, "JWT_DECODE", fake_jwt_decode_bad_exp)
    assert module.decode_session("tok") is None

    monkeypatch.setattr(module, "JWT_DECODE", fake_jwt_decode_expired)
    assert module.decode_session("tok") is None

    monkeypatch.setattr(module, "JWT_DECODE", fake_jwt_decode_missing_sub)
    assert module.decode_session("tok") is None

    req = dummy_request(path="/", args={}, cookies={module.SESSION_COOKIE_NAME: "tok"})
    monkeypatch.setattr(module, "decode_session", fake_decode_session)
    assert module.current_user(req) == "alice"

    class CookieResponse:
        def __init__(self) -> None:
            self.cookie_calls: list[tuple[str, str, int | None]] = []
            self.delete_calls: list[str] = []

        def set_cookie(
            self,
            key: str,
            value: str,
            max_age: int | None = None,
            path: str = "/",
            secure: bool = False,
            httponly: bool = False,
            samesite: str = "Lax",
        ) -> None:
            _ = (path, secure, httponly, samesite)
            self.cookie_calls.append((key, value, max_age))

        def delete_cookie(self, key: str, path: str = "/") -> None:
            _ = path
            self.delete_calls.append(key)

    cookie_response = CookieResponse()
    module.set_login_cookie(cookie_response, "alice")
    module.clear_login_cookie(cookie_response)
    assert cookie_response.cookie_calls[0][0] == module.SESSION_COOKIE_NAME
    assert cookie_response.delete_calls == [
        module.SESSION_COOKIE_NAME,
        module.CSRF_COOKIE_NAME,
    ]

    captured: dict[str, Path | None] = {"metadata": None}

    def fake_ingest_cbz(
        cbz_path: Path, metadata_path: Path | None
    ) -> dict[str, object]:
        captured["metadata"] = metadata_path
        return {"work_id": "w1", "cbz_path": str(cbz_path)}

    monkeypatch.setattr(module, "ingest_cbz", fake_ingest_cbz)
    cbz_upload = UploadLike("upload.cbz", "cbz")
    metadata_upload = UploadLike("meta.json", "{}")

    result_with_metadata = module.save_uploaded_ingest(cbz_upload, metadata_upload)
    assert result_with_metadata["work_id"] == "w1"
    assert captured["metadata"] is not None

    captured["metadata"] = None
    result_without_metadata = module.save_uploaded_ingest(cbz_upload, None)
    assert result_without_metadata["work_id"] == "w1"
    assert captured["metadata"] is None

    page_path = module.page_file_for("w1", "p1.jpg")
    thumb_path = module.thumb_file_for("w1", "t1.jpg")
    assert page_path.parts[-3:] == ("w1", "pages", "p1.jpg")
    assert thumb_path.parts[-3:] == ("w1", "thumbs", "t1.jpg")


def test_log_path_resolution_uses_log_suffix(
    load_route_module: Callable[[str, str], ModuleType],
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/common.py", "common_log_path_suffix_test"
    )

    with_default_template = module._resolve_log_path("logs/%TIMESTAMP%")
    assert with_default_template.suffix == ".log"

    with_blank_template = module._resolve_log_path("   ")
    assert with_blank_template.suffix == ".log"

    with_explicit_suffix = module._resolve_log_path("logs/custom.txt")
    assert with_explicit_suffix.suffix == ".txt"
