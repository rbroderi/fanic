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


def _enforce_https_ok(_request: object, _response: object) -> bool:
    return True


def _validate_csrf_ok(_request: object) -> bool:
    return True


def _check_post_rate_limit_ok(_request: object) -> int:
    return 0


def _current_user_alice(_request: object) -> str:
    return "alice"


def _email_unverified(_username: str) -> bool:
    return False


def _email_verified(_username: str) -> bool:
    return True


def _onboarding_required(_username: str) -> bool:
    return True


def _local_user_alice(_username: str) -> dict[str, object]:
    return {
        "username": "alice",
        "display_name": "AliceArtist",
        "email": "alice@example.com",
        "is_over_18": None,
        "age_gate_completed": False,
        "role": "user",
        "active": True,
        "created_at": "2026-03-22T00:00:00Z",
    }


def _allow_secure_get(monkeypatch: pytest.MonkeyPatch, module: ModuleType) -> None:
    monkeypatch.setattr(module, "enforce_https_termination", _enforce_https_ok)


def _allow_secure_post(monkeypatch: pytest.MonkeyPatch, module: ModuleType) -> None:
    _allow_secure_get(monkeypatch, module)
    monkeypatch.setattr(module, "validate_csrf", _validate_csrf_ok)
    monkeypatch.setattr(module, "check_post_rate_limit", _check_post_rate_limit_ok)


def test_verify_email_get_renders_when_unverified(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/account/verify-email.ex.get.py",
        "fanicsite_account_verify_email_ex_get_render_test",
    )
    _allow_secure_get(monkeypatch, module)

    monkeypatch.setattr(module, "current_user", _current_user_alice)
    monkeypatch.setattr(module, "get_auth0_email_verified_for_username", _email_unverified)
    monkeypatch.setattr(module, "get_local_user", _local_user_alice)

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
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/account/verify-email.ex.get.py",
        "fanicsite_account_verify_email_ex_get_verified_onboarding_test",
    )
    _allow_secure_get(monkeypatch, module)

    monkeypatch.setattr(module, "current_user", _current_user_alice)
    monkeypatch.setattr(module, "get_auth0_email_verified_for_username", _email_verified)
    monkeypatch.setattr(module, "user_requires_onboarding", _onboarding_required)

    request = dummy_request(path="/account/verify-email", args={})
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 303
    assert result.headers["Location"] == "/user/onboarding?msg=onboarding-required"


def test_verify_email_post_refresh_redirects_to_check_email_when_still_unverified(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/account/verify-email.ex.post.py",
        "fanicsite_account_verify_email_ex_post_unverified_test",
    )
    _allow_secure_post(monkeypatch, module)

    monkeypatch.setattr(module, "current_user", _current_user_alice)
    monkeypatch.setattr(module, "get_auth0_email_verified_for_username", _email_unverified)

    request = dummy_request(path="/account/verify-email", method="POST", form={})
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 303
    assert result.headers["Location"] == "/account/verify-email?msg=still-unverified"


def test_verify_email_post_refresh_redirects_to_onboarding_when_verified(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/account/verify-email.ex.post.py",
        "fanicsite_account_verify_email_ex_post_verified_test",
    )
    _allow_secure_post(monkeypatch, module)

    monkeypatch.setattr(module, "current_user", _current_user_alice)
    monkeypatch.setattr(module, "get_auth0_email_verified_for_username", _email_verified)
    monkeypatch.setattr(module, "user_requires_onboarding", _onboarding_required)

    request = dummy_request(path="/account/verify-email", method="POST", form={})
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 303
    assert result.headers["Location"] == "/user/onboarding?msg=onboarding-required"
