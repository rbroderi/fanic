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

    def set_data(self, data: str | bytes) -> None: ...


class DummyUpload:
    def __init__(self, filename: str, content: str) -> None:
        self.filename: str = filename
        self._content: str = content

    def save(self, dst: str | Path) -> None:
        Path(dst).write_text(self._content, encoding="utf-8")


def test_profile_post_saves_theme_toml(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/user/profile.ex.post.py",
        "fanicsite_user_profile_ex_post_test",
    )

    def fake_current_user(request: Any) -> str:
        _ = request
        return "alice"

    monkeypatch.setattr(module, "current_user", fake_current_user)

    saved: dict[str, object] = {}

    def fake_set_user_theme_preference(
        username: str,
        *,
        enabled: bool,
        toml_text: str,
    ) -> None:
        saved["username"] = username
        saved["enabled"] = enabled
        saved["toml_text"] = toml_text

    monkeypatch.setattr(
        module, "set_user_theme_preference", fake_set_user_theme_preference
    )

    upload = DummyUpload("theme.toml", '[dark]\naccent = "#268bd2"\n')
    request = dummy_request(
        path="/user/profile",
        method="POST",
        form={"profile_action": "theme", "custom_theme_enabled": "on"},
        files={"theme_toml": upload},
    )
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 303
    assert result.headers["Location"] == "/user/profile?msg=theme_saved"
    assert saved["username"] == "alice"
    assert saved["enabled"] is True
    assert isinstance(saved["toml_text"], str)
    assert "[dark]" in str(saved["toml_text"])


def test_profile_get_marks_custom_theme_checked(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/user/profile.ex.get.py",
        "fanicsite_user_profile_ex_get_test",
    )

    def fake_current_user(request: Any) -> str:
        _ = request
        return "alice"

    def fake_list_works_by_uploader(username: str) -> list[dict[str, Any]]:
        _ = username
        return []

    def fake_user_prefers_explicit(username: str) -> bool:
        _ = username
        return False

    def fake_user_prefers_mature(username: str) -> bool:
        _ = username
        return True

    def fake_get_user_theme_preference(username: str) -> dict[str, Any]:
        _ = username
        return {"enabled": True, "toml_text": '[dark]\naccent="#b58900"'}

    class FakeSettings:
        profile_history_limit: int = 7

    def fake_list_recent_reading_history(
        user_id: str,
        *,
        limit: int,
    ) -> list[dict[str, Any]]:
        _ = (user_id, limit)
        return []

    def fake_list_user_bookmarks(username: str) -> list[dict[str, Any]]:
        _ = username
        return []

    def fake_list_fanart_items_by_uploader(
        username: str,
        *,
        limit: int = 30,
    ) -> list[dict[str, Any]]:
        _ = (username, limit)
        return []

    def fake_can_view_work(username: str | None, work: dict[str, Any]) -> bool:
        _ = (username, work)
        return True

    monkeypatch.setattr(module, "current_user", fake_current_user)
    monkeypatch.setattr(module, "list_works_by_uploader", fake_list_works_by_uploader)
    monkeypatch.setattr(module, "user_prefers_mature", fake_user_prefers_mature)
    monkeypatch.setattr(module, "user_prefers_explicit", fake_user_prefers_explicit)
    monkeypatch.setattr(module, "get_settings", lambda: FakeSettings())
    monkeypatch.setattr(
        module,
        "list_recent_reading_history",
        fake_list_recent_reading_history,
    )
    monkeypatch.setattr(module, "list_user_bookmarks", fake_list_user_bookmarks)
    monkeypatch.setattr(
        module,
        "list_fanart_items_by_uploader",
        fake_list_fanart_items_by_uploader,
    )
    monkeypatch.setattr(module, "can_view_work", fake_can_view_work)
    monkeypatch.setattr(
        module,
        "get_user_theme_preference",
        fake_get_user_theme_preference,
    )

    captured: dict[str, str] = {}

    def fake_render_html_template(
        request: Any,
        response: ResponseLike,
        template_name: str,
        replacements: dict[str, str],
    ) -> ResponseLike:
        _ = (request, template_name)
        captured["checked"] = replacements[
            "__PROFILE_CUSTOM_THEME_ENABLED_CHECKED_ATTR__"
        ]
        captured["mature_checked"] = replacements[
            "__PROFILE_VIEW_MATURE_CHECKED_ATTR__"
        ]
        captured["settings_hidden"] = replacements["__PROFILE_SETTINGS_HIDDEN_ATTR__"]
        captured["public_link_hidden"] = replacements[
            "__PROFILE_PUBLIC_LINK_HIDDEN_ATTR__"
        ]
        captured["history_hidden"] = replacements["__PROFILE_HISTORY_HIDDEN_ATTR__"]
        response.status_code = 200
        response.content_type = "text/html; charset=utf-8"
        response.set_data("ok")
        return response

    monkeypatch.setattr(module, "render_html_template", fake_render_html_template)

    request = dummy_request(path="/user/profile", args={})
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 200
    assert captured["checked"] == "checked"
    assert captured["mature_checked"] == "checked"
    assert captured["settings_hidden"] == ""
    assert captured["public_link_hidden"] == ""
    assert captured["history_hidden"] == ""


