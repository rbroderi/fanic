import json
from collections.abc import Callable
from io import BytesIO
from pathlib import Path
from types import ModuleType
from typing import Any
from typing import Protocol
from zipfile import ZipFile

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
    assert b"/comic/work-1" in result.data


def test_home_route_renders_fanart_tab(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite.ex.get.py",
        "fanicsite_ex_get_fanart_test",
    )

    def fake_current_user(request: Any) -> str:
        _ = request
        return "alice"

    seen_filters: dict[str, Any] = {}

    def fake_list_fanart_items(
        filters: dict[str, str] | None = None,
        *,
        limit: int = 120,
    ) -> list[dict[str, Any]]:
        seen_filters.clear()
        seen_filters.update(filters if filters else {})
        _ = limit
        return [
            {
                "id": "fanart-1",
                "uploader_username": "alice",
                "uploader_display_name": "AliceArtist",
                "title": "Sky",
                "summary": "Color test",
                "fandom": "Skyverse",
                "rating": "General Audiences",
                "image_filename": "_objects/ab/image.avif",
                "thumb_filename": "_objects/ab/thumb.avif",
                "width": 1000,
                "height": 800,
                "created_at": "2026-03-22T00:00:00Z",
                "updated_at": "2026-03-22T00:00:00Z",
            }
        ]

    monkeypatch.setattr(module, "current_user", fake_current_user)
    monkeypatch.setattr(module, "list_fanart_items", fake_list_fanart_items)

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

    request = dummy_request(
        path="/",
        args={
            "view": "fanart",
            "q": "ali",
            "user": "alice",
            "sort": "title_asc",
        },
    )
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 200
    assert b"/fanart/alice/reader?item_id=fanart-1" in result.data
    assert b'<h3><a href="/fanart/alice">@AliceArtist</a></h3>' in result.data
    assert b"/static/fanart/thumbs/_objects/ab/thumb.avif" in result.data
    assert (
        b"/dmca?issue_type=copyright-dmca&work_title=Sky&claimed_url=%2Fstatic%2Ffanart%2Fimages%2F_objects%2Fab%2Fimage.avif"
        in result.data
    )
    assert seen_filters["q"] == "ali"
    assert seen_filters["user"] == "alice"
    assert seen_filters["sort"] == "title_asc"


