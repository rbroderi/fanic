from __future__ import annotations

from collections.abc import Callable
from types import ModuleType
from typing import Any
from typing import Protocol


class ResponseLike(Protocol):
    status_code: int
    content_type: str
    headers: dict[str, str]

    def set_data(self, data: str | bytes) -> None: ...


def _role_user(_: str | None) -> str:
    return "user"


def _role_admin(_: str | None) -> str:
    return "admin"


def test_reports_post_forbidden_for_non_admin(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: Any,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/admin/reports.ex.post.py",
        "fanicsite_reports_ex_post_forbidden_test",
    )

    def always_true(request: Any) -> bool:
        _ = request
        return True

    def fake_current_user(request: Any) -> str:
        _ = request
        return "alice"

    monkeypatch.setattr(module, "enforce_https_termination", always_true)
    monkeypatch.setattr(module, "validate_csrf", always_true)
    monkeypatch.setattr(module, "current_user", fake_current_user)
    monkeypatch.setattr(module, "role_for_user", _role_user)

    request = dummy_request(
        path="/admin/reports",
        method="POST",
        form={"report_id": "1", "report_action": "mark-false"},
    )
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 403


def test_reports_post_marks_report_false_and_preserves_filters(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: Any,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/admin/reports.ex.post.py",
        "fanicsite_reports_ex_post_mark_false_test",
    )

    def always_true(request: Any) -> bool:
        _ = request
        return True

    def fake_current_user(request: Any) -> str:
        _ = request
        return "admin"

    captured: dict[str, object] = {}

    def fake_update_content_report_status(report_id: int, status: str) -> bool:
        captured["report_id"] = report_id
        captured["status"] = status
        return True

    monkeypatch.setattr(module, "enforce_https_termination", always_true)
    monkeypatch.setattr(module, "validate_csrf", always_true)
    monkeypatch.setattr(module, "current_user", fake_current_user)
    monkeypatch.setattr(module, "role_for_user", _role_admin)
    monkeypatch.setattr(
        module,
        "update_content_report_status",
        fake_update_content_report_status,
    )

    request = dummy_request(
        path="/admin/reports",
        method="POST",
        form={
            "report_id": "22",
            "report_action": "mark-false",
            "work_id": "work-2",
            "issue_type": "illegal-content",
            "status": "open",
            "start_date": "2026-03-01",
            "end_date": "2026-03-31",
        },
    )
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 303
    location = result.headers.get("Location", "")
    assert location.startswith("/admin/reports?")
    assert "msg=marked-false" in location
    assert "work_id=work-2" in location
    assert "issue_type=illegal-content" in location
    assert "status=open" in location
    assert captured["report_id"] == 22
    assert captured["status"] == "false-report"


def test_reports_post_remove_redirects_not_found_when_missing(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: Any,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/admin/reports.ex.post.py",
        "fanicsite_reports_ex_post_remove_missing_test",
    )

    def always_true(request: Any) -> bool:
        _ = request
        return True

    def fake_current_user(request: Any) -> str:
        _ = request
        return "admin"

    def fake_delete_content_report(report_id: int) -> bool:
        _ = report_id
        return False

    monkeypatch.setattr(module, "enforce_https_termination", always_true)
    monkeypatch.setattr(module, "validate_csrf", always_true)
    monkeypatch.setattr(module, "current_user", fake_current_user)
    monkeypatch.setattr(module, "role_for_user", _role_admin)
    monkeypatch.setattr(module, "delete_content_report", fake_delete_content_report)

    request = dummy_request(
        path="/admin/reports",
        method="POST",
        form={"report_id": "999", "report_action": "remove"},
    )
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 303
    assert result.headers.get("Location") == "/admin/reports?msg=not-found"


def test_reports_post_marks_report_resolved_and_reopen(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: Any,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/admin/reports.ex.post.py",
        "fanicsite_reports_ex_post_resolve_reopen_test",
    )

    def always_true(request: Any) -> bool:
        _ = request
        return True

    def fake_current_user(request: Any) -> str:
        _ = request
        return "admin"

    statuses: list[str] = []

    def fake_update_content_report_status(report_id: int, status: str) -> bool:
        _ = report_id
        statuses.append(status)
        return True

    monkeypatch.setattr(module, "enforce_https_termination", always_true)
    monkeypatch.setattr(module, "validate_csrf", always_true)
    monkeypatch.setattr(module, "current_user", fake_current_user)
    monkeypatch.setattr(module, "role_for_user", _role_admin)
    monkeypatch.setattr(
        module,
        "update_content_report_status",
        fake_update_content_report_status,
    )

    resolve_request = dummy_request(
        path="/admin/reports",
        method="POST",
        form={"report_id": "7", "report_action": "mark-resolved"},
    )
    resolve_response = dummy_response()
    resolve_result = module.main(resolve_request, resolve_response)
    assert resolve_result.status_code == 303
    assert (
        resolve_result.headers.get("Location") == "/admin/reports?msg=marked-resolved"
    )

    reopen_request = dummy_request(
        path="/admin/reports",
        method="POST",
        form={"report_id": "7", "report_action": "mark-reopen"},
    )
    reopen_response = dummy_response()
    reopen_result = module.main(reopen_request, reopen_response)
    assert reopen_result.status_code == 303
    assert reopen_result.headers.get("Location") == "/admin/reports?msg=marked-reopen"

    assert statuses == ["resolved", "re-open"]


def test_reports_post_promote_explicit_marks_report_resolved(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: Any,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/admin/reports.ex.post.py",
        "fanicsite_reports_ex_post_promote_explicit_test",
    )

    def always_true(request: Any) -> bool:
        _ = request
        return True

    def fake_current_user(request: Any) -> str:
        _ = request
        return "admin"

    captured: dict[str, object] = {}

    def fake_set_work_rating(
        work_id: str,
        rating: str,
        *,
        editor_username: str,
        edited_by_admin: bool,
    ) -> bool:
        captured["work_id"] = work_id
        captured["rating"] = rating
        captured["editor_username"] = editor_username
        captured["edited_by_admin"] = edited_by_admin
        return True

    statuses: list[str] = []

    def fake_update_content_report_status(report_id: int, status: str) -> bool:
        _ = report_id
        statuses.append(status)
        return True

    monkeypatch.setattr(module, "enforce_https_termination", always_true)
    monkeypatch.setattr(module, "validate_csrf", always_true)
    monkeypatch.setattr(module, "current_user", fake_current_user)
    monkeypatch.setattr(module, "role_for_user", _role_admin)
    monkeypatch.setattr(module, "set_work_rating", fake_set_work_rating)
    monkeypatch.setattr(
        module,
        "update_content_report_status",
        fake_update_content_report_status,
    )

    request = dummy_request(
        path="/admin/reports",
        method="POST",
        form={
            "report_id": "11",
            "report_action": "promote-explicit",
            "report_work_id": "work-11",
        },
    )
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 303
    assert result.headers.get("Location") == "/admin/reports?msg=promoted-explicit"
    assert captured["work_id"] == "work-11"
    assert captured["rating"] == "Explicit"
    assert captured["editor_username"] == "admin"
    assert captured["edited_by_admin"] is True
    assert statuses == ["resolved"]
