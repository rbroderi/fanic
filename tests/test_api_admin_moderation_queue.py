import json
from collections.abc import Callable
from types import ModuleType
from typing import Any
from typing import Protocol


class ResponseLike(Protocol):
    status_code: int
    data: bytes

    def set_data(self, data: str | bytes) -> None: ...


def _current_user_admin(_request: object) -> str:
    return "admin-user"


def _current_user_none(_request: object) -> None:
    return None


def _role_admin(_username: object) -> str:
    return "admin"


def _role_user(_username: object) -> str:
    return "user"


def _always_true(*_args: object, **_kwargs: object) -> bool:
    return True


def _queue_items_stub(*, status: str = "pending", limit: int = 200) -> list[dict[str, object]]:
    _ = (status, limit)
    return [
        {
            "id": 7,
            "content_type": "work",
            "content_id": "abc123",
            "uploader_username": "alice",
            "source_member": "page-01.png",
            "reason_type": "explicit",
            "confidence": 0.83,
            "min_threshold": 0.8,
            "max_threshold": 0.9,
            "moderation_json": "{}",
            "status": "pending",
            "created_at": "2026-04-07 00:00:00",
            "reviewed_by": "",
            "reviewed_at": "",
            "review_note": "",
            "content_title": "Demo",
            "content_href": "/comic/abc123",
        }
    ]


def _queue_item_stub(queue_id: int) -> dict[str, object]:
    return {
        "id": queue_id,
        "content_type": "work",
        "content_id": "work-1",
        "uploader_username": "alice",
        "source_member": "page-01.png",
        "reason_type": "explicit",
        "confidence": 0.85,
        "min_threshold": 0.8,
        "max_threshold": 0.9,
        "moderation_json": "{}",
        "status": "pending",
        "created_at": "2026-04-07 00:00:00",
        "reviewed_by": "",
        "reviewed_at": "",
        "review_note": "",
        "content_title": "Demo",
        "content_href": "/comic/work-1",
    }


def _fanart_rating_stub(_item_id: str, _rating: str) -> bool:
    return True


def test_api_admin_moderation_queue_get_requires_admin(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: Any,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/api/admin/moderation-queue.ex.get.py",
        "fanicsite_api_admin_moderation_queue_ex_get_requires_admin_test",
    )

    monkeypatch.setattr(module, "current_user", _current_user_none)
    monkeypatch.setattr(module, "role_for_user", _role_user)

    request = dummy_request(path="/api/admin/moderation-queue", args={})
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 403


def test_api_admin_moderation_queue_get_returns_items(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: Any,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/api/admin/moderation-queue.ex.get.py",
        "fanicsite_api_admin_moderation_queue_ex_get_items_test",
    )

    monkeypatch.setattr(module, "current_user", _current_user_admin)
    monkeypatch.setattr(module, "role_for_user", _role_admin)
    monkeypatch.setattr(module, "list_moderation_review_items", _queue_items_stub)

    request = dummy_request(path="/api/admin/moderation-queue", args={"status": "pending", "limit": "10"})
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 200
    payload = json.loads(result.data.decode("utf-8"))
    assert payload["ok"] is True
    assert payload["count"] == 1
    assert payload["items"][0]["id"] == 7


def test_api_admin_moderation_queue_post_approve_promotes_explicit_work(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: Any,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/api/admin/moderation-queue.ex.post.py",
        "fanicsite_api_admin_moderation_queue_ex_post_approve_work_test",
    )

    promoted: list[tuple[str, str, str, bool]] = []
    updated: list[tuple[int, str, str, str]] = []

    monkeypatch.setattr(module, "enforce_https_termination", _always_true)
    monkeypatch.setattr(module, "validate_csrf", _always_true)
    monkeypatch.setattr(module, "current_user", _current_user_admin)
    monkeypatch.setattr(module, "role_for_user", _role_admin)
    monkeypatch.setattr(module, "get_moderation_review_item", _queue_item_stub)

    def _set_work_rating(work_id: str, rating: str, *, editor_username: str, edited_by_admin: bool) -> bool:
        promoted.append((work_id, rating, editor_username, edited_by_admin))
        return True

    monkeypatch.setattr(module, "set_work_rating", _set_work_rating)
    monkeypatch.setattr(module, "set_fanart_item_rating", _fanart_rating_stub)

    def _update_status(*, queue_id: int, status: str, reviewed_by: str, review_note: str = "") -> bool:
        updated.append((queue_id, status, reviewed_by, review_note))
        return True

    monkeypatch.setattr(module, "update_moderation_review_status", _update_status)

    request = dummy_request(
        path="/api/admin/moderation-queue",
        method="POST",
        form={"queue_id": "7", "action": "approve"},
    )
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 200
    payload = json.loads(result.data.decode("utf-8"))
    assert payload["ok"] is True
    assert payload["status"] == "approved"
    assert promoted == [("work-1", "Explicit", "admin-user", True)]
    assert updated == [(7, "approved", "admin-user", "")]