def test_fanart_route_gallery_and_media(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/fanart.ex.get.py",
        "fanicsite_fanart_ex_get_test",
    )

    def fake_list_fanart_items_by_uploader(
        uploader_username: str,
        *,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        _ = (uploader_username, limit)
        return [
            {
                "id": "art-1",
                "uploader_username": "alice",
                "uploader_display_name": "AliceArtist",
                "title": "Sky",
                "summary": "Color test",
                "fandom": "Skyverse",
                "rating": "General Audiences",
                "image_filename": "_objects/aa/image.avif",
                "thumb_filename": "_objects/aa/thumb.avif",
                "width": 1000,
                "height": 800,
                "created_at": "2026-03-22T00:00:00Z",
                "updated_at": "2026-03-22T00:00:00Z",
            }
        ]

    monkeypatch.setattr(
        module,
        "list_fanart_items_by_uploader",
        fake_list_fanart_items_by_uploader,
    )
    monkeypatch.setattr(module, "list_fanart_galleries_by_uploader", lambda *_: [])
    monkeypatch.setattr(module, "get_fanart_gallery_by_slug", lambda *_: None)
    monkeypatch.setattr(module, "list_fanart_gallery_item_ids", lambda *_: set())
    monkeypatch.setattr(module, "current_user", lambda *_: "admin-user")
    monkeypatch.setattr(module, "role_for_user", lambda *_: "admin")

    rendered: dict[str, str] = {}

    def fake_render_html_template(
        request: Any,
        response: ResponseLike,
        template_name: str,
        replacements: dict[str, str],
    ) -> ResponseLike:
        _ = request
        rendered["template"] = template_name
        rendered["grid"] = replacements.get("__FANART_GRID_HTML__", "")
        rendered.update(replacements)
        response.status_code = 200
        response.content_type = "text/html; charset=utf-8"
        response.set_data("ok")
        return response

    monkeypatch.setattr(module, "render_html_template", fake_render_html_template)

    gallery_request = dummy_request(path="/fanart/alice", args={})
    gallery_response = dummy_response()
    gallery_result = module.main(gallery_request, gallery_response)

    assert gallery_result.status_code == 200
    assert rendered["template"] == "fanart-gallery.html"
    assert rendered["__GALLERY_TITLE__"] == "@AliceArtist"
    assert rendered["__GALLERY_DOWNLOAD_CBZ_HREF__"] == "/fanart/alice/download/cbz"
    assert "/static/fanart/thumbs/_objects/aa/thumb.avif" in rendered["grid"]
    assert "/fanart/download/_objects/aa/image.avif" in rendered["grid"]
    assert 'data-copy-url="/static/fanart/images/_objects/aa/image.avif"' in rendered["grid"]
    assert "/static/citrus.svg" in rendered["grid"]
    assert "fandom: Skyverse" in rendered["grid"]
    assert 'class="admin-delete-form"' in rendered["grid"]
    assert "/fanart/alice/art-1/delete" in rendered["grid"]
    assert "/fanart/alice/reader?item_id=art-1" in rendered["grid"]
    assert (
        "/dmca?issue_type=copyright-dmca&work_title=Sky&claimed_url=%2Fstatic%2Ffanart%2Fimages%2F_objects%2Faa%2Fimage.avif"
        in rendered["grid"]
    )

    reader_request = dummy_request(path="/fanart/alice/reader", args={"item_id": "art-1"})
    reader_response = dummy_response()
    reader_result = module.main(reader_request, reader_response)

    assert reader_result.status_code == 200
    assert rendered["template"] == "reader.html"
    reader_bootstrap = json.loads(rendered["__READER_BOOTSTRAP_JSON__"])
    assert reader_bootstrap["mode"] == "fanart"
    assert len(reader_bootstrap["pages"]) == 1
    assert reader_bootstrap["pages"][0]["id"] == "art-1"
    assert reader_bootstrap["page_index"] == 1
    assert rendered["__READER_REPORT_HIDDEN_ATTR__"] == ""
    assert rendered["__READER_REPORT_TITLE__"] == "Report this image"
    assert rendered["__READER_REPORT_WORK_TITLE__"] == "@AliceArtist fanart"
    assert rendered["__READER_REPORT_CLAIMED_URL__"].endswith("/static/fanart/images/_objects/aa/image.avif")
    assert "Copyright infringement (DMCA)" in rendered["__REPORT_ISSUE_OPTIONS_HTML__"]

    media_request = dummy_request(path="/fanart/thumbs/_objects/aa/thumb.avif")
    media_response = dummy_response()
    media_result = module.main(media_request, media_response)

    assert media_result.status_code == 404

    image_file = tmp_path / "image.avif"
    image_file.write_bytes(b"image")

    monkeypatch.setattr(
        module,
        "get_fanart_item_by_image_filename",
        lambda *_: {
            "id": "art-1",
            "uploader_username": "alice",
            "title": "Sky",
        },
    )
    monkeypatch.setattr(module, "fanart_file_for", lambda *_: image_file)

    captured: dict[str, str] = {}

    def fake_send_file_download(
        response: ResponseLike,
        file_path: Path,
        filename: str | None = None,
    ) -> ResponseLike:
        captured["filename"] = filename if filename else ""
        response.status_code = 200
        response.content_type = "image/avif"
        response.set_data(file_path.read_bytes())
        return response

    monkeypatch.setattr(module, "send_file", fake_send_file_download)

    download_request = dummy_request(path="/fanart/download/_objects/aa/image.avif")
    download_response = dummy_response()
    download_result = module.main(download_request, download_response)

    assert download_result.status_code == 200
    assert download_result.data == b"image"
    assert captured["filename"] == "alice_sky.avif"

    cbz_download_request = dummy_request(path="/fanart/alice/download/cbz")
    cbz_download_response = dummy_response()
    cbz_download_result = module.main(cbz_download_request, cbz_download_response)

    assert cbz_download_result.status_code == 200
    assert cbz_download_result.content_type == "application/vnd.comicbook+zip"
    assert cbz_download_result.headers["Content-Disposition"] == 'attachment; filename="alice_fanart_gallery.cbz"'

    with ZipFile(BytesIO(cbz_download_result.data), "r") as archive:
        names = archive.namelist()
        assert names == ["alice_sky.avif"]
        assert archive.read("alice_sky.avif") == b"image"


def test_fanart_route_gallery_grouping_filter(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/fanart.ex.get.py",
        "fanicsite_fanart_ex_get_gallery_filter_test",
    )

    works = [
        {
            "id": "art-1",
            "uploader_username": "alice",
            "uploader_display_name": "AliceArtist",
            "title": "Sky",
            "summary": "Color test",
            "fandom": "Skyverse",
            "rating": "General Audiences",
            "image_filename": "_objects/aa/image.avif",
            "thumb_filename": "_objects/aa/thumb.avif",
            "width": 1000,
            "height": 800,
            "created_at": "2026-03-22T00:00:00Z",
            "updated_at": "2026-03-22T00:00:00Z",
        },
        {
            "id": "art-2",
            "uploader_username": "alice",
            "uploader_display_name": "AliceArtist",
            "title": "Cloud",
            "summary": "Shape study",
            "fandom": "Skyverse",
            "rating": "General Audiences",
            "image_filename": "_objects/bb/image.avif",
            "thumb_filename": "_objects/bb/thumb.avif",
            "width": 1000,
            "height": 800,
            "created_at": "2026-03-23T00:00:00Z",
            "updated_at": "2026-03-23T00:00:00Z",
        },
    ]

    monkeypatch.setattr(module, "list_fanart_items_by_uploader", lambda *_args, **_kwargs: works)
    monkeypatch.setattr(
        module,
        "list_fanart_galleries_by_uploader",
        lambda *_: [
            {
                "id": "gallery-1",
                "uploader_username": "alice",
                "name": "Sketches",
                "slug": "sketches",
                "description": "",
                "item_count": 1,
                "created_at": "",
                "updated_at": "",
            }
        ],
    )
    monkeypatch.setattr(
        module,
        "get_fanart_gallery_by_slug",
        lambda *_: {
            "id": "gallery-1",
            "uploader_username": "alice",
            "name": "Sketches",
            "slug": "sketches",
            "description": "",
            "item_count": 1,
            "created_at": "",
            "updated_at": "",
        },
    )
    monkeypatch.setattr(module, "list_fanart_gallery_item_ids", lambda *_: {"art-2"})
    monkeypatch.setattr(module, "current_user", lambda *_: "alice")
    monkeypatch.setattr(module, "role_for_user", lambda *_: "user")

    rendered: dict[str, str] = {}

    def fake_render_html_template(
        request: Any,
        response: ResponseLike,
        template_name: str,
        replacements: dict[str, str],
    ) -> ResponseLike:
        _ = request
        rendered["template"] = template_name
        rendered["grid"] = replacements.get("__FANART_GRID_HTML__", "")
        rendered.update(replacements)
        response.status_code = 200
        response.content_type = "text/html; charset=utf-8"
        response.set_data("ok")
        return response

    monkeypatch.setattr(module, "render_html_template", fake_render_html_template)

    gallery_request = dummy_request(path="/fanart/alice", args={"gallery": "sketches"})
    gallery_response = dummy_response()
    gallery_result = module.main(gallery_request, gallery_response)

    assert gallery_result.status_code == 200
    assert rendered["template"] == "fanart-gallery.html"
    assert "Cloud" in rendered["grid"]
    assert "/fanart/alice/reader?item_id=art-1" not in rendered["grid"]
    assert "/fanart/alice/reader?item_id=art-2" in rendered["grid"]
    assert rendered["__GALLERY_DOWNLOAD_CBZ_HREF__"] == "/fanart/alice/download/cbz?gallery=sketches"
    assert 'name="gallery_item_id"' in rendered["__FANART_GALLERY_MANAGE_FORM_HTML__"]


def test_work_detail_route_renders_work_page(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/comic.ex.get.py",
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

    request = dummy_request(path="/comic/work-1", args={})
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
        "src/fanic/cylinder_sites/fanicsite/comic.ex.get.py",
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
    monkeypatch.setattr(module, "render_editor_chapters_html", fake_render_editor_chapters_html)
    monkeypatch.setattr(
        module,
        "render_common_tag_datalist_replacements",
        fake_render_common_tag_datalist_replacements,
    )
    monkeypatch.setattr(module, "render_html_template", fake_render_html_template)

    request = dummy_request(path="/comic/work-1/edit", args={"msg": "page-added"})
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
        "src/fanic/cylinder_sites/fanicsite/comic.ex.get.py",
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

    request = dummy_request(path="/comic/work-1/edit", args={"msg": "explicit-rating-locked"})
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 200
    assert rendered["status_class"] == "error"
    assert rendered["status_text"] == "Only admins can lower a work from Explicit to a lower rating."


def test_work_versions_route_renders_selected_version(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/comic.ex.get.py",
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

    def fake_get_work_version_manifest(work_id: str, version_id: str) -> dict[str, Any] | None:
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
    monkeypatch.setattr(module, "get_work_version_manifest", fake_get_work_version_manifest)
    monkeypatch.setattr(module, "render_html_template", fake_render_html_template)

    request = dummy_request(path="/comic/work-1/versions", args={})
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 200
    assert rendered["template"] == "work-versions.html"
    assert rendered["status"] == "Viewing version v1"
    assert rendered["reader_href"] == "/tools/reader/work-1?version_id=v1"


def test_work_versions_route_returns_404_for_missing_version(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/comic.ex.get.py",
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

    def fake_get_work_version_manifest(work_id: str, version_id: str) -> dict[str, Any] | None:
        _ = (work_id, version_id)
        return None

    monkeypatch.setattr(module, "current_user", fake_current_user)
    monkeypatch.setattr(module, "can_view_work", fake_can_view_work)
    monkeypatch.setattr(module, "get_work", fake_get_work)
    monkeypatch.setattr(module, "list_work_versions", fake_list_work_versions)
    monkeypatch.setattr(module, "get_work_version_manifest", fake_get_work_version_manifest)

    request = dummy_request(path="/comic/work-1/versions/missing", args={})
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
        "src/fanic/cylinder_sites/fanicsite/comic.ex.get.py",
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

    request = dummy_request(path="/comic/work-1/edit", args={})
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
        "src/fanic/cylinder_sites/fanicsite/comic.ex.get.py",
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

    request = dummy_request(path="/comic/work-1/versions", args={})
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
        "src/fanic/cylinder_sites/fanicsite/comic.ex.get.py",
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

    request = dummy_request(path="/comic/work-1", args={"msg": msg})
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 200
    assert captured["status_class"] == expected_class
    assert captured["status_text"] != ""
