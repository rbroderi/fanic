from collections.abc import Callable
from types import ModuleType
from typing import Any
from typing import Protocol


class ResponseLike(Protocol):
    status_code: int
    content_type: str
    headers: dict[str, str]

    def set_data(self, data: str | bytes) -> None: ...


def test_verify_email_get_renders_when_unverified(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: Any,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/account/verify-email.ex.get.py",
        "fanicsite_account_verify_email_ex_get_render_test",
    )

    monkeypatch.setattr(module, "current_user", lambda _request: "alice")
    monkeypatch.setattr(module, "get_auth0_email_verified_for_username", lambda _username: False)
    monkeypatch.setattr(
        module,
        "get_local_user",
        lambda _username: {
            "username": "alice",
            "display_name": "AliceArtist",
            "email": "alice@example.com",
            "is_over_18": None,
            "age_gate_completed": False,
            "role": "user",
            "active": True,
            "created_at": "2026-03-22T00:00:00Z",
        },
    )

    captured: dict[str, str] = {}

    def fake_render_html_template(
        request: Any,
        response: ResponseLike,
        template_name: str,
        replacements: dict[str, str],
    ) -> ResponseLike:
        _ = request
        captured["template"] = template_name
        captured["status"] = replacements["__VERIFY_EMAIL_STATUS__"]
        captured["email"] = replacements["__VERIFY_EMAIL_EMAIL_HINT__"]
        response.status_code = 200
        response.content_type = "text/html; charset=utf-8"
        response.set_data("ok")
        return response

    monkeypatch.setattr(module, "render_html_template", fake_render_html_template)

    request = dummy_request(path="/account/verify-email", args={"msg": "verify-required"})
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 200
    assert captured["template"] == "verify_email.html"
    assert "verify your email address" in captured["status"].lower()
    assert captured["email"] == "alice@example.com"


def test_verify_email_get_redirects_to_onboarding_when_verified(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: Any,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/account/verify-email.ex.get.py",
        "fanicsite_account_verify_email_ex_get_verified_onboarding_test",
    )

    monkeypatch.setattr(module, "current_user", lambda _request: "alice")
    monkeypatch.setattr(module, "get_auth0_email_verified_for_username", lambda _username: True)
    monkeypatch.setattr(module, "user_requires_onboarding", lambda _username: True)

    request = dummy_request(path="/account/verify-email", args={})
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 303
    assert result.headers["Location"] == "/user/onboarding?msg=onboarding-required"


def test_verify_email_post_refresh_redirects_to_check_email_when_still_unverified(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: Any,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/account/verify-email.ex.post.py",
        "fanicsite_account_verify_email_ex_post_unverified_test",
    )

    monkeypatch.setattr(module, "current_user", lambda _request: "alice")
    monkeypatch.setattr(module, "get_auth0_email_verified_for_username", lambda _username: False)

    request = dummy_request(path="/account/verify-email", method="POST", form={})
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 303
    assert result.headers["Location"] == "/account/verify-email?msg=still-unverified"


def test_verify_email_post_refresh_redirects_to_onboarding_when_verified(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: Any,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/account/verify-email.ex.post.py",
        "fanicsite_account_verify_email_ex_post_verified_test",
    )

    monkeypatch.setattr(module, "current_user", lambda _request: "alice")
    monkeypatch.setattr(module, "get_auth0_email_verified_for_username", lambda _username: True)
    monkeypatch.setattr(module, "user_requires_onboarding", lambda _username: True)

    request = dummy_request(path="/account/verify-email", method="POST", form={})
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 303
    assert result.headers["Location"] == "/user/onboarding?msg=onboarding-required"
