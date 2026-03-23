from __future__ import annotations

from collections.abc import Callable
from types import ModuleType
from typing import Any
from typing import Protocol

import pytest


class ResponseLike(Protocol):
    data: bytes
    status_code: int

    def set_data(self, data: str | bytes) -> None: ...


def test_render_html_template_injects_custom_theme_style(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/common.py",
        "fanicsite_common_test",
    )

    def fake_current_user(request: Any) -> str:
        _ = request
        return "alice"

    def fake_get_user_theme_preference(username: str) -> dict[str, Any]:
        _ = username
        return {
            "enabled": True,
            "toml_text": '[light]\naccent="#268bd2"\n[dark]\naccent="#b58900"\n',
        }

    monkeypatch.setattr(module, "current_user", fake_current_user)
    monkeypatch.setattr(
        module,
        "get_user_theme_preference",
        fake_get_user_theme_preference,
    )

    request = dummy_request(path="/user/profile", args={})
    response = dummy_response()
    render_html_template: Callable[
        [Any, ResponseLike, str, dict[str, str]], ResponseLike
    ] = module.render_html_template
    result = render_html_template(request, response, "profile.html", {})

    html = result.data.decode("utf-8")
    assert result.status_code == 200
    assert "customThemeOverrides" in html
    assert "--accent: #268bd2;" in html
    assert "--accent: #b58900;" in html
