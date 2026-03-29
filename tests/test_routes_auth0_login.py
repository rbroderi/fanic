from collections.abc import Callable
from types import ModuleType
from typing import Any
from typing import Protocol


class ResponseLike(Protocol):
    status_code: int
    content_type: str
    headers: dict[str, str]

    def set_data(self, data: str | bytes) -> None: ...


def test_auth0_login_sets_prompt_login(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: Any,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/account/auth0/login.ex.get.py",
        "fanicsite_account_auth0_login_ex_get_prompt_test",
    )

    class FakeSettings:
        auth0_configured: bool = True

    class FakeConfig:
        callback_url: str = "https://fanic.media/account/callback"
        audience: str = ""
        connection: str = "Username-Password-Authentication"
        authorization_endpoint: str = "https://auth.fanic.media/authorize"

    captured: dict[str, object] = {}

    class FakeClient:
        def create_authorization_url(
            self,
            endpoint: str,
            **kwargs: object,
        ) -> tuple[str, str]:
            captured["endpoint"] = endpoint
            captured["kwargs"] = kwargs
            return ("https://auth.fanic.media/authorize?ok=1", "state-1")

    monkeypatch.setattr(module, "enforce_https_termination", lambda _r, _s: True)
    monkeypatch.setattr(module, "get_settings", lambda: FakeSettings())
    monkeypatch.setattr(module, "auth0_config_from_settings", lambda _s: FakeConfig())
    monkeypatch.setattr(module, "build_oauth_client", lambda _c: FakeClient())
    monkeypatch.setattr(module, "new_code_verifier", lambda: "verifier-1")
    monkeypatch.setattr(
        module,
        "set_auth0_oauth_cookie",
        lambda _response, *, state, code_verifier, next_url: None,
    )

    request = dummy_request(path="/account/auth0/login", args={})
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 303
    kwargs = captured["kwargs"]
    assert isinstance(kwargs, dict)
    assert kwargs.get("prompt") == "login"
