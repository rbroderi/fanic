# pyright: reportUnknownLambdaType=false, reportUnknownArgumentType=false

from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any
from typing import Protocol

import pytest

from fanic.media import LocalMediaBackend
from fanic.media import MediaService


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
    module = load_route_module("src/fanic/cylinder_sites/common/responses.py", "common_helpers_test")

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
    responses_module = load_route_module("src/fanic/cylinder_sites/common/responses.py", "common_send_file_test")
    security_module = load_route_module("src/fanic/cylinder_sites/common/security.py", "common_send_file_security_test")

    missing = responses_module.send_file(dummy_response(), tmp_path / "missing.txt")
    assert missing.status_code == 404
    assert missing.data == b"Not found"

    test_file = tmp_path / "demo.txt"
    test_file.write_text("hello", encoding="utf-8")
    sent = responses_module.send_file(dummy_response(), test_file, filename="download.txt")
    assert sent.status_code == 200
    assert sent.data == b"hello"
    assert sent.headers["Content-Disposition"] == 'attachment; filename="download.txt"'

    safe_path = security_module.safe_static_path("styles.css")
    assert safe_path is not None
    assert safe_path.name == "styles.css"

    class _LocalSettings:
        media_base_url: str = "https://fanic.media"
        media_cdn_base_url: str = "https://media.fanic.media"

    security_media_service = MediaService(
        settings=_LocalSettings(),
        backend=LocalMediaBackend(
            works_root=tmp_path / "sec-works",
            fanart_root=tmp_path / "sec-fanart",
        ),
    )
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        security_module,
        "get_media_service",
        lambda: security_media_service,
    )

    fanart_safe_path = security_module.safe_static_path("fanart/images/example.avif")
    assert fanart_safe_path is not None
    assert fanart_safe_path.parts[-2:] == ("images", "example.avif")

    monkeypatch.undo()

    assert security_module.safe_static_path("../../escape.txt") is None
    assert security_module.safe_static_path("fanart/../../escape.txt") is None


