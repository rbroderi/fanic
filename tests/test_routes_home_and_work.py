from __future__ import annotations

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


def test_home_route_renders_work_links(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite.ex.get.py",
        "fanicsite_ex_get_test",
    )

    def fake_current_user(request: Any) -> str:
        _ = request
        return "alice"

    def fake_can_view_work(username: str, work: dict[str, Any]) -> bool:
        _ = (username, work)
        return True

    def fake_list_works(filters: dict[str, Any]) -> list[dict[str, Any]]:
        _ = filters
        return [
            {
                "id": "work-1",
                "slug": "work-1",
                "title": "Test Work",
                "summary": "Summary",
                "status": "complete",
                "rating": "General Audiences",
                "warnings": "",
                "page_count": 12,
                "cover_page_index": 1,
                "updated_at": "2026-03-22T00:00:00Z",
            }
        ]

    monkeypatch.setattr(module, "current_user", fake_current_user)
    monkeypatch.setattr(module, "can_view_work", fake_can_view_work)
    monkeypatch.setattr(
        module,
        "list_works",
        fake_list_works,
    )

    def fake_render_html_template(
        request: Any,
        response: ResponseLike,
        template_name: str,
        replacements: dict[str, str],
    ) -> ResponseLike:
        _ = (request, template_name)
        response.status_code = 200
        response.content_type = "text/html; charset=utf-8"
        response.set_data(replacements["__WORK_GRID_HTML__"])
        return response

    monkeypatch.setattr(module, "render_html_template", fake_render_html_template)

    request = dummy_request(path="/", args={})
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 200
    assert b"/works/work-1" in result.data


def test_work_detail_route_renders_work_page(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/works.ex.get.py",
        "fanicsite_works_ex_get_test",
    )

    def fake_current_user(request: Any) -> str:
        _ = request
        return "alice"

    def fake_can_view_work(username: str, work: dict[str, Any]) -> bool:
        _ = (username, work)
        return True

    def fake_list_work_comments(work_id: str) -> list[dict[str, Any]]:
        _ = work_id
        return []

    def fake_work_kudos_count(work_id: str) -> int:
        _ = work_id
        return 0

    def fake_has_user_kudoed_work(work_id: str, username: str) -> bool:
        _ = (work_id, username)
        return False

    monkeypatch.setattr(module, "current_user", fake_current_user)
    monkeypatch.setattr(module, "can_view_work", fake_can_view_work)
    monkeypatch.setattr(module, "list_work_comments", fake_list_work_comments)
    monkeypatch.setattr(module, "work_kudos_count", fake_work_kudos_count)
    monkeypatch.setattr(module, "has_user_kudoed_work", fake_has_user_kudoed_work)

    def fake_get_work(work_id: str) -> dict[str, Any]:
        return {
            "id": work_id,
            "title": "Test Work",
            "summary": "Summary",
            "rating": "General Audiences",
            "status": "in_progress",
            "page_count": 5,
            "cover_page_index": 1,
            "uploader_username": "alice",
            "tags": [],
        }

    monkeypatch.setattr(
        module,
        "get_work",
        fake_get_work,
    )

    rendered: dict[str, str] = {}

    def fake_render_html_template(
        request: Any,
        response: ResponseLike,
        template_name: str,
        replacements: dict[str, str],
    ) -> ResponseLike:
        _ = request
        rendered["template"] = template_name
        rendered["title"] = replacements["__WORK_TITLE__"]
        rendered["report_options"] = replacements["__REPORT_ISSUE_OPTIONS_HTML__"]
        response.status_code = 200
        response.content_type = "text/html; charset=utf-8"
        response.set_data("ok")
        return response

    monkeypatch.setattr(module, "render_html_template", fake_render_html_template)

    request = dummy_request(path="/works/work-1", args={})
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 200
    assert rendered["template"] == "work.html"
    assert rendered["title"] == "Test Work"
    assert "Illegal content" in rendered["report_options"]


