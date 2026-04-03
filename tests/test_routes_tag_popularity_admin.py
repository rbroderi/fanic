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


def _role_user(_: str | None) -> str:
    return "user"


def _role_admin(_: str | None) -> str:
    return "admin"


def _current_user_alice(_request: object) -> str:
    return "alice"


def _current_user_admin(_request: object) -> str:
    return "admin"


def _tag_popularity_rows(**_kwargs: object) -> list[dict[str, object]]:
    return [
        {
            "tag_id": 1,
            "slug": "adventure",
            "name": "Adventure",
            "type": "freeform",
            "attached_works": 4,
            "seed_count": 100,
            "usage_count": 20,
            "effective_popularity": 120,
        }
    ]


def test_tag_popularity_route_forbidden_for_non_admin(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/admin/tag-popularity.ex.get.py",
        "fanicsite_tag_popularity_forbidden_test",
    )

    monkeypatch.setattr(module, "current_user", _current_user_alice)
    monkeypatch.setattr(module, "role_for_user", _role_user)

    request = dummy_request(path="/admin/tag-popularity", args={})
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 403


def test_tag_popularity_route_renders_rows_for_admin(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/admin/tag-popularity.ex.get.py",
        "fanicsite_tag_popularity_admin_test",
    )

    monkeypatch.setattr(module, "current_user", _current_user_admin)
    monkeypatch.setattr(module, "role_for_user", _role_admin)
    monkeypatch.setattr(module, "list_top_tag_popularity", _tag_popularity_rows)

    captured: dict[str, str] = {}

    def fake_render_html_template(
        request: Any,
        response: ResponseLike,
        template_name: str,
        replacements: dict[str, str],
    ) -> ResponseLike:
        _ = request
        captured["template"] = template_name
        captured["count"] = replacements["__TAG_POPULARITY_COUNT__"]
        captured["rows"] = replacements["__TAG_POPULARITY_ROWS_HTML__"]
        response.status_code = 200
        response.content_type = "text/html; charset=utf-8"
        response.set_data("ok")
        return response

    monkeypatch.setattr(module, "render_html_template", fake_render_html_template)

    request = dummy_request(
        path="/admin/tag-popularity",
        args={"type": "freeform", "q": "adv", "limit": "10"},
    )
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 200
    assert captured["template"] == "tag-popularity-admin.html"
    assert captured["count"] == "1"
    assert "Adventure" in captured["rows"]
    assert "120" in captured["rows"]