def test_users_public_profile_uses_public_template(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    route_module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/users.ex.get.py",
        "fanicsite_users_ex_get_public_profile_test",
    )
    handler_module = route_module.ex_get_handler

    def fake_current_user(request: Any) -> str:
        _ = request
        return "admin"

    def fake_list_works_by_uploader(username: str) -> list[dict[str, Any]]:
        _ = username
        return []

    def fake_list_user_bookmarks(username: str) -> list[dict[str, Any]]:
        _ = username
        return []

    def fake_list_fanart_items_by_uploader(
        username: str,
        *,
        limit: int = 30,
    ) -> list[dict[str, Any]]:
        _ = (username, limit)
        return []

    def fake_can_view_work(username: str | None, work: dict[str, Any]) -> bool:
        _ = (username, work)
        return True

    monkeypatch.setattr(handler_module, "current_user", fake_current_user)
    monkeypatch.setattr(
        handler_module, "list_works_by_uploader", fake_list_works_by_uploader
    )
    monkeypatch.setattr(handler_module, "list_user_bookmarks", fake_list_user_bookmarks)
    monkeypatch.setattr(
        handler_module,
        "list_fanart_items_by_uploader",
        fake_list_fanart_items_by_uploader,
    )
    monkeypatch.setattr(handler_module, "can_view_work", fake_can_view_work)

    captured: dict[str, str] = {}

    def fake_render_html_template(
        request: Any,
        response: ResponseLike,
        template_name: str,
        replacements: dict[str, str],
    ) -> ResponseLike:
        _ = request
        captured["template"] = template_name
        captured["has_settings_marker"] = str(
            "__PROFILE_SETTINGS_HIDDEN_ATTR__" in replacements
        )
        captured["has_prefs_marker"] = str(
            "__PROFILE_PREFS_HIDDEN_ATTR__" in replacements
        )
        captured["has_public_link_marker"] = str(
            "__PROFILE_PUBLIC_LINK_HIDDEN_ATTR__" in replacements
        )
        response.status_code = 200
        response.content_type = "text/html; charset=utf-8"
        response.set_data("ok")
        return response

    monkeypatch.setattr(
        handler_module, "render_html_template", fake_render_html_template
    )

    request = dummy_request(path="/users/admin", args={})
    response = dummy_response()
    result = route_module.main(request, response)

    assert result.status_code == 200
    assert captured["template"] == "profile-public.html"
    assert captured["has_public_link_marker"] == "False"
    assert captured["has_settings_marker"] == "False"
    assert captured["has_prefs_marker"] == "False"


def test_profile_post_disabling_custom_theme_stops_override_injection(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    post_module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/user/profile.ex.post.py",
        "fanicsite_user_profile_ex_post_disable_theme_test",
    )
    common_module = load_route_module(
        "src/fanic/cylinder_sites/common.py",
        "fanicsite_common_disable_theme_test",
    )

    state: dict[str, object] = {
        "enabled": True,
        "toml_text": '[light]\naccent = "#268bd2"\n',
    }

    def fake_current_user(request: Any) -> str:
        _ = request
        return "alice"

    def fake_set_user_theme_preference(
        username: str,
        *,
        enabled: bool,
        toml_text: str | None,
    ) -> None:
        _ = username
        state["enabled"] = enabled
        state["toml_text"] = toml_text if toml_text is not None else state["toml_text"]

    def fake_get_user_theme_preference(username: str) -> dict[str, object]:
        _ = username
        return {
            "enabled": bool(state["enabled"]),
            "toml_text": str(state["toml_text"]),
        }

    monkeypatch.setattr(post_module, "current_user", fake_current_user)
    monkeypatch.setattr(
        post_module,
        "set_user_theme_preference",
        fake_set_user_theme_preference,
    )
    monkeypatch.setattr(common_module, "current_user", fake_current_user)
    monkeypatch.setattr(
        common_module,
        "get_user_theme_preference",
        fake_get_user_theme_preference,
    )

    request = dummy_request(
        path="/user/profile",
        method="POST",
        form={"profile_action": "theme"},
        files={},
    )
    response = dummy_response()
    result = post_module.main(request, response)

    assert result.status_code == 303
    assert result.headers["Location"] == "/user/profile?msg=theme_saved"
    assert state["enabled"] is False

    get_request = dummy_request(path="/user/profile", args={})
    assert common_module._custom_theme_style_tag(get_request) == ""
