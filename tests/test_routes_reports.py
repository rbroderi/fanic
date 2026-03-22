from __future__ import annotations

from collections.abc import Callable
from types import ModuleType
from typing import Any
from typing import Protocol


class ResponseLike(Protocol):
    status_code: int
    content_type: str
    data: bytes

    def set_data(self, data: str | bytes) -> None: ...


def test_reports_route_forbidden_for_non_admin(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: Any,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/reports.ex.get.py",
        "fanicsite_reports_ex_get_forbidden_test",
    )

    def fake_current_user(request: Any) -> str:
        _ = request
        return "alice"

    monkeypatch.setattr(module, "current_user", fake_current_user)

    request = dummy_request(path="/reports", args={})
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 403


def test_reports_route_renders_report_rows_for_admin(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: Any,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/reports.ex.get.py",
        "fanicsite_reports_ex_get_admin_test",
    )

    def fake_current_user(request: Any) -> str:
        _ = request
        return module.ADMIN_USERNAME

    def fake_list_content_reports(
        *,
        work_id: str,
        issue_type: str,
        status: str,
        start_date: str,
        end_date: str,
        limit: int = 250,
    ) -> list[dict[str, object]]:
        _ = (work_id, issue_type, status, start_date, end_date, limit)
        return [
            {
                "id": 1,
                "work_id": "work-1",
                "work_title": "Sample Work",
                "issue_type": "illegal-content",
                "status": "resolved",
                "reason": "Illegal content",
                "reporter_name": "Reporter",
                "reporter_email": "reporter@example.com",
                "claimed_url": "https://example.test/works/work-1",
                "evidence_url": "",
                "details": "This appears illegal.",
                "reporter_username": "alice",
                "source_path": "/dmca",
                "created_at": "2026-03-22 16:00:00",
            }
        ]

    captured: dict[str, str] = {}

    def fake_render_html_template(
        request: Any,
        response: ResponseLike,
        template_name: str,
        replacements: dict[str, str],
    ) -> ResponseLike:
        _ = request
        captured["template"] = template_name
        captured["count"] = replacements["__REPORT_COUNT__"]
        captured["rows"] = replacements["__REPORT_ROWS_HTML__"]
        captured["options"] = replacements["__REPORT_ISSUE_OPTIONS_HTML__"]
        captured["status_options"] = replacements["__REPORT_STATUS_OPTIONS_HTML__"]
        response.status_code = 200
        response.content_type = "text/html; charset=utf-8"
        response.set_data("ok")
        return response

    monkeypatch.setattr(module, "current_user", fake_current_user)
    monkeypatch.setattr(module, "list_content_reports", fake_list_content_reports)
    monkeypatch.setattr(module, "render_html_template", fake_render_html_template)

    request = dummy_request(
        path="/reports",
        args={
            "work_id": "work-1",
            "issue_type": "illegal-content",
            "status": "resolved",
            "start_date": "2026-03-01",
            "end_date": "2026-03-31",
        },
    )
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 200
    assert captured["template"] == "reports.html"
    assert captured["count"] == "1"
    assert "Sample Work" in captured["rows"]
    assert "Resolved" in captured["rows"]
    assert "Illegal content" in captured["options"]
    assert "resolved" in captured["status_options"]
    assert "re-open" in captured["status_options"]
