import json
from collections.abc import Sequence
from html import escape
from typing import Any
from typing import cast
from urllib.parse import quote

from fanic.cylinder_sites.common import RequestLike
from fanic.cylinder_sites.common import ResponseLike
from fanic.cylinder_sites.common import current_user
from fanic.cylinder_sites.common import media_url
from fanic.cylinder_sites.common import render_html_template
from fanic.cylinder_sites.common import route_tail
from fanic.cylinder_sites.common import text_error
from fanic.cylinder_sites.report_issues import report_issue_options_html
from fanic.repository import can_view_work
from fanic.repository import get_manifest
from fanic.repository import get_work
from fanic.repository import get_work_version_manifest
from fanic.repository import load_progress


def _reader_pages_from_version_manifest(
    work_id: str,
    manifest: dict[str, object],
) -> list[dict[str, object]]:
    pages_obj = manifest.get("pages")
    if not isinstance(pages_obj, Sequence):
        return []

    built: list[dict[str, object]] = []
    for page_obj in pages_obj:
        if not isinstance(page_obj, dict):
            continue
        page = cast(dict[str, Any], page_obj)
        page_index_obj = page.get("page_index", 0)
        try:
            page_index = int(page_index_obj)
        except (TypeError, ValueError):
            continue
        if page_index < 1:
            continue
        image_filename = str(page.get("image_filename", "")).strip()
        thumb_filename = str(page.get("thumb_filename", "")).strip()
        if image_filename:
            thumb_name = thumb_filename if thumb_filename else image_filename
            image_url = media_url(f"/works/{quote(work_id, safe='')}/pages/{quote(image_filename, safe='/')}")
            thumb_url = media_url(f"/works/{quote(work_id, safe='')}/thumbs/{quote(thumb_name, safe='/')}")
        else:
            image_url = media_url(str(page.get("image_url", "")).strip())
            thumb_url = media_url(str(page.get("thumb_url", "")).strip())
            if not image_url or not thumb_url:
                continue
        built.append(
            {
                "index": page_index,
                "image_url": image_url,
                "thumb_url": thumb_url,
                "width": page.get("width"),
                "height": page.get("height"),
            }
        )

    built.sort(key=lambda row: cast(int, row["index"]))
    return built


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    tail = route_tail(request, ["tools", "reader"])
    if tail is None or len(tail) != 1:
        return text_error(response, "Not found", 404)

    work_id = tail[0]
    back_href = request.args.get("back", "").strip()
    back_href = back_href if back_href else "/?view=comics"
    work = get_work(work_id)
    if not work:
        return text_error(response, "Work not found", 404)

    username = current_user(request)
    if not can_view_work(username, work):
        return text_error(response, "Work not found", 404)

    version_id = request.args.get("version_id", "").strip()
    manifest: dict[str, object] | None
    reader_pages: list[dict[str, object]]
    chapters: object
    work_href = f"/works/{work_id}"
    if version_id:
        version_manifest = get_work_version_manifest(work_id, version_id)
        if version_manifest is None:
            return text_error(response, "Version not found", 404)
        manifest = version_manifest
        reader_pages = _reader_pages_from_version_manifest(
            work_id,
            version_manifest,
        )
        chapters = version_manifest.get("chapters", [])
        work_href = f"/works/{work_id}/versions/{version_id}"
    else:
        manifest = get_manifest(work_id)
        if manifest is None:
            return text_error(response, "Work not found", 404)
        pages_obj = manifest.get("pages", [])
        if isinstance(pages_obj, Sequence):
            reader_pages = []
            for row in pages_obj:
                if not isinstance(row, dict):
                    continue
                page = cast(dict[str, object], row)
                image_url_raw = str(page.get("image_url", "")).strip()
                thumb_url_raw = str(page.get("thumb_url", "")).strip()
                if image_url_raw:
                    page["image_url"] = media_url(image_url_raw)
                if thumb_url_raw:
                    page["thumb_url"] = media_url(thumb_url_raw)
                reader_pages.append(page)
        else:
            reader_pages = []
        chapters = manifest.get("chapters", [])

    user_id = username if username else "anon"
    page_index = load_progress(work_id, user_id)
    manifest_title = str(manifest.get("title", "FANIC Reader"))
    if version_id:
        manifest_title = f"{manifest_title} (version {version_id})"
    bootstrap_json = json.dumps(
        {
            "work_id": work_id,
            "title": manifest_title,
            "work_href": work_href,
            "user_id": user_id,
            "page_index": page_index,
            "pages": reader_pages,
            "chapters": chapters,
        },
        ensure_ascii=True,
    ).replace("<", "\\u003c")

    return render_html_template(
        request,
        response,
        "reader.html",
        {
            "__READER_TITLE__": escape(manifest_title),
            "__READER_BACK_HREF__": escape(back_href),
            "__READER_BACK_LABEL__": "Back to search",
            "__READER_WORK_HREF__": escape(work_href),
            "__READER_WORK_LABEL__": "Work",
            "__READER_REPORT_HIDDEN_ATTR__": "hidden",
            "__READER_REPORT_TITLE__": "Report this work",
            "__READER_REPORT_WORK_ID__": escape(work_id),
            "__READER_REPORT_WORK_TITLE__": escape(manifest_title),
            "__READER_REPORT_CLAIMED_URL__": f"/works/{escape(work_id)}",
            "__REPORT_ISSUE_OPTIONS_HTML__": report_issue_options_html("copyright-dmca"),
            "__READER_BOOKMARK_HIDDEN_ATTR__": "",
            "__READER_BOOTSTRAP_JSON__": bootstrap_json,
            "__READER_SCRIPT_SRC__": "/static/reader.js",
        },
    )
