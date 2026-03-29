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


def _always_https(req: Any, res: Any) -> bool:
    _ = (req, res)
    return True


def _always_valid_csrf(req: Any) -> bool:
    _ = req
    return True


def _bob_user(_: Any) -> str:
    return "bob"


def _role_user(_: str | None) -> str:
    return "user"


def _work_sample(work_id: str) -> dict[str, object]:
    return {
        "id": work_id,
        "title": "Example Work",
        "uploader_username": "alice",
        "rating": "Not Rated",
        "page_count": 5,
    }


def _can_view(_username: str | None, _work: dict[str, object]) -> bool:
    return True


def _kudo_inserted(_work_id: str, _username: str) -> bool:
    return True


def _add_comment(
    _work_id: str,
    _username: str,
    _body: str,
    chapter_number: int | None = None,
) -> None:
    _ = chapter_number


def test_works_post_kudos_creates_notification_for_uploader(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/comic.ex.post.py",
        "fanicsite_works_ex_post_kudos_notification_test",
    )

    monkeypatch.setattr(module, "enforce_https_termination", _always_https)
    monkeypatch.setattr(module, "validate_csrf", _always_valid_csrf)
    monkeypatch.setattr(module, "current_user", _bob_user)
    monkeypatch.setattr(module, "role_for_user", _role_user)
    monkeypatch.setattr(module, "get_work", _work_sample)
    monkeypatch.setattr(module, "can_view_work", _can_view)
    monkeypatch.setattr(module, "add_work_kudo", _kudo_inserted)

    captured: dict[str, str] = {}

    def fake_create_notification(
        username: str,
        *,
        actor_username: str,
        work_id: str | None,
        kind: str,
        message: str,
        href: str,
    ) -> int:
        _ = work_id
        captured["username"] = username
        captured["actor"] = actor_username
        captured["kind"] = kind
        captured["message"] = message
        captured["href"] = href
        return 1

    monkeypatch.setattr(module, "create_notification", fake_create_notification)

    request = dummy_request(path="/comic/work-1/kudos", method="POST", form={})
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 303
    assert result.headers["Location"] == "/comic/work-1?msg=kudos-saved"
    assert captured["username"] == "alice"
    assert captured["actor"] == "bob"
    assert captured["kind"] == "kudo"
    assert captured["href"] == "/comic/work-1"


def test_works_post_comment_creates_notification_for_uploader(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/comic.ex.post.py",
        "fanicsite_works_ex_post_comment_notification_test",
    )

    monkeypatch.setattr(module, "enforce_https_termination", _always_https)
    monkeypatch.setattr(module, "validate_csrf", _always_valid_csrf)
    monkeypatch.setattr(module, "current_user", _bob_user)
    monkeypatch.setattr(module, "role_for_user", _role_user)
    monkeypatch.setattr(module, "get_work", _work_sample)
    monkeypatch.setattr(module, "can_view_work", _can_view)
    monkeypatch.setattr(module, "add_work_comment", _add_comment)

    captured: dict[str, str] = {}

    def fake_create_notification(
        username: str,
        *,
        actor_username: str,
        work_id: str | None,
        kind: str,
        message: str,
        href: str,
    ) -> int:
        _ = work_id
        captured["username"] = username
        captured["actor"] = actor_username
        captured["kind"] = kind
        captured["message"] = message
        captured["href"] = href
        return 1

    monkeypatch.setattr(module, "create_notification", fake_create_notification)

    request = dummy_request(
        path="/comic/work-1/comments",
        method="POST",
        form={"comment_body": "Great chapter", "chapter_number": "2"},
    )
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 303
    assert result.headers["Location"] == "/comic/work-1?msg=comment-saved"
    assert captured["username"] == "alice"
    assert captured["actor"] == "bob"
    assert captured["kind"] == "comment"
    assert "chapter 2" in captured["message"]
    assert captured["href"] == "/comic/work-1"
