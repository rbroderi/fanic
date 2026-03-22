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
        "src/fanic/cylinder_sites/fanicsite/profile.ex.post.py",
        "fanicsite_profile_ex_post_test",
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
        path="/profile",
        method="POST",
        form={"profile_action": "theme", "custom_theme_enabled": "on"},
        files={"theme_toml": upload},
    )
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 303
    assert result.headers["Location"] == "/profile?msg=theme_saved"
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
        "src/fanic/cylinder_sites/fanicsite/profile.ex.get.py",
        "fanicsite_profile_ex_get_test",
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

    def fake_get_user_theme_preference(username: str) -> dict[str, Any]:
        _ = username
        return {"enabled": True, "toml_text": '[dark]\naccent="#b58900"'}

    monkeypatch.setattr(module, "current_user", fake_current_user)
    monkeypatch.setattr(module, "list_works_by_uploader", fake_list_works_by_uploader)
    monkeypatch.setattr(module, "user_prefers_explicit", fake_user_prefers_explicit)
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
        response.status_code = 200
        response.content_type = "text/html; charset=utf-8"
        response.set_data("ok")
        return response

    monkeypatch.setattr(module, "render_html_template", fake_render_html_template)

    request = dummy_request(path="/profile", args={})
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 200
    assert captured["checked"] == "checked"


def test_profile_post_disabling_custom_theme_stops_override_injection(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    post_module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/profile.ex.post.py",
        "fanicsite_profile_ex_post_disable_theme_test",
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
        path="/profile",
        method="POST",
        form={"profile_action": "theme"},
        files={},
    )
    response = dummy_response()
    result = post_module.main(request, response)

    assert result.status_code == 303
    assert result.headers["Location"] == "/profile?msg=theme_saved"
    assert state["enabled"] is False

    get_request = dummy_request(path="/profile", args={})
    assert common_module._custom_theme_style_tag(get_request) == ""