def test_work_edit_route_renders_editor_with_success_status(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/works.ex.get.py",
        "fanicsite_works_edit_ex_get_test",
    )

    def fake_current_user(request: Any) -> str:
        _ = request
        return "alice"

    def fake_can_view_work(username: str, work: dict[str, Any]) -> bool:
        _ = (username, work)
        return True

    def fake_get_work(work_id: str) -> dict[str, Any]:
        return {
            "id": work_id,
            "title": "Editable Work",
            "summary": "Summary",
            "rating": "General Audiences",
            "status": "in_progress",
            "page_count": 5,
            "cover_page_index": 1,
            "uploader_username": "alice",
            "language": "en",
            "warnings": "",
            "tags": [
                {"type": "fandom", "name": "Fandom A"},
                {"type": "character", "name": "Character A"},
            ],
        }

    def fake_list_work_page_rows(work_id: str) -> list[dict[str, Any]]:
        _ = work_id
        return [{"page_number": 1, "filename": "p1.jpg"}]

    def fake_list_work_chapters(work_id: str) -> list[dict[str, Any]]:
        _ = work_id
        return [{"number": 1, "title": "Chapter 1"}]

    def fake_render_options_html(options: list[str], selected: str) -> str:
        _ = (options, selected)
        return "<option>General Audiences</option>"

    def fake_render_editor_page_gallery_html(
        work_id: str,
        pages: list[dict[str, Any]],
        chapters: list[dict[str, Any]],
    ) -> str:
        _ = (work_id, pages, chapters)
        return "<div>gallery</div>"

    def fake_render_editor_chapters_html(
        work_id: str,
        chapters: list[dict[str, Any]],
        **kwargs: Any,
    ) -> str:
        _ = (work_id, chapters, kwargs)
        return "<div>chapters</div>"

    def fake_render_common_tag_datalist_replacements() -> dict[str, str]:
        return {
            "__COMMON_FANDOM_OPTIONS__": "",
            "__COMMON_RELATIONSHIP_OPTIONS__": "",
            "__COMMON_CHARACTER_OPTIONS__": "",
            "__COMMON_FREEFORM_OPTIONS__": "",
        }

    rendered: dict[str, str] = {}

    def fake_render_html_template(
        request: Any,
        response: ResponseLike,
        template_name: str,
        replacements: dict[str, str],
    ) -> ResponseLike:
        _ = request
        rendered["template"] = template_name
        rendered["status_text"] = replacements["__EDIT_STATUS_TEXT__"]
        rendered["status_class"] = replacements["__EDIT_STATUS_CLASS__"]
        rendered["gallery"] = replacements["__EDITOR_PAGE_GALLERY_HTML__"]
        response.status_code = 200
        response.content_type = "text/html; charset=utf-8"
        response.set_data("ok")
        return response

    monkeypatch.setattr(module, "current_user", fake_current_user)
    monkeypatch.setattr(module, "can_view_work", fake_can_view_work)
    monkeypatch.setattr(module, "get_work", fake_get_work)
    monkeypatch.setattr(module, "list_work_page_rows", fake_list_work_page_rows)
    monkeypatch.setattr(module, "list_work_chapters", fake_list_work_chapters)
    monkeypatch.setattr(module, "render_options_html", fake_render_options_html)
    monkeypatch.setattr(
        module,
        "render_editor_page_gallery_html",
        fake_render_editor_page_gallery_html,
    )
    monkeypatch.setattr(
        module, "render_editor_chapters_html", fake_render_editor_chapters_html
    )
    monkeypatch.setattr(
        module,
        "render_common_tag_datalist_replacements",
        fake_render_common_tag_datalist_replacements,
    )
    monkeypatch.setattr(module, "render_html_template", fake_render_html_template)

    request = dummy_request(path="/works/work-1/edit", args={"msg": "page-added"})
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 200
    assert rendered["template"] == "work-edit.html"
    assert rendered["status_text"] == "Page uploaded."
    assert rendered["status_class"] == "success"
    assert rendered["gallery"] == "<div>gallery</div>"


