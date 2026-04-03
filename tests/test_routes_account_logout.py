from collections.abc import Callable
from types import ModuleType
from typing import Any
from typing import Protocol

import pytest


class ResponseLike(Protocol):
    status_code: int
    content_type: str
    headers: dict[str, str]

    def set_data(self, data: str | bytes) -> None: ...


def _clear_cookie(response: ResponseLike) -> None:
    _ = response


def _allow_https(_request: Any, _response: ResponseLike) -> bool:
    return True


def _validate_csrf(_request: Any) -> bool:
    return True


def test_logout_get_redirects_to_auth0_with_logged_out_return_to(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/account/logout.ex.get.py",
        "fanicsite_account_logout_ex_get_test",
    )

    class FakeSettings:
        auth0_configured: bool = True

    class FakeConfig:
        client_id: str = "client-1"
        logout_return_url: str = "https://fanic.media/"
        logout_endpoint: str = "https://auth.fanic.media/v2/logout"

    def fake_get_settings() -> FakeSettings:
        return FakeSettings()

    def fake_auth0_config_from_settings(_settings: FakeSettings) -> FakeConfig:
        return FakeConfig()

    monkeypatch.setattr(module, "clear_login_cookie", _clear_cookie)
    monkeypatch.setattr(module, "clear_auth0_oauth_cookie", _clear_cookie)
    monkeypatch.setattr(module, "get_settings", fake_get_settings)
    monkeypatch.setattr(module, "auth0_config_from_settings", fake_auth0_config_from_settings)

    request = dummy_request(path="/account/logout", method="GET")
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 303
    location = result.headers["Location"]
    assert location.startswith("https://auth.fanic.media/v2/logout?")
    assert "returnTo=https%3A%2F%2Ffanic.media%2Faccount%2Flogged-out" in location


def test_logout_get_redirects_to_logged_out_when_auth0_not_configured(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/account/logout.ex.get.py",
        "fanicsite_account_logout_ex_get_test_no_auth0",
    )

    class FakeSettings:
        auth0_configured: bool = False

    def fake_get_settings() -> FakeSettings:
        return FakeSettings()

    monkeypatch.setattr(module, "clear_login_cookie", _clear_cookie)
    monkeypatch.setattr(module, "clear_auth0_oauth_cookie", _clear_cookie)
    monkeypatch.setattr(module, "get_settings", fake_get_settings)

    request = dummy_request(path="/account/logout", method="GET")
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 303
    assert result.headers["Location"] == "/account/logged-out"


def test_logout_post_redirects_to_auth0_with_logged_out_return_to(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/account/logout.ex.post.py",
        "fanicsite_account_logout_ex_post_test",
    )

    class FakeSettings:
        auth0_configured: bool = True

    class FakeConfig:
        client_id: str = "client-1"
        logout_return_url: str = "https://fanic.media/"
        logout_endpoint: str = "https://auth.fanic.media/v2/logout"

    def fake_get_settings() -> FakeSettings:
        return FakeSettings()

    def fake_auth0_config_from_settings(_settings: FakeSettings) -> FakeConfig:
        return FakeConfig()

    monkeypatch.setattr(module, "enforce_https_termination", _allow_https)
    monkeypatch.setattr(module, "validate_csrf", _validate_csrf)
    monkeypatch.setattr(module, "clear_login_cookie", _clear_cookie)
    monkeypatch.setattr(module, "clear_auth0_oauth_cookie", _clear_cookie)
    monkeypatch.setattr(module, "get_settings", fake_get_settings)
    monkeypatch.setattr(module, "auth0_config_from_settings", fake_auth0_config_from_settings)

    request = dummy_request(path="/account/logout", method="POST")
    request.headers = {"Host": "fanic.media", "X-Forwarded-Proto": "https"}
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 303
    location = result.headers["Location"]
    assert location.startswith("https://auth.fanic.media/v2/logout?")
    assert "returnTo=https%3A%2F%2Ffanic.media%2Faccount%2Flogged-out" in location


def test_logout_post_prefers_configured_return_to_over_request_host(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/account/logout.ex.post.py",
        "fanicsite_account_logout_ex_post_test_prefer_config",
    )

    class FakeSettings:
        auth0_configured: bool = True

    class FakeConfig:
        client_id: str = "client-1"
        logout_return_url: str = "https://fanic.media/account/logged-out"
        logout_endpoint: str = "https://auth.fanic.media/v2/logout"

    def fake_get_settings() -> FakeSettings:
        return FakeSettings()

    def fake_auth0_config_from_settings(_settings: FakeSettings) -> FakeConfig:
        return FakeConfig()

    monkeypatch.setattr(module, "enforce_https_termination", _allow_https)
    monkeypatch.setattr(module, "validate_csrf", _validate_csrf)
    monkeypatch.setattr(module, "clear_login_cookie", _clear_cookie)
    monkeypatch.setattr(module, "clear_auth0_oauth_cookie", _clear_cookie)
    monkeypatch.setattr(module, "get_settings", fake_get_settings)
    monkeypatch.setattr(module, "auth0_config_from_settings", fake_auth0_config_from_settings)

    request = dummy_request(path="/account/logout", method="POST")
    request.headers = {"Host": "127.0.0.1:8000", "X-Forwarded-Proto": "http"}
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 303
    location = result.headers["Location"]
    assert "returnTo=https%3A%2F%2Ffanic.media%2Faccount%2Flogged-out" in location


def test_logged_out_page_renders_template(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/account/logged-out.ex.get.py",
        "fanicsite_account_logged_out_ex_get_test",
    )

    captured: dict[str, str] = {}

    def fake_render_html_template(
        request: Any,
        response: ResponseLike,
        template_name: str,
        replacements: dict[str, str] | None = None,
    ) -> ResponseLike:
        _ = (request, replacements)
        captured["template"] = template_name
        response.status_code = 200
        response.content_type = "text/html; charset=utf-8"
        response.set_data("ok")
        return response

    monkeypatch.setattr(module, "render_html_template", fake_render_html_template)

    request = dummy_request(path="/account/logged-out")
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 200
    assert captured["template"] == "logged-out.html"
