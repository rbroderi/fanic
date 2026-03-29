from collections.abc import Callable
from types import ModuleType
from typing import Any
from typing import Protocol


class ResponseLike(Protocol):
    status_code: int
    content_type: str
    data: bytes
    headers: dict[str, str]

    def set_data(self, data: str | bytes) -> None: ...


def test_api_works_post_bookmark_persists_for_logged_in_user(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: Any,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/api/comic.ex.post.py",
        "fanicsite_api_works_ex_post_bookmark_test",
    )

    captured: dict[str, object] = {}

    def fake_upsert_user_bookmark(
        username: str,
        work_id: str,
        *,
        page_index: int,
        message: str,
    ) -> bool:
        captured["username"] = username
        captured["work_id"] = work_id
        captured["page_index"] = page_index
        captured["message"] = message
        return True

    monkeypatch.setattr(module, "upsert_user_bookmark", fake_upsert_user_bookmark)

    request = dummy_request(
        path="/api/comic/work-123/bookmark",
        method="POST",
        form={
            "user_id": "alice",
            "page_index": "9",
            "message": "Loved this chapter.",
        },
    )
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 200
    assert captured["username"] == "alice"
    assert captured["work_id"] == "work-123"
    assert captured["page_index"] == 9
    assert captured["message"] == "Loved this chapter."


def test_api_works_post_bookmark_requires_authentication(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/api/comic.ex.post.py",
        "fanicsite_api_works_ex_post_bookmark_auth_test",
    )

    request = dummy_request(
        path="/api/comic/work-123/bookmark",
        method="POST",
        form={
            "user_id": "anon",
            "message": "note",
        },
    )
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 401