def test_work_edit_route_renders_explicit_rating_lock_error(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/works.ex.get.py",
        "fanicsite_works_edit_explicit_lock_msg_test",
    )

    def fake_current_user(request: Any) -> str:
        _ = request
        return "alice"

    def fake_can_view_work(username: str, work: dict[str, Any]) -> bool:
        _ = (username, work)
        return True

    def fake_get_work(work_id: str) -> dict[str, Any]:
        return {
            "id": work_id,
            "title": "Editable Work",
            "summary": "Summary",
            "rating": "Explicit",
            "status": "in_progress",
            "page_count": 5,
            "cover_page_index": 1,
            "uploader_username": "alice",
            "language": "en",
            "warnings": "",
            "tags": [],
        }

    def fake_list_work_page_rows(work_id: str) -> list[dict[str, Any]]:
        _ = work_id
        return []

    def fake_list_work_chapters(work_id: str) -> list[dict[str, Any]]:
        _ = work_id
        return []

    def fake_render_options_html(options: list[str], selected: str) -> str:
        _ = (options, selected)
        return "<option>Explicit</option>"

    def fake_render_editor_page_gallery_html(
        work_id: str,
        pages: list[dict[str, Any]],
        chapters: list[dict[str, Any]],
    ) -> str:
        _ = (work_id, pages, chapters)
        return "<div></div>"

    def fake_render_editor_chapters_html(
        work_id: str,
        chapters: list[dict[str, Any]],
        **kwargs: Any,
    ) -> str:
        _ = (work_id, chapters, kwargs)
        return "<div></div>"

    def fake_render_common_tag_datalist_replacements() -> dict[str, str]:
        return {
            "__COMMON_FANDOM_OPTIONS__": "",
            "__COMMON_RELATIONSHIP_OPTIONS__": "",
            "__COMMON_CHARACTER_OPTIONS__": "",
            "__COMMON_FREEFORM_OPTIONS__": "",
        }

    rendered: dict[str, str] = {}

    def fake_render_html_template(
        request: Any,
        response: ResponseLike,
        template_name: str,
        replacements: dict[str, str],
    ) -> ResponseLike:
        _ = (request, template_name)
        rendered["status_text"] = replacements["__EDIT_STATUS_TEXT__"]
        rendered["status_class"] = replacements["__EDIT_STATUS_CLASS__"]
        response.status_code = 200
        response.content_type = "text/html; charset=utf-8"
        response.set_data("ok")
        return response

    monkeypatch.setattr(module, "current_user", fake_current_user)
    monkeypatch.setattr(module, "can_view_work", fake_can_view_work)
    monkeypatch.setattr(module, "get_work", fake_get_work)
    monkeypatch.setattr(module, "list_work_page_rows", fake_list_work_page_rows)
    monkeypatch.setattr(module, "list_work_chapters", fake_list_work_chapters)
    monkeypatch.setattr(module, "render_options_html", fake_render_options_html)
    monkeypatch.setattr(
        module,
        "render_editor_page_gallery_html",
        fake_render_editor_page_gallery_html,
    )
    monkeypatch.setattr(
        module,
        "render_editor_chapters_html",
        fake_render_editor_chapters_html,
    )
    monkeypatch.setattr(
        module,
        "render_common_tag_datalist_replacements",
        fake_render_common_tag_datalist_replacements,
    )
    monkeypatch.setattr(module, "render_html_template", fake_render_html_template)

    request = dummy_request(
        path="/works/work-1/edit", args={"msg": "explicit-rating-locked"}
    )
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 200
    assert rendered["status_class"] == "error"
    assert (
        rendered["status_text"]
        == "Only admins can lower a work from Explicit to a lower rating."
    )