def test_route_helpers_and_user_menu(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses_module = load_route_module("src/fanic/cylinder_sites/common/responses.py", "common_route_helpers_test")
    security_module = load_route_module(
        "src/fanic/cylinder_sites/common/security.py",
        "common_route_helpers_security_test",
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

    request = dummy_request(path="/comic/abc", args={})
    assert security_module.path_parts(request) == ["comic", "abc"]
    assert security_module.route_tail(request, ["comic"]) == ["abc"]
    assert security_module.route_tail(request, ["comic", "abc", "extra"]) is None
    assert security_module.route_tail(request, ["reader"]) is None

    monkeypatch.setattr(responses_module, "current_user", fake_current_user_logged_in)
    monkeypatch.setattr(
        responses_module,
        "role_for_user",
        _role_for_alice_or_guest,
    )
    monkeypatch.setattr(
        responses_module,
        "get_local_user",
        lambda _username: {
            "username": "alice",
            "display_name": "AliceDisplay",
            "email": "alice@example.com",
            "is_over_18": True,
            "age_gate_completed": True,
            "role": "user",
            "active": True,
            "created_at": "2026-03-22T00:00:00Z",
        },
    )
    logged_in = responses_module.user_menu_replacements(request)
    assert logged_in["__USER_MENU_LOGIN_HIDDEN_ATTR__"] == "hidden"
    assert logged_in["__USER_MENU_PROFILE_HIDDEN_ATTR__"] == ""
    assert logged_in["__ADMIN_REPORTS_LINK__"] == ""
    assert logged_in["__USER_MENU_STATUS__"] == "Logged in as AliceDisplay."

    monkeypatch.setattr(responses_module, "current_user", fake_current_user_admin)
    monkeypatch.setattr(responses_module, "role_for_user", _role_superadmin)
    logged_in_admin = responses_module.user_menu_replacements(request)
    admin_links_html = logged_in_admin["__ADMIN_REPORTS_LINK__"]
    assert '<a href="/admin/reports">Reports</a>' in admin_links_html
    assert '<a href="/admin/users">Users</a>' in admin_links_html

    monkeypatch.setattr(responses_module, "current_user", fake_current_user_logged_out)
    monkeypatch.setattr(responses_module, "role_for_user", _role_guest)
    logged_out = responses_module.user_menu_replacements(request)
    assert logged_out["__USER_MENU_LOGIN_HIDDEN_ATTR__"] == ""
    assert logged_out["__USER_MENU_PROFILE_HIDDEN_ATTR__"] == "hidden"
    assert logged_out["__ADMIN_REPORTS_LINK__"] == ""


def test_theme_override_parsing_and_style_tag(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_route_module("src/fanic/cylinder_sites/common/responses.py", "common_theme_parse_test")

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
    css_text = module.custom_theme_css_text(req)
    assert "--accent: #268bd2;" in css_text
    assert "--accent: #b58900;" in css_text

    monkeypatch.setattr(
        module,
        "get_user_theme_preference",
        fake_get_theme_preference_invalid,
    )
    assert module.custom_theme_css_text(req) == ""


def test_session_and_upload_helpers(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_module = load_route_module("src/fanic/cylinder_sites/common/session.py", "common_session_upload_test")
    responses_module = load_route_module(
        "src/fanic/cylinder_sites/common/responses.py",
        "common_session_upload_responses_test",
    )

    class _LocalSettings:
        media_base_url: str = "https://fanic.media"
        media_cdn_base_url: str = "https://media.fanic.media"

    local_media_service = MediaService(
        settings=_LocalSettings(),
        backend=LocalMediaBackend(
            works_root=Path("/tmp/fanic-test-works"),
            fanart_root=Path("/tmp/fanic-test-fanart"),
        ),
    )
    monkeypatch.setattr(
        responses_module,
        "get_media_service",
        lambda: local_media_service,
    )

    def fake_jwt_encode(header: object, payload: object, secret: object) -> bytes:
        _ = (header, payload, secret)
        return b"tok"

    def fake_jwt_decode_ok(token: str | bytes, secret: object) -> dict[str, object]:
        _ = (token, secret)
        return {"exp": 1_100, "sub": "alice"}

    def fake_jwt_decode_bad_exp(token: str | bytes, secret: object) -> dict[str, object]:
        _ = (token, secret)
        return {"exp": "x", "sub": "alice"}

    def fake_jwt_decode_expired(token: str | bytes, secret: object) -> dict[str, object]:
        _ = (token, secret)
        return {"exp": 900, "sub": "alice"}

    def fake_jwt_decode_missing_sub(token: str | bytes, secret: object) -> dict[str, object]:
        _ = (token, secret)
        return {"exp": 1_100}

    def fake_decode_session(token: str) -> str:
        _ = token
        return "alice"

    monkeypatch.setattr(session_module.time, "time", lambda: 1_000)
    monkeypatch.setattr(session_module, "JWT_ENCODE", fake_jwt_encode)
    monkeypatch.setattr(
        session_module,
        "JWT_DECODE",
        fake_jwt_decode_ok,
    )

    token = session_module.encode_session("alice")
    assert token == "tok"
    assert session_module.decode_session(token) == "alice"

    monkeypatch.setattr(session_module, "JWT_DECODE", fake_jwt_decode_bad_exp)
    assert session_module.decode_session("tok") is None

    monkeypatch.setattr(session_module, "JWT_DECODE", fake_jwt_decode_expired)
    assert session_module.decode_session("tok") is None

    monkeypatch.setattr(session_module, "JWT_DECODE", fake_jwt_decode_missing_sub)
    assert session_module.decode_session("tok") is None

    req = dummy_request(path="/", args={}, cookies={session_module.SESSION_COOKIE_NAME: "tok"})
    monkeypatch.setattr(session_module, "decode_session", fake_decode_session)
    assert session_module.current_user(req) == "alice"

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
    session_module.set_login_cookie(cookie_response, "alice")
    session_module.clear_login_cookie(cookie_response)
    assert cookie_response.cookie_calls[0][0] == session_module.SESSION_COOKIE_NAME
    assert cookie_response.delete_calls == [
        session_module.SESSION_COOKIE_NAME,
        session_module.CSRF_COOKIE_NAME,
    ]

    captured: dict[str, Path | None] = {"metadata": None}

    def fake_ingest_cbz(cbz_path: Path, metadata_path: Path | None) -> dict[str, object]:
        captured["metadata"] = metadata_path
        return {"work_id": "w1", "cbz_path": str(cbz_path)}

    monkeypatch.setattr(responses_module, "ingest_cbz", fake_ingest_cbz)
    cbz_upload = UploadLike("upload.cbz", "cbz")
    metadata_upload = UploadLike("meta.json", "{}")

    result_with_metadata = responses_module.save_uploaded_ingest(cbz_upload, metadata_upload)
    assert result_with_metadata["work_id"] == "w1"
    assert captured["metadata"] is not None

    captured["metadata"] = None
    result_without_metadata = responses_module.save_uploaded_ingest(cbz_upload, None)
    assert result_without_metadata["work_id"] == "w1"
    assert captured["metadata"] is None

    page_path = responses_module.page_file_for("w1", "p1.jpg")
    thumb_path = responses_module.thumb_file_for("w1", "t1.jpg")
    assert page_path.parts[-3:] == ("w1", "pages", "p1.jpg")
    assert thumb_path.parts[-3:] == ("w1", "thumbs", "t1.jpg")


def test_media_url_prefers_cdn_for_static_paths(
    load_route_module: Callable[[str, str], ModuleType],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_route_module("src/fanic/cylinder_sites/common/responses.py", "common_media_url_cdn_test")

    class _Settings:
        media_base_url: str = "https://fanic.media"
        media_cdn_base_url: str = "https://media.fanic.media"

    media_service = MediaService(
        settings=_Settings(),
        backend=LocalMediaBackend(
            works_root=Path("/tmp/fanic-test-works"),
            fanart_root=Path("/tmp/fanic-test-fanart"),
        ),
    )
    monkeypatch.setattr(module, "get_media_service", lambda: media_service)

    assert module.media_url("/static/work-1/pages/001.avif") == "https://media.fanic.media/static/work-1/pages/001.avif"
    assert (
        module.media_url("static/fanart/thumbs/thumb.avif")
        == "https://media.fanic.media/static/fanart/thumbs/thumb.avif"
    )
    assert module.media_url("/static/logo.png") == "https://fanic.media/static/logo.png"
    assert module.media_url("/fanart/alice") == "https://fanic.media/fanart/alice"
    assert module.media_url("https://example.com/image.avif") == "https://example.com/image.avif"


def test_media_url_uses_media_base_when_cdn_disabled(
    load_route_module: Callable[[str, str], ModuleType],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_route_module("src/fanic/cylinder_sites/common/responses.py", "common_media_url_base_test")

    class _Settings:
        media_base_url: str = "https://fanic.media"
        media_cdn_base_url: str = ""

    media_service = MediaService(
        settings=_Settings(),
        backend=LocalMediaBackend(
            works_root=Path("/tmp/fanic-test-works"),
            fanart_root=Path("/tmp/fanic-test-fanart"),
        ),
    )
    monkeypatch.setattr(module, "get_media_service", lambda: media_service)

    assert module.media_url("/static/work-1/pages/001.avif") == "https://fanic.media/static/work-1/pages/001.avif"


def test_editor_gallery_uses_direct_thumb_src(
    load_route_module: Callable[[str, str], ModuleType],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/editor_gallery.py",
        "editor_gallery_deferred_thumb_test",
    )
    monkeypatch.setattr(module, "list_work_chapter_members", lambda *_: [])

    html = module.render_editor_page_gallery_html(
        "work-1",
        [
            {
                "page_index": 1,
                "image_filename": "_objects/aa/page.avif",
                "thumb_filename": "_objects/aa/thumb.avif",
            }
        ],
        [],
    )

    assert '/static/work-1/thumbs/_objects/aa/thumb.avif"' in html
    assert 'data-thumb-src="' not in html


def test_log_path_resolution_uses_log_suffix(
    load_route_module: Callable[[str, str], ModuleType],
) -> None:
    module = load_route_module(
        "src/fanic/path_utils.py",
        "path_utils_log_path_suffix_test",
    )

    with_default_template = module.resolve_log_path("logs/%TIMESTAMP%")
    assert with_default_template.suffix == ".log"

    with_blank_template = module.resolve_log_path("   ")
    assert with_blank_template.suffix == ".log"

    with_explicit_suffix = module.resolve_log_path("logs/custom.txt")
    assert with_explicit_suffix.suffix == ".txt"


def test_comic_ingest_queue_helpers(
    load_route_module: Callable[[str, str], ModuleType],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/common/rate_limit.py",
        "common_comic_ingest_queue_test",
    )

    monkeypatch.setattr(module, "COMIC_INGEST_MAX_CONCURRENT", 1)
    monkeypatch.setattr(module, "COMIC_INGEST_QUEUE_WAIT_SECONDS", 0)
    monkeypatch.setattr(module._comic_ingest_state, "active", 0)
    monkeypatch.setattr(module._comic_ingest_state, "waiting", 0)

    seen_positions: list[int] = []

    def capture_queue_position(position: int) -> None:
        seen_positions.append(position)

    first_session = module.begin_comic_ingest_session(
        wait_timeout_seconds=0,
    )
    assert first_session.allowed is True
    assert first_session.retry_after == 0
    assert first_session.queue_position == 0

    second_session = module.begin_comic_ingest_session(
        wait_timeout_seconds=0,
        on_queued=capture_queue_position,
    )
    assert second_session.allowed is False
    assert second_session.retry_after == 1
    assert second_session.queue_position == 1
    assert seen_positions == [1]

    module.end_comic_ingest_session()

    third_session = module.begin_comic_ingest_session(
        wait_timeout_seconds=0,
    )
    assert third_session.allowed is True
    assert third_session.retry_after == 0
    assert third_session.queue_position == 0

    module.end_comic_ingest_session()
