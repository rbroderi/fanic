from __future__ import annotations

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


def _none_user(_: Any) -> None:
    return None


def _alice_user(_: Any) -> str:
    return "alice"


def _always_https(req: Any, res: Any) -> bool:
    _ = (req, res)
    return True


def _always_valid_csrf(req: Any) -> bool:
    _ = req
    return True


def _mark_read_true(username: str, notification_id: int) -> bool:
    _ = (username, notification_id)
    return True


def _delete_true(username: str, notification_id: int) -> bool:
    _ = (username, notification_id)
    return True


def _mark_all_one(username: str) -> int:
    _ = username
    return 1


def _sample_notifications(
    username: str, *, limit: int = 200
) -> list[dict[str, object]]:
    _ = limit
    return [
        {
            "id": 1,
            "username": username,
            "actor_username": "bob",
            "work_id": "work-1",
            "kind": "comment",
            "message": "bob commented.",
            "href": "/works/work-1",
            "is_read": False,
            "created_at": "2026-03-23 00:00:00",
        }
    ]


def test_notification_get_requires_login(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/user/notifications.ex.get.py",
        "fanicsite_user_notifications_ex_get_login_required_test",
    )

    monkeypatch.setattr(module, "current_user", _none_user)

    captured: dict[str, str] = {}

    def fake_render_html_template(
        request: Any,
        response: ResponseLike,
        template_name: str,
        replacements: dict[str, str],
    ) -> ResponseLike:
        _ = request
        captured["template"] = template_name
        captured["status"] = replacements["__NOTIFICATION_STATUS__"]
        response.status_code = 200
        response.content_type = "text/html; charset=utf-8"
        response.set_data("ok")
        return response

    monkeypatch.setattr(module, "render_html_template", fake_render_html_template)

    request = dummy_request(path="/user/notifications", args={})
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 200
    assert captured["template"] == "notification.html"
    assert "Login required" in captured["status"]


def test_notification_get_renders_items(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/user/notifications.ex.get.py",
        "fanicsite_user_notifications_ex_get_items_test",
    )

    monkeypatch.setattr(module, "current_user", _alice_user)
    monkeypatch.setattr(module, "list_user_notifications", _sample_notifications)

    captured: dict[str, str] = {}

    def fake_render_html_template(
        request: Any,
        response: ResponseLike,
        template_name: str,
        replacements: dict[str, str],
    ) -> ResponseLike:
        _ = (request, template_name)
        captured["unread"] = replacements["__NOTIFICATION_UNREAD_COUNT__"]
        captured["items"] = replacements["__NOTIFICATION_ITEMS_HTML__"]
        response.status_code = 200
        response.content_type = "text/html; charset=utf-8"
        response.set_data("ok")
        return response

    monkeypatch.setattr(module, "render_html_template", fake_render_html_template)

    request = dummy_request(path="/user/notifications", args={})
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 200
    assert captured["unread"] == "1"
    assert "bob commented." in captured["items"]


def test_notification_post_actions_redirect(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/user/notifications.ex.post.py",
        "fanicsite_user_notifications_ex_post_actions_test",
    )

    monkeypatch.setattr(module, "enforce_https_termination", _always_https)
    monkeypatch.setattr(module, "validate_csrf", _always_valid_csrf)
    monkeypatch.setattr(module, "current_user", _alice_user)
    monkeypatch.setattr(module, "mark_notification_read", _mark_read_true)
    monkeypatch.setattr(module, "delete_notification", _delete_true)
    monkeypatch.setattr(module, "mark_all_notifications_read", _mark_all_one)

    request_mark = dummy_request(
        path="/user/notifications",
        method="POST",
        form={"notification_action": "mark-read", "notification_id": "1"},
    )
    response_mark = dummy_response()
    result_mark = module.main(request_mark, response_mark)
    assert result_mark.status_code == 303
    assert result_mark.headers["Location"] == "/user/notifications?msg=updated"

    request_delete = dummy_request(
        path="/user/notifications",
        method="POST",
        form={"notification_action": "delete", "notification_id": "1"},
    )
    response_delete = dummy_response()
    result_delete = module.main(request_delete, response_delete)
    assert result_delete.status_code == 303
    assert result_delete.headers["Location"] == "/user/notifications?msg=updated"

    request_all = dummy_request(
        path="/user/notifications",
        method="POST",
        form={"notification_action": "mark-all-read"},
    )
    response_all = dummy_response()
    result_all = module.main(request_all, response_all)
    assert result_all.status_code == 303
    assert result_all.headers["Location"] == "/user/notifications?msg=cleared"
