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


def test_dmca_get_renders_form_with_prefilled_reason(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: Any,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/dmca.ex.get.py",
        "fanicsite_dmca_ex_get_test",
    )

    captured: dict[str, str] = {}

    def fake_render_html_template(
        request: Any,
        response: ResponseLike,
        template_name: str,
        replacements: dict[str, str],
    ) -> ResponseLike:
        _ = request
        captured["template"] = template_name
        captured["work_id"] = replacements["__DMCA_WORK_ID__"]
        captured["claimed_url"] = replacements["__DMCA_CLAIMED_URL__"]
        captured["options"] = replacements["__REPORT_ISSUE_OPTIONS_HTML__"]
        response.status_code = 200
        response.content_type = "text/html; charset=utf-8"
        response.set_data("ok")
        return response

    monkeypatch.setattr(module, "render_html_template", fake_render_html_template)

    request = dummy_request(
        path="/dmca",
        args={
            "work_id": "work-42",
            "claimed_url": "/comic/work-42",
            "issue_type": "illegal-content",
        },
    )
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 200
    assert captured["template"] == "dmca.html"
    assert captured["work_id"] == "work-42"
    assert captured["claimed_url"] == "/comic/work-42"
    assert "Illegal content" in captured["options"]
    assert "selected" in captured["options"]


def test_dmca_post_rejects_missing_required_fields(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: Any,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/dmca.ex.post.py",
        "fanicsite_dmca_ex_post_invalid_test",
    )

    def always_true(*_args: Any) -> bool:
        return True

    monkeypatch.setattr(module, "enforce_https_termination", always_true)
    monkeypatch.setattr(module, "validate_csrf", always_true)

    request = dummy_request(
        path="/dmca",
        method="POST",
        form={
            "reporter_name": "",
            "reporter_email": "owner@example.com",
            "issue_type": "illegal-content",
            "claimed_url": "https://example.test/comic/work-1",
            "details": "Unauthorized copy",
            "attest": "on",
        },
    )
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 303
    assert result.headers.get("Location") == "/dmca?msg=invalid"


def test_dmca_get_normalizes_relative_claimed_url_to_absolute(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: Any,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/dmca.ex.get.py",
        "fanicsite_dmca_ex_get_absolute_claimed_url_test",
    )

    captured: dict[str, str] = {}

    def fake_render_html_template(
        request: Any,
        response: ResponseLike,
        template_name: str,
        replacements: dict[str, str],
    ) -> ResponseLike:
        _ = request
        captured["template"] = template_name
        captured["claimed_url"] = replacements["__DMCA_CLAIMED_URL__"]
        response.status_code = 200
        response.content_type = "text/html; charset=utf-8"
        response.set_data("ok")
        return response

    monkeypatch.setattr(module, "render_html_template", fake_render_html_template)

    request = dummy_request(
        path="/dmca",
        args={
            "work_id": "work-42",
            "claimed_url": "/comic/work-42",
        },
    )
    request.host_url = "https://fanic.test/"

    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 200
    assert captured["template"] == "dmca.html"
    assert captured["claimed_url"] == "https://fanic.test/comic/work-42"


def test_dmca_post_persists_report_and_redirects(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: Any,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/dmca.ex.post.py",
        "fanicsite_dmca_ex_post_success_test",
    )

    captured: dict[str, object] = {}

    def always_true(*_args: Any) -> bool:
        return True

    def fake_current_user(request: Any) -> str:
        _ = request
        return "alice"

    monkeypatch.setattr(module, "enforce_https_termination", always_true)
    monkeypatch.setattr(module, "validate_csrf", always_true)
    monkeypatch.setattr(module, "current_user", fake_current_user)

    def fake_add_dmca_report(**kwargs: object) -> int:
        captured.update(kwargs)
        return 17

    monkeypatch.setattr(module, "add_dmca_report", fake_add_dmca_report)

    request = dummy_request(
        path="/dmca",
        method="POST",
        form={
            "work_id": "work-1",
            "work_title": "Sample Work",
            "reporter_name": "Owner Name",
            "reporter_email": "owner@example.com",
            "issue_type": "illegal-content",
            "claimed_url": "https://example.test/comic/work-1",
            "evidence_url": "https://example.test/original",
            "details": "This is my copyrighted work.",
            "attest": "on",
        },
    )
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 303
    assert result.headers.get("Location") == "/dmca?msg=submitted&report_id=17"
    assert captured["work_id"] == "work-1"
    assert captured["issue_type"] == "illegal-content"
    assert captured["reporter_username"] == "alice"
