# pyright: reportUnknownLambdaType=false, reportUnknownArgumentType=false

import json
from collections.abc import Callable
from io import BytesIO
from time import perf_counter
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


def _always_true(*_args: object, **_kwargs: object) -> bool:
    return True


def _role_admin(*_args: object, **_kwargs: object) -> str:
    return "admin"


def _role_superadmin(*_args: object, **_kwargs: object) -> str:
    return "superadmin"


def _current_user_alice(*_args: object, **_kwargs: object) -> str:
    return "alice"


def _owner_profile_key(username: str) -> str:
    return username


def _patch_current_user_and_can_view(
    monkeypatch: pytest.MonkeyPatch,
    module: ModuleType,
    *,
    current_user_func: Callable[..., str],
    can_view_work_func: Callable[..., bool],
) -> None:
    monkeypatch.setattr(module, "current_user", current_user_func)
    monkeypatch.setattr(module, "can_view_work", can_view_work_func)


def _comic_get_deps(
    module: ModuleType,
    *,
    get_work_func: Callable[[str], dict[str, Any] | None],
    render_html_template_func: Callable[..., ResponseLike],
    current_user_func: Callable[..., str | None] = _current_user_alice,
    can_view_work_func: Callable[..., bool] = _always_true,
    list_work_versions_func: Callable[[str, int], list[dict[str, Any]]] = lambda *_: [],
    get_work_version_manifest_func: Callable[[str, str], dict[str, Any] | None] = lambda *_: None,
) -> object:
    return module.ComicGetDependencies(
        get_work=get_work_func,
        current_user=current_user_func,
        can_view_work=can_view_work_func,
        role_for_user=_role_admin,
        get_page_files=lambda *_: {"image": "cover.jpg"},
        list_work_comments=lambda *_: [],
        work_kudos_count=lambda *_: 0,
        has_user_kudoed_work=lambda *_: False,
        load_progress=lambda *_: 1,
        list_work_versions=list_work_versions_func,
        get_work_version_manifest=get_work_version_manifest_func,
        render_html_template=render_html_template_func,
    )


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

    seen_filters: dict[str, Any] = {}

    def fake_list_works(filters: dict[str, Any]) -> list[dict[str, Any]]:
        seen_filters.clear()
        seen_filters.update(filters)
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
    monkeypatch.setattr(module, "user_prefers_mature", lambda *_: False)
    monkeypatch.setattr(module, "user_prefers_explicit", lambda *_: False)
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
    assert seen_filters["include_mature"] == "0"
    assert seen_filters["include_explicit"] == "0"


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
    monkeypatch.setattr(module, "role_for_user", _role_superadmin)
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
    assert b"/fanart/AliceArtist/reader?item_id=fanart-1" in result.data
    assert b'<h3><a href="/users/AliceArtist">@AliceArtist</a></h3>' in result.data
    assert b'class="admin-delete-form"' in result.data
    assert b"/fanart/AliceArtist/fanart-1/delete?next=%2F%3Fview%3Dfanart" in result.data
    assert b"/static/fanart/thumbs/_objects/ab/thumb.avif" in result.data
    assert b'/fanart/file/fanart-1" target="_blank" rel="noopener noreferrer">Get link</a>' in result.data
    assert (
        b"/dmca?issue_type=copyright-dmca&work_title=Sky&claimed_url=https%3A%2F%2Fmedia.fanic.media%2Fstatic%2Ffanart%2Fimages%2F_objects%2Fab%2Fimage.avif"
        in result.data
    )
    assert seen_filters["q"] == "ali"
    assert seen_filters["user"] == "alice"
    assert seen_filters["sort"] == "title_asc"


