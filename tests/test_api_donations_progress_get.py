import json
from collections.abc import Callable
from types import ModuleType
from typing import Any
from typing import Protocol

import pytest


class ResponseLike(Protocol):
    status_code: int
    data: bytes

    def set_data(self, data: str | bytes) -> None: ...


def test_api_donations_progress_not_found(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/api/donations-progress.ex.get.py",
        "fanicsite_api_donations_progress_not_found_test",
    )

    request = dummy_request(path="/api/not-donations-progress")
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 404


def test_api_donations_progress_sums_supporter_amounts(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/api/donations-progress.ex.get.py",
        "fanicsite_api_donations_progress_sum_test",
    )

    class _DummySettings:
        buymeacoffee_api_key: str = "test-api-key"  # pragma: allowlist secret
        buymeacoffee_api_url: str = "https://example.invalid/supporters"
        buymeacoffee_goal_amount: float = 100.0

    class _DummyResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "data": [
                    {"support_coffees": "2", "support_coffee_price": "5"},
                    {"support_amount": "7.5"},
                ]
            }

    def _fake_requests_get(*_args: object, **_kwargs: object) -> _DummyResponse:
        return _DummyResponse()

    monkeypatch.setattr(module, "get_settings", lambda: _DummySettings())
    monkeypatch.setattr(module.requests, "get", _fake_requests_get)

    request = dummy_request(path="/api/donations-progress")
    response = dummy_response()
    result = module.main(request, response)
    payload = json.loads(result.data.decode("utf-8"))

    assert result.status_code == 200
    assert payload["ok"] is True
    assert payload["current_total"] == 17.5
    assert payload["goal_total"] == 100.0
    assert payload["progress_ratio"] == 0.175


def test_api_donations_progress_disabled_without_api_key(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/api/donations-progress.ex.get.py",
        "fanicsite_api_donations_progress_disabled_test",
    )

    class _DummySettings:
        buymeacoffee_api_key: str = ""
        buymeacoffee_api_url: str = "https://example.invalid/supporters"
        buymeacoffee_goal_amount: float = 250.0

    monkeypatch.setattr(module, "get_settings", lambda: _DummySettings())

    request = dummy_request(path="/api/donations-progress")
    response = dummy_response()
    result = module.main(request, response)
    payload = json.loads(result.data.decode("utf-8"))

    assert result.status_code == 200
    assert payload["ok"] is True
    assert payload["source"] == "disabled"
    assert payload["goal_total"] == 250.0
