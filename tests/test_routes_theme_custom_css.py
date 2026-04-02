from collections.abc import Callable
from types import ModuleType
from typing import Any
from typing import Protocol

import pytest

import fanic.cylinder_sites.common.responses as common_module


class ResponseLike(Protocol):
    status_code: int
    content_type: str
    headers: dict[str, str]
    data: bytes

    def set_data(self, data: str | bytes) -> None: ...


def test_theme_custom_css_returns_css_for_enabled_theme(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/theme/custom.css.ex.get.py",
        "fanicsite_theme_custom_css_ex_get_enabled_test",
    )

    def fake_current_user(_request: Any) -> str:
        return "alice"

    def fake_get_user_theme_preference(_username: str) -> dict[str, Any]:
        return {
            "enabled": True,
            "toml_text": '[light]\naccent="#268bd2"\n[dark]\naccent="#b58900"\n',
        }

    monkeypatch.setattr(common_module, "current_user", fake_current_user)
    monkeypatch.setattr(common_module, "get_user_theme_preference", fake_get_user_theme_preference)

    request = dummy_request(path="/theme/custom.css", args={})
    response = dummy_response()

    result = module.main(request, response)
    css_text = result.data.decode("utf-8")

    assert result.status_code == 200
    assert result.content_type == "text/css; charset=utf-8"
    assert result.headers["Cache-Control"] == "private, no-store"
    assert "--accent: #268bd2;" in css_text
    assert "--accent: #b58900;" in css_text


def test_theme_custom_css_returns_empty_for_disabled_theme(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/theme/custom.css.ex.get.py",
        "fanicsite_theme_custom_css_ex_get_disabled_test",
    )

    def fake_current_user(_request: Any) -> str:
        return "alice"

    def fake_get_user_theme_preference(_username: str) -> dict[str, Any]:
        return {
            "enabled": False,
            "toml_text": '[light]\naccent="#268bd2"\n',
        }

    monkeypatch.setattr(common_module, "current_user", fake_current_user)
    monkeypatch.setattr(common_module, "get_user_theme_preference", fake_get_user_theme_preference)

    request = dummy_request(path="/theme/custom.css", args={})
    response = dummy_response()

    result = module.main(request, response)

    assert result.status_code == 200
    assert result.content_type == "text/css; charset=utf-8"
    assert result.headers["Cache-Control"] == "private, no-store"
    assert result.data.decode("utf-8") == ""