def test_home_route_includes_tag_datalist_replacements(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite.ex.get.py",
        "fanicsite_ex_get_search_datalist_test",
    )

    monkeypatch.setattr(module, "current_user", _current_user_alice)
    monkeypatch.setattr(module, "user_prefers_mature", lambda *_: True)
    monkeypatch.setattr(module, "user_prefers_explicit", lambda *_: True)
    monkeypatch.setattr(module, "list_works", lambda *_: [])
    monkeypatch.setattr(module, "_USER_OPTIONS_HTML", '<option value="AliceArtist"></option>')
    monkeypatch.setattr(
        module,
        "_SEARCH_TAG_DATALIST_REPLACEMENTS",
        {
            "__FANDOM_OPTIONS_HTML__": '<option value="Zootopia (2016)"></option>',
            "__FREEFORM_OPTIONS_HTML__": '<option value="Detective AU"></option>',
        },
    )

    captured: dict[str, str] = {}

    def fake_render_html_template(
        request: Any,
        response: ResponseLike,
        template_name: str,
        replacements: dict[str, str],
    ) -> ResponseLike:
        _ = (request, template_name)
        captured.update(replacements)
        response.status_code = 200
        response.content_type = "text/html; charset=utf-8"
        response.set_data("ok")
        return response

    monkeypatch.setattr(module, "render_html_template", fake_render_html_template)

    result = module.main(dummy_request(path="/", args={}), dummy_response())

    assert result.status_code == 200
    assert "AliceArtist" in captured["__USER_OPTIONS_HTML__"]
    assert "Zootopia (2016)" in captured["__FANDOM_OPTIONS_HTML__"]
    assert "Detective AU" in captured["__FREEFORM_OPTIONS_HTML__"]