def test_work_versions_route_renders_selected_version(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/works.ex.get.py",
        "fanicsite_works_versions_ex_get_test",
    )

    def fake_current_user(request: Any) -> str:
        _ = request
        return "alice"

    def fake_can_view_work(username: str, work: dict[str, Any]) -> bool:
        _ = (username, work)
        return True

    def fake_get_work(work_id: str) -> dict[str, Any]:
        return {"id": work_id, "title": "Versioned Work", "uploader_username": "alice"}

    def fake_list_work_versions(work_id: str, limit: int = 50) -> list[dict[str, Any]]:
        _ = (work_id, limit)
        return [
            {
                "version_id": "v1",
                "created_at": "2026-03-22T00:00:00Z",
                "action": "save",
                "actor": "alice",
                "page_count": 5,
            }
        ]

    def fake_get_work_version_manifest(
        work_id: str, version_id: str
    ) -> dict[str, Any] | None:
        _ = work_id
        if version_id != "v1":
            return None
        return {
            "version_id": "v1",
            "created_at": "2026-03-22T00:00:00Z",
            "action": "save",
            "actor": "alice",
            "work": {
                "title": "Versioned Work",
                "rating": "General Audiences",
                "status": "in_progress",
                "page_count": 5,
                "updated_at": "2026-03-22T00:00:00Z",
            },
        }

    rendered: dict[str, str] = {}

    def fake_render_html_template(
        request: Any,
        response: ResponseLike,
        template_name: str,
        replacements: dict[str, str],
    ) -> ResponseLike:
        _ = request
        rendered["template"] = template_name
        rendered["status"] = replacements["__VERSION_STATUS__"]
        rendered["reader_href"] = replacements["__VERSION_READER_HREF__"]
        response.status_code = 200
        response.content_type = "text/html; charset=utf-8"
        response.set_data("ok")
        return response

    monkeypatch.setattr(module, "current_user", fake_current_user)
    monkeypatch.setattr(module, "can_view_work", fake_can_view_work)
    monkeypatch.setattr(module, "get_work", fake_get_work)
    monkeypatch.setattr(module, "list_work_versions", fake_list_work_versions)
    monkeypatch.setattr(
        module, "get_work_version_manifest", fake_get_work_version_manifest
    )
    monkeypatch.setattr(module, "render_html_template", fake_render_html_template)

    request = dummy_request(path="/works/work-1/versions", args={})
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 200
    assert rendered["template"] == "work-versions.html"
    assert rendered["status"] == "Viewing version v1"
    assert rendered["reader_href"] == "/reader/work-1?version_id=v1"


def test_work_versions_route_returns_404_for_missing_version(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/works.ex.get.py",
        "fanicsite_works_versions_missing_ex_get_test",
    )

    def fake_current_user(request: Any) -> str:
        _ = request
        return "alice"

    def fake_can_view_work(username: str, work: dict[str, Any]) -> bool:
        _ = (username, work)
        return True

    def fake_get_work(work_id: str) -> dict[str, Any]:
        return {"id": work_id, "title": "Versioned Work", "uploader_username": "alice"}

    def fake_list_work_versions(work_id: str, limit: int = 50) -> list[dict[str, Any]]:
        _ = (work_id, limit)
        return [{"version_id": "v1"}]

    def fake_get_work_version_manifest(
        work_id: str, version_id: str
    ) -> dict[str, Any] | None:
        _ = (work_id, version_id)
        return None

    monkeypatch.setattr(module, "current_user", fake_current_user)
    monkeypatch.setattr(module, "can_view_work", fake_can_view_work)
    monkeypatch.setattr(module, "get_work", fake_get_work)
    monkeypatch.setattr(module, "list_work_versions", fake_list_work_versions)
    monkeypatch.setattr(
        module, "get_work_version_manifest", fake_get_work_version_manifest
    )

    request = dummy_request(path="/works/work-1/versions/missing", args={})
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 404
    assert b"Version not found" in result.data


def test_work_edit_route_forbidden_for_non_uploader(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/works.ex.get.py",
        "fanicsite_works_edit_forbidden_test",
    )

    def fake_current_user(request: Any) -> str:
        _ = request
        return "bob"

    def fake_can_view_work(username: str, work: dict[str, Any]) -> bool:
        _ = (username, work)
        return True

    def fake_get_work(work_id: str) -> dict[str, Any]:
        return {
            "id": work_id,
            "title": "Editable Work",
            "uploader_username": "alice",
            "rating": "General Audiences",
            "status": "in_progress",
            "summary": "",
            "language": "en",
            "tags": [],
        }

    monkeypatch.setattr(module, "current_user", fake_current_user)
    monkeypatch.setattr(module, "can_view_work", fake_can_view_work)
    monkeypatch.setattr(module, "get_work", fake_get_work)

    request = dummy_request(path="/works/work-1/edit", args={})
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 403


