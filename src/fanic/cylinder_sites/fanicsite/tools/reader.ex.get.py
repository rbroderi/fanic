from __future__ import annotations

import json
from collections.abc import Sequence
from html import escape
from typing import Any
from typing import cast

from fanic.cylinder_sites.common import RequestLike
from fanic.cylinder_sites.common import ResponseLike
from fanic.cylinder_sites.common import current_user
from fanic.cylinder_sites.common import render_html_template
from fanic.cylinder_sites.common import route_tail
from fanic.cylinder_sites.common import text_error
from fanic.repository import can_view_work
from fanic.repository import get_manifest
from fanic.repository import get_work
from fanic.repository import get_work_version_manifest
from fanic.repository import load_progress


def _reader_pages_from_version_manifest(
    work_id: str,
    version_id: str,
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
        built.append(
            {
                "index": page_index,
                "image_url": f"/api/works/{work_id}/pages/{page_index}/image?version_id={version_id}",
                "thumb_url": f"/api/works/{work_id}/pages/{page_index}/thumb?version_id={version_id}",
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
            version_id,
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
            reader_pages = [
                cast(dict[str, object], row)
                for row in pages_obj
                if isinstance(row, dict)
            ]
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
            "__READER_WORK_HREF__": escape(work_href),
            "__READER_BOOTSTRAP_JSON__": bootstrap_json,
        },
    )
