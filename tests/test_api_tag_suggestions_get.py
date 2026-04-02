import json
from collections.abc import Callable
from types import ModuleType
from typing import Any
from typing import Protocol

import pytest


class ResponseLike(Protocol):
    status_code: int
    content_type: str
    data: bytes

    def set_data(self, data: str | bytes) -> None: ...


def test_tag_suggestions_returns_matches(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/api/tag-suggestions.ex.get.py",
        "fanicsite_api_tag_suggestions_get_test",
    )

    monkeypatch.setattr(
        module,
        "list_tag_name_suggestions",
        lambda tag_type, query, limit=12: [
            f"{tag_type}:{query}:one",
            f"{tag_type}:{query}:two",
        ][:limit],
    )

    request = dummy_request(
        path="/api/tag-suggestions",
        args={"type": "freeform", "q": "hurt", "limit": "2"},
    )
    response = dummy_response()
    result = module.main(request, response)

    payload = json.loads(result.data.decode("utf-8"))
    assert result.status_code == 200
    assert payload["type"] == "freeform"
    assert payload["q"] == "hurt"
    assert payload["limit"] == 2
    assert payload["suggestions"] == ["freeform:hurt:one", "freeform:hurt:two"]


def test_tag_suggestions_rejects_invalid_type(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/api/tag-suggestions.ex.get.py",
        "fanicsite_api_tag_suggestions_get_invalid_type_test",
    )

    request = dummy_request(
        path="/api/tag-suggestions",
        args={"type": "not-a-type", "q": "abc"},
    )
    response = dummy_response()
    result = module.main(request, response)

    payload = json.loads(result.data.decode("utf-8"))
    assert result.status_code == 400
    assert payload["detail"] == "invalid tag type"