def test_home_route_tab_views_render_quickly(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite.ex.get.py",
        "fanicsite_ex_get_perf_test",
    )

    monkeypatch.setattr(module, "current_user", _current_user_alice)
    monkeypatch.setattr(module, "role_for_user", _role_admin)
    monkeypatch.setattr(module, "user_prefers_mature", lambda *_: False)
    monkeypatch.setattr(module, "user_prefers_explicit", lambda *_: False)
    monkeypatch.setattr(
        module,
        "list_works",
        lambda *_: [
            {
                "id": "work-1",
                "slug": "work-1",
                "title": "Fast Work",
                "summary": "Summary",
                "status": "complete",
                "rating": "General Audiences",
                "warnings": "",
                "page_count": 5,
                "cover_page_index": 1,
                "updated_at": "2026-03-22T00:00:00Z",
            }
        ],
    )
    monkeypatch.setattr(
        module,
        "list_fanart_items",
        lambda **_: [
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
        ],
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

    budget_seconds = 0.08

    comics_start = perf_counter()
    comics_result = module.main(dummy_request(path="/", args={}), dummy_response())
    comics_elapsed = perf_counter() - comics_start

    fanart_start = perf_counter()
    fanart_result = module.main(
        dummy_request(path="/", args={"view": "fanart"}),
        dummy_response(),
    )
    fanart_elapsed = perf_counter() - fanart_start

    assert comics_result.status_code == 200
    assert fanart_result.status_code == 200
    assert comics_elapsed < budget_seconds
    assert fanart_elapsed < budget_seconds


def test_fanart_route_gallery_and_media(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: pytest.MonkeyPatch,
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
    monkeypatch.setattr(
        module,
        "list_fanart_items",
        lambda *_args, **_kwargs: fake_list_fanart_items_by_uploader("alice"),
    )
    monkeypatch.setattr(module, "list_fanart_galleries_by_uploader", lambda *_: [])
    monkeypatch.setattr(module, "get_fanart_gallery_by_slug", lambda *_: None)
    monkeypatch.setattr(module, "list_fanart_gallery_item_ids", lambda *_: set())
    monkeypatch.setattr(module, "list_fanart_comments", lambda *_: [])
    monkeypatch.setattr(module, "current_user", lambda *_: "admin-user")
    monkeypatch.setattr(module, "role_for_user", _role_admin)

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
    monkeypatch.setattr(module, "_owner_profile_key", _owner_profile_key)

    gallery_request = dummy_request(path="/fanart/alice", args={})
    gallery_response = dummy_response()
    gallery_result = module.main(gallery_request, gallery_response)

    assert gallery_result.status_code == 200
    assert rendered["template"] == "fanart-gallery.html"
    assert rendered["__GALLERY_TITLE__"] == "@AliceArtist"
    assert rendered["__GALLERY_DOWNLOAD_CBZ_HREF__"] == "/fanart/alice/download/cbz"
    assert "/static/fanart/thumbs/_objects/aa/thumb.avif" in rendered["grid"]
    assert "/fanart/download/_objects/aa/image.avif" in rendered["grid"]
    assert 'href="/fanart/file/art-1" target="_blank" rel="noopener noreferrer">Get link</a>' in rendered["grid"]
    assert "/static/citrus.svg" in rendered["grid"]
    assert "fandom: Skyverse" in rendered["grid"]
    assert 'class="admin-delete-form"' in rendered["grid"]
    assert "/fanart/alice/art-1/delete" in rendered["grid"]
    assert "/fanart/alice/reader?item_id=art-1" in rendered["grid"]
    assert (
        "/dmca?issue_type=copyright-dmca&work_title=Sky&claimed_url=https%3A%2F%2Fmedia.fanic.media%2Fstatic%2Ffanart%2Fimages%2F_objects%2Faa%2Fimage.avif"
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
    assert rendered["__READER_META_SECTION_HIDDEN_ATTR__"] == ""
    assert "title: Sky" in rendered["__READER_META_LINE__"]
    assert rendered["__READER_META_SUMMARY__"] == "Color test"
    assert "No comments yet." in rendered["__READER_FANART_COMMENTS_HTML__"]
    assert rendered["__READER_COMMENT_FORM_ACTION__"] == "/fanart/alice/reader/comments"
    assert rendered["__READER_FANART_ITEM_ID__"] == "art-1"
    assert rendered["__READER_FANART_NEXT_HREF__"] == "/fanart/alice/reader?item_id=art-1"

    media_request = dummy_request(path="/fanart/thumbs/_objects/aa/thumb.avif")
    media_response = dummy_response()
    media_result = module.main(media_request, media_response)

    assert media_result.status_code == 404

    monkeypatch.setattr(
        module,
        "get_fanart_item",
        lambda *_: {
            "id": "art-1",
            "image_filename": "_objects/aa/image.avif",
            "thumb_filename": "_objects/aa/thumb.avif",
        },
    )
    file_request = dummy_request(path="/fanart/file/art-1")
    file_response = dummy_response()
    file_result = module.main(file_request, file_response)

    assert file_result.status_code == 302
    assert file_result.headers["Location"] == "https://media.fanic.media/static/fanart/images/_objects/aa/image.avif"

    monkeypatch.setattr(
        module,
        "get_fanart_item_by_image_filename",
        lambda *_: {
            "id": "art-1",
            "uploader_username": "alice",
            "uploader_display_name": "AliceArtist",
            "title": "Sky",
        },
    )
    from fanic.cylinder_sites.fanicsite import fanart_get_helpers

    class _DummyMediaService:
        def fanart_image_key(self, image_name: str) -> str:
            return f"fanart/images/{image_name.strip().lstrip('/')}"

        def exists(self, key: str) -> bool:
            return key == "fanart/images/_objects/aa/image.avif"

        def get_bytes(self, key: str) -> bytes:
            assert key == "fanart/images/_objects/aa/image.avif"
            return b"image"

    monkeypatch.setattr(module, "get_media_service", lambda: _DummyMediaService())
    monkeypatch.setattr(
        fanart_get_helpers,
        "get_media_service",
        lambda: _DummyMediaService(),
    )

    download_request = dummy_request(path="/fanart/download/_objects/aa/image.avif")
    download_response = dummy_response()
    download_result = module.main(download_request, download_response)

    assert download_result.status_code == 200
    assert download_result.data == b"image"
    assert download_result.headers["Content-Disposition"] == 'attachment; filename="aliceartist_sky.avif"'

    cbz_download_request = dummy_request(path="/fanart/alice/download/cbz")
    cbz_download_response = dummy_response()
    cbz_download_result = module.main(cbz_download_request, cbz_download_response)

    assert cbz_download_result.status_code == 200
    assert cbz_download_result.content_type == "application/vnd.comicbook+zip"
    assert cbz_download_result.headers["Content-Disposition"] == 'attachment; filename="aliceartist_fanart_gallery.cbz"'

    with ZipFile(BytesIO(cbz_download_result.data), "r") as archive:
        names = archive.namelist()
        assert names == ["aliceartist_sky.avif"]
        assert archive.read("aliceartist_sky.avif") == b"image"


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
    monkeypatch.setattr(module, "list_fanart_items", lambda *_args, **_kwargs: works)
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
    monkeypatch.setattr(module, "list_fanart_comments", lambda *_: [])
    monkeypatch.setattr(module, "current_user", _current_user_alice)
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
    monkeypatch.setattr(module, "_owner_profile_key", _owner_profile_key)

    gallery_request = dummy_request(path="/fanart/alice", args={"gallery": "sketches"})
    gallery_response = dummy_response()
    gallery_result = module.main(gallery_request, gallery_response)

    assert gallery_result.status_code == 200
    assert rendered["template"] == "fanart-gallery.html"
    assert "Cloud" in rendered["grid"]
    assert "/fanart/alice/reader?item_id=art-1" not in rendered["grid"]
    assert "/fanart/alice/reader?item_id=art-2&gallery=sketches" in rendered["grid"]
    assert rendered["__GALLERY_DOWNLOAD_CBZ_HREF__"] == "/fanart/alice/download/cbz?gallery=sketches"
    assert 'name="gallery_item_id"' in rendered["__FANART_GALLERY_MANAGE_FORM_HTML__"]
    assert "/fanart/alice/galleries/delete" in rendered["__FANART_GALLERY_MANAGE_FORM_HTML__"]
    assert "Trash gallery" in rendered["__FANART_GALLERY_MANAGE_FORM_HTML__"]
    assert "move all items to Ungrouped" in rendered["__FANART_GALLERY_MANAGE_FORM_HTML__"]

    reader_request = dummy_request(
        path="/fanart/alice/reader",
        args={"item_id": "art-2", "gallery": "sketches"},
    )
    reader_response = dummy_response()
    reader_result = module.main(reader_request, reader_response)

    assert reader_result.status_code == 200
    assert rendered["template"] == "reader.html"
    reader_bootstrap = json.loads(rendered["__READER_BOOTSTRAP_JSON__"])
    assert len(reader_bootstrap["pages"]) == 1
    assert reader_bootstrap["pages"][0]["id"] == "art-2"
    assert rendered["__READER_WORK_HREF__"] == "/fanart/alice?gallery=sketches"
    assert rendered["__READER_FANART_NEXT_HREF__"] == "/fanart/alice/reader?item_id=art-2&amp;gallery=sketches"


def test_fanart_download_filename_uses_display_name_fallback(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/fanart.ex.get.py",
        "fanicsite_fanart_ex_get_download_filename_display_fallback_test",
    )

    monkeypatch.setattr(
        module,
        "get_fanart_item_by_image_filename",
        lambda *_: {
            "id": "art-1",
            "uploader_username": "uuid-owner",
            "title": "Sky",
        },
    )
    monkeypatch.setattr(module, "_owner_profile_key", lambda *_: "AliceArtist")

    class _DummyMediaService:
        def fanart_image_key(self, image_name: str) -> str:
            return f"fanart/images/{image_name.strip().lstrip('/')}"

        def exists(self, key: str) -> bool:
            return key == "fanart/images/_objects/aa/image.avif"

        def get_bytes(self, key: str) -> bytes:
            assert key == "fanart/images/_objects/aa/image.avif"
            return b"image"

    monkeypatch.setattr(module, "get_media_service", lambda: _DummyMediaService())

    download_request = dummy_request(path="/fanart/download/_objects/aa/image.avif")
    download_response = dummy_response()
    download_result = module.main(download_request, download_response)

    assert download_result.status_code == 200
    assert download_result.headers["Content-Disposition"] == 'attachment; filename="aliceartist_sky.avif"'


def test_fanart_reader_normalizes_legacy_image_filename_urls(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/fanart.ex.get.py",
        "fanicsite_fanart_ex_get_reader_legacy_path_test",
    )

    monkeypatch.setattr(
        module,
        "list_fanart_items_by_uploader",
        lambda *_args, **_kwargs: [
            {
                "id": "art-1",
                "uploader_username": "alice",
                "uploader_display_name": "AliceArtist",
                "title": "Sky",
                "summary": "Color test",
                "fandom": "Skyverse",
                "rating": "General Audiences",
                "image_filename": "/_objects/aa/image.avif",
                "thumb_filename": "_objects/aa/thumb.avif",
                "width": 1000,
                "height": 800,
                "created_at": "2026-03-22T00:00:00Z",
                "updated_at": "2026-03-22T00:00:00Z",
            }
        ],
    )
    monkeypatch.setattr(module, "get_fanart_gallery_by_slug", lambda *_: None)
    monkeypatch.setattr(module, "list_fanart_comments", lambda *_: [])

    rendered: dict[str, str] = {}

    def fake_render_html_template(
        request: Any,
        response: ResponseLike,
        template_name: str,
        replacements: dict[str, str],
    ) -> ResponseLike:
        _ = request
        rendered["template"] = template_name
        rendered.update(replacements)
        response.status_code = 200
        response.content_type = "text/html; charset=utf-8"
        response.set_data("ok")
        return response

    monkeypatch.setattr(module, "render_html_template", fake_render_html_template)

    reader_request = dummy_request(path="/fanart/alice/reader", args={"item_id": "art-1"})
    reader_response = dummy_response()
    reader_result = module.main(reader_request, reader_response)

    assert reader_result.status_code == 200
    assert rendered["template"] == "reader.html"
    reader_bootstrap = json.loads(rendered["__READER_BOOTSTRAP_JSON__"])
    page = reader_bootstrap["pages"][0]
    assert page["image_url"].endswith("/static/fanart/images/_objects/aa/image.avif")
    assert page["download_url"] == "/fanart/download/_objects/aa/image.avif?item_id=art-1"


def test_fanart_reader_renders_comments_markup(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/fanart.ex.get.py",
        "fanicsite_fanart_ex_get_reader_comments_test",
    )

    monkeypatch.setattr(
        module,
        "list_fanart_items_by_uploader",
        lambda *_args, **_kwargs: [
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
        ],
    )
    monkeypatch.setattr(module, "get_fanart_gallery_by_slug", lambda *_: None)
    monkeypatch.setattr(
        module,
        "list_fanart_comments",
        lambda *_: [
            {
                "id": "c1",
                "fanart_item_id": "art-1",
                "username": "bob",
                "commenter_display_name": "BobArtist",
                "body": "Great colors",
                "created_at": "2026-03-22T01:00:00Z",
            }
        ],
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
        rendered.update(replacements)
        response.status_code = 200
        response.content_type = "text/html; charset=utf-8"
        response.set_data("ok")
        return response

    monkeypatch.setattr(module, "render_html_template", fake_render_html_template)

    reader_request = dummy_request(
        path="/fanart/alice/reader",
        args={"item_id": "art-1", "msg": "comment-saved"},
    )
    reader_response = dummy_response()
    reader_result = module.main(reader_request, reader_response)

    assert reader_result.status_code == 200
    assert rendered["template"] == "reader.html"
    assert "BobArtist" in rendered["__READER_FANART_COMMENTS_HTML__"]
    assert "Great colors" in rendered["__READER_FANART_COMMENTS_HTML__"]
    assert rendered["__READER_COMMENT_STATUS_TEXT__"] == "Comment posted."
    assert rendered["__READER_COMMENT_STATUS_CLASS__"] == "success"
    assert rendered["__READER_COMMENT_STATUS_HIDDEN_ATTR__"] == ""


def test_work_detail_route_renders_work_page(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/comic.ex.get.py",
        "fanicsite_works_ex_get_test",
    )

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

    deps = _comic_get_deps(
        module,
        get_work_func=fake_get_work,
        render_html_template_func=fake_render_html_template,
    )

    request = dummy_request(path="/comic/work-1", args={})
    response = dummy_response()
    result = module.main_with_deps(request, response, deps)

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
        return [{"page_number": 1, "filename": "p1.jpg", "thumb_filename": "p1-thumb.avif"}]

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
        _ = (work_id, chapters)
        rendered["gallery_thumb_filename"] = str(pages[0].get("thumb_filename", "")) if pages else ""
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

    _patch_current_user_and_can_view(
        monkeypatch,
        module,
        current_user_func=fake_current_user,
        can_view_work_func=fake_can_view_work,
    )
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
    assert rendered["gallery_thumb_filename"] == "p1-thumb.avif"


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

    _patch_current_user_and_can_view(
        monkeypatch,
        module,
        current_user_func=fake_current_user,
        can_view_work_func=fake_can_view_work,
    )
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
    assert rendered["status_text"] == (
        "Only admins can lower Explicit, and non-admins can only raise to Explicit from Mature."
    )


def test_work_versions_route_renders_selected_version(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/comic.ex.get.py",
        "fanicsite_works_versions_ex_get_test",
    )

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

    deps = _comic_get_deps(
        module,
        get_work_func=fake_get_work,
        render_html_template_func=fake_render_html_template,
        list_work_versions_func=fake_list_work_versions,
        get_work_version_manifest_func=fake_get_work_version_manifest,
    )

    request = dummy_request(path="/comic/work-1/versions", args={})
    response = dummy_response()
    result = module.main_with_deps(request, response, deps)

    assert result.status_code == 200
    assert rendered["template"] == "work-versions.html"
    assert rendered["status"] == "Viewing version v1"
    assert rendered["reader_href"] == "/tools/reader/work-1?version_id=v1"


def test_work_versions_route_returns_404_for_missing_version(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/comic.ex.get.py",
        "fanicsite_works_versions_missing_ex_get_test",
    )

    def fake_get_work(work_id: str) -> dict[str, Any]:
        return {"id": work_id, "title": "Versioned Work", "uploader_username": "alice"}

    def fake_list_work_versions(work_id: str, limit: int = 50) -> list[dict[str, Any]]:
        _ = (work_id, limit)
        return [{"version_id": "v1"}]

    def fake_get_work_version_manifest(work_id: str, version_id: str) -> dict[str, Any] | None:
        _ = (work_id, version_id)
        return None

    deps = _comic_get_deps(
        module,
        get_work_func=fake_get_work,
        render_html_template_func=lambda _request, response, *_args, **_kwargs: response,
        list_work_versions_func=fake_list_work_versions,
        get_work_version_manifest_func=fake_get_work_version_manifest,
    )

    request = dummy_request(path="/comic/work-1/versions/missing", args={})
    response = dummy_response()
    result = module.main_with_deps(request, response, deps)

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
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/comic.ex.get.py",
        "fanicsite_works_versions_empty_test",
    )

    def fake_get_work(work_id: str) -> dict[str, Any]:
        return {
            "id": work_id,
            "title": "Versioned Work",
            "uploader_username": "alice",
        }

    def fake_list_work_versions(work_id: str, limit: int = 50) -> list[dict[str, Any]]:
        _ = (work_id, limit)
        return []

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

    deps = _comic_get_deps(
        module,
        get_work_func=fake_get_work,
        render_html_template_func=fake_render_html_template,
        list_work_versions_func=fake_list_work_versions,
    )

    request = dummy_request(path="/comic/work-1/versions", args={})
    response = dummy_response()
    result = module.main_with_deps(request, response, deps)

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
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/comic.ex.get.py",
        f"fanicsite_work_status_msg_{msg}",
    )

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

    deps = _comic_get_deps(
        module,
        get_work_func=fake_get_work,
        render_html_template_func=fake_render_html_template,
    )

    request = dummy_request(path="/comic/work-1", args={"msg": msg})
    response = dummy_response()
    result = module.main_with_deps(request, response, deps)

    assert result.status_code == 200
    assert captured["status_class"] == expected_class
    assert captured["status_text"] != ""