def test_work_versions_route_renders_empty_versions_message(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/works.ex.get.py",
        "fanicsite_works_versions_empty_test",
    )

    def fake_current_user(request: Any) -> str:
        _ = request
        return "alice"

    def fake_can_view_work(username: str, work: dict[str, Any]) -> bool:
        _ = (username, work)
        return True

    def fake_get_work(work_id: str) -> dict[str, Any]:
        return {
            "id": work_id,
            "title": "Versioned Work",
            "uploader_username": "alice",
        }

    def fake_list_work_versions(work_id: str, limit: int = 50) -> list[dict[str, Any]]:
        _ = (work_id, limit)
        return []

    monkeypatch.setattr(module, "current_user", fake_current_user)
    monkeypatch.setattr(module, "can_view_work", fake_can_view_work)
    monkeypatch.setattr(module, "get_work", fake_get_work)
    monkeypatch.setattr(module, "list_work_versions", fake_list_work_versions)

    captured: dict[str, str] = {}

    def fake_render_html_template(
        request: Any,
        response: ResponseLike,
        template_name: str,
        replacements: dict[str, str],
    ) -> ResponseLike:
        _ = (request, template_name)
        captured["status"] = replacements["__VERSION_STATUS__"]
        response.status_code = 200
        response.content_type = "text/html; charset=utf-8"
        response.set_data("ok")
        return response

    monkeypatch.setattr(module, "render_html_template", fake_render_html_template)

    request = dummy_request(path="/works/work-1/versions", args={})
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 200
    assert captured["status"] == "No versions recorded yet."


@pytest.mark.parametrize(
    ("msg", "expected_class"),
    [
        ("comment-saved", "success"),
        ("kudos-saved", "success"),
        ("already-kudoed", ""),
        ("login-required", "error"),
        ("comment-empty", "error"),
        ("chapter-invalid", "error"),
    ],
)
def test_work_detail_status_messages(
    msg: str,
    expected_class: str,
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/works.ex.get.py",
        f"fanicsite_work_status_msg_{msg}",
    )

    def fake_current_user(request: Any) -> str:
        _ = request
        return "alice"

    def fake_can_view_work(username: str, work: dict[str, Any]) -> bool:
        _ = (username, work)
        return True

    def fake_get_work(work_id: str) -> dict[str, Any]:
        return {
            "id": work_id,
            "title": "Status Work",
            "summary": "Summary",
            "rating": "General Audiences",
            "status": "in_progress",
            "page_count": 3,
            "cover_page_index": 1,
            "uploader_username": "alice",
            "tags": [],
        }

    def fake_list_work_comments(work_id: str) -> list[dict[str, Any]]:
        _ = work_id
        return []

    def fake_work_kudos_count(work_id: str) -> int:
        _ = work_id
        return 0

    def fake_has_user_kudoed_work(work_id: str, username: str) -> bool:
        _ = (work_id, username)
        return False

    monkeypatch.setattr(module, "current_user", fake_current_user)
    monkeypatch.setattr(module, "can_view_work", fake_can_view_work)
    monkeypatch.setattr(module, "get_work", fake_get_work)
    monkeypatch.setattr(module, "list_work_comments", fake_list_work_comments)
    monkeypatch.setattr(module, "work_kudos_count", fake_work_kudos_count)
    monkeypatch.setattr(module, "has_user_kudoed_work", fake_has_user_kudoed_work)

    captured: dict[str, str] = {}

    def fake_render_html_template(
        request: Any,
        response: ResponseLike,
        template_name: str,
        replacements: dict[str, str],
    ) -> ResponseLike:
        _ = (request, template_name)
        captured["status_class"] = replacements["__WORK_STATUS_CLASS__"]
        captured["status_text"] = replacements["__WORK_STATUS_TEXT__"]
        response.status_code = 200
        response.content_type = "text/html; charset=utf-8"
        response.set_data("ok")
        return response

    monkeypatch.setattr(module, "render_html_template", fake_render_html_template)

    request = dummy_request(path="/works/work-1", args={"msg": msg})
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 200
    assert captured["status_class"] == expected_class
    assert captured["status_text"] != ""
