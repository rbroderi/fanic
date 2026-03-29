from collections.abc import Callable
from types import ModuleType
from typing import Any
from typing import Protocol


class ResponseLike(Protocol):
    status_code: int
    content_type: str
    headers: dict[str, str]

    def set_data(self, data: str | bytes) -> None: ...


def test_auth_callback_success_uses_session_token_for_userinfo(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: Any,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/account/callback.ex.get.py",
        "fanicsite_account_callback_ex_get_success_test",
    )

    class FakeSettings:
        auth0_configured: bool = True

    class FakeConfig:
        token_endpoint: str = "https://auth.example.com/oauth/token"
        callback_url: str = "https://app.example.com/account/callback"
        userinfo_endpoint: str = "https://auth.example.com/userinfo"

    class FakeUserinfoResponse:
        def json(self) -> dict[str, object]:
            return {
                "sub": "auth0|abc123",
                "email": "person@example.com",
                "email_verified": True,
                "name": "Person Example",
            }

    class FakeClient:
        def __init__(self) -> None:
            self.token: dict[str, object] | None = None

        def fetch_token(
            self,
            endpoint: str,
            *,
            code: str,
            redirect_uri: str,
            code_verifier: str,
        ) -> dict[str, object]:
            _ = (endpoint, code, redirect_uri, code_verifier)
            return {"access_token": "token-123", "token_type": "Bearer"}

        def get(self, endpoint: str) -> FakeUserinfoResponse:
            _ = endpoint
            assert self.token is not None
            return FakeUserinfoResponse()

    fake_client = FakeClient()

    def always_true(_request: object, _response: object) -> bool:
        return True

    def no_op_clear(_response: object) -> None:
        return None

    def no_op_set_login(_response: object, _username: str) -> None:
        return None

    def no_onboarding(_username: str) -> bool:
        return False

    def internal_user_id(**_kwargs: object) -> str:
        return "internal-user-id"

    def fake_config_from_settings(_settings_obj: object) -> FakeConfig:
        return FakeConfig()

    def fake_client_builder(_config_obj: object) -> FakeClient:
        _ = _config_obj
        return fake_client

    def fake_oauth_state(_request_obj: object) -> dict[str, str]:
        _ = _request_obj
        return {
            "state": "state-1",
            "code_verifier": "verifier-1",
            "next_url": "/",
        }

    monkeypatch.setattr(module, "enforce_https_termination", always_true)
    monkeypatch.setattr(module, "get_settings", lambda: FakeSettings())
    monkeypatch.setattr(module, "auth0_config_from_settings", fake_config_from_settings)
    monkeypatch.setattr(module, "build_oauth_client", fake_client_builder)
    monkeypatch.setattr(
        module,
        "read_auth0_oauth_state",
        fake_oauth_state,
    )
    monkeypatch.setattr(module, "clear_auth0_oauth_cookie", no_op_clear)
    monkeypatch.setattr(module, "set_login_cookie", no_op_set_login)
    monkeypatch.setattr(module, "user_requires_onboarding", no_onboarding)
    monkeypatch.setattr(
        module,
        "get_or_create_user_for_auth0_identity",
        internal_user_id,
    )

    request = dummy_request(
        path="/account/callback",
        args={"state": "state-1", "code": "code-1"},
    )
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 303
    assert result.headers["Location"] == "/user/profile"
