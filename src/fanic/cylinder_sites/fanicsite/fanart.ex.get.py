from __future__ import annotations

import json
from collections.abc import Sequence
from html import escape
from pathlib import Path
from typing import cast
from urllib.parse import quote

from fanic.cylinder_sites.common import RequestLike
from fanic.cylinder_sites.common import ResponseLike
from fanic.cylinder_sites.common import current_user
from fanic.cylinder_sites.common import media_url
from fanic.cylinder_sites.common import rating_badge_html
from fanic.cylinder_sites.common import render_html_template
from fanic.cylinder_sites.common import role_for_user
from fanic.cylinder_sites.common import route_tail
from fanic.cylinder_sites.common import send_file
from fanic.cylinder_sites.common import text_error
from fanic.cylinder_sites.editor_metadata import RATING_CHOICES
from fanic.cylinder_sites.editor_metadata import render_options_html
from fanic.cylinder_sites.report_issues import report_issue_options_html
from fanic.repository import FanartItemRow
from fanic.repository import fanart_file_for
from fanic.repository import fanart_thumb_for
from fanic.repository import get_fanart_item_by_image_filename
from fanic.repository import get_fanart_item_by_thumb_filename
from fanic.repository import list_fanart_items_by_uploader
from fanic.utils import slugify


def _redirect(response: ResponseLike, location: str) -> ResponseLike:
    response.status_code = 303
    response.content_type = "text/plain; charset=utf-8"
    response.headers["Location"] = location
    response.set_data(f"See Other: {location}")
    return response


def _upload_status(msg: str) -> tuple[str, str, str]:
    match msg:
        case "uploaded":
            return ("Fanart uploaded.", "success", "")
        case "uploaded-rating-elevated":
            return (
                "Fanart uploaded. Rating auto-elevated based on moderation detection.",
                "success",
                "",
            )
        case "invalid":
            return ("Please complete all required fields.", "error", "")
        case "missing-file":
            return ("Choose an image file to upload.", "error", "")
        case "policy":
            return ("Upload rejected by file policy.", "error", "")
        case "blocked":
            return (
                "Upload blocked by moderation policy (photorealistic images are not allowed).",
                "error",
                "",
            )
        case "login-required":
            return ("Login required before uploading fanart.", "error", "")
        case "terms":
            return (
                "You must agree to the Terms and Conditions before uploading.",
                "error",
                "",
            )
        case _:
            return ("", "", "hidden")


def _standardized_download_filename(
    uploader_username: str,
    title: str,
    image_filename: str,
) -> str:
    uploader_slug = slugify(uploader_username).replace("-", "_")
    title_slug = slugify(title).replace("-", "_")
    suffix = Path(image_filename).suffix.lower()
    safe_suffix = suffix if suffix else ".avif"
    return f"{uploader_slug}_{title_slug}{safe_suffix}"


def _fanart_grid_html(
    uploader_username: str,
    items: Sequence[FanartItemRow],
    *,
    can_delete: bool,
) -> str:
    if not items:
        return '<p class="profile-meta">No fanart uploaded yet.</p>'

    safe_uploader = quote(uploader_username, safe="")
    parts: list[str] = []
    for item in items:
        item_id = str(item.get("id", "")).strip()
        if not item_id:
            continue

        safe_item_id = quote(item_id, safe="")
        title_raw = str(item.get("title", "Untitled"))
        title = escape(title_raw)
        summary_raw = str(item.get("summary", "")).strip()
        summary = escape(summary_raw if summary_raw else "No summary yet.")
        fandom_raw = str(item.get("fandom", "")).strip()
        fandom_html = f" | fandom: {escape(fandom_raw)}" if fandom_raw else ""
        rating_html = rating_badge_html(item.get("rating", "Not Rated"))
        image_name = str(item.get("image_filename", "")).strip()
        thumb_name = str(item.get("thumb_filename", "")).strip()
        created_at = escape(str(item.get("created_at", "")))
        size_text = f"{item.get('width', 0)}x{item.get('height', 0)}"
        reader_href = f"/fanart/{safe_uploader}/reader?item_id={safe_item_id}"
        download_href = (
            f"/fanart/download/{quote(image_name, safe='/')}"
            if image_name
            else reader_href
        )
        claimed_url = (
            f"/fanart/images/{quote(image_name, safe='/')}"
            if image_name
            else reader_href
        )
        report_href = (
            "/dmca?issue_type=copyright-dmca"
            f"&work_title={quote(title_raw, safe='')}"
            f"&claimed_url={quote(claimed_url, safe='')}"
        )

        thumb_src = (
            f"/fanart/thumbs/{quote(thumb_name, safe='/')}"
            if thumb_name
            else "/static/logo.png"
        )

        delete_html = ""
        if can_delete:
            delete_html = f"""
        <form method="post" action="/fanart/{safe_uploader}/{safe_item_id}/delete" class="admin-delete-form" onsubmit="return confirm('Delete this fanart? This cannot be undone.');">
          <button type="submit" class="icon-delete-button" title="Delete fanart" aria-label="Delete fanart">
            <i class="fa-solid fa-trash" aria-hidden="true"></i>
          </button>
        </form>
      """

        parts.append(
            f'''
      <article class="card work-card">
        {delete_html}
                <a href="{reader_href}">
          <img class="work-cover" src="{thumb_src}" alt="{title}" loading="lazy" />
        </a>
                <h3><a href="{reader_href}">{title}</a></h3>
                <p class="work-meta">{rating_html} | {escape(size_text)}{fandom_html} | {created_at}</p>
        <p>{summary}</p>
            <p><a href="{download_href}">Download</a> | <a href="{report_href}">Report</a></p>
      </article>
    '''
        )

    return "".join(parts)


def _fanart_reader_bootstrap(
    uploader_username: str,
    items: Sequence[FanartItemRow],
    requested_item_id: str,
) -> dict[str, object]:
    pages: list[dict[str, object]] = []
    selected_index = 1
    safe_uploader = quote(uploader_username, safe="")

    for item in items:
        item_id = str(item.get("id", "")).strip()
        image_name = str(item.get("image_filename", "")).strip()
        if not item_id or not image_name:
            continue

        thumb_name = str(item.get("thumb_filename", "")).strip()
        thumb_url = media_url(f"/fanart/thumbs/{quote(thumb_name, safe='/')}")
        if not thumb_name:
            thumb_url = media_url(f"/fanart/images/{quote(image_name, safe='/')}")
        page: dict[str, object] = {
            "index": len(pages) + 1,
            "id": item_id,
            "title": str(item.get("title", "Untitled")),
            "image_url": media_url(f"/fanart/images/{quote(image_name, safe='/')}"),
            "thumb_url": thumb_url,
            "width": item.get("width"),
            "height": item.get("height"),
        }
        pages.append(page)
        if requested_item_id and item_id == requested_item_id:
            selected_index = len(pages)

    return {
        "mode": "fanart",
        "work_id": "",
        "title": f"@{uploader_username} fanart",
        "work_href": f"/fanart/{safe_uploader}",
        "user_id": "anon",
        "page_index": selected_index,
        "pages": pages,
        "chapters": [],
    }


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    tail = route_tail(request, ["fanart"])
    if tail is None:
        return text_error(response, "Not found", 404)

    if tail == []:
        return _redirect(response, "/?view=fanart")

    if len(tail) == 1 and tail[0] == "upload":
        upload_msg = request.args.get("msg", "").strip()
        status_text, status_class, status_hidden_attr = _upload_status(upload_msg)
        return render_html_template(
            request,
            response,
            "fanart-upload.html",
            {
                "__UPLOAD_STATUS_TEXT__": status_text,
                "__UPLOAD_STATUS_CLASS__": status_class,
                "__UPLOAD_STATUS_HIDDEN_ATTR__": status_hidden_attr,
                "__TITLE__": escape(request.args.get("title", "").strip()),
                "__SUMMARY__": escape(request.args.get("summary", "").strip()),
                "__FANDOM__": escape(request.args.get("fandom", "").strip()),
                "__RATING_OPTIONS_HTML__": render_options_html(
                    RATING_CHOICES,
                    request.args.get("rating", "Not Rated").strip(),
                ),
            },
        )

    if len(tail) >= 2 and tail[0] in {"images", "thumbs"}:
        media_kind = tail[0]
        file_name = "/".join(part for part in tail[1:] if part)
        if not file_name:
            return text_error(response, "Not found", 404)

        if media_kind == "images":
            item = get_fanart_item_by_image_filename(file_name)
        else:
            item = get_fanart_item_by_thumb_filename(file_name)
        if item is None:
            return text_error(response, "Not found", 404)

        if media_kind == "images":
            path = fanart_file_for(file_name)
        else:
            path = fanart_thumb_for(file_name)

        if not path.exists():
            return text_error(response, "Not found", 404)

        return send_file(response, path)

    if len(tail) >= 2 and tail[0] == "download":
        file_name = "/".join(part for part in tail[1:] if part)
        if not file_name:
            return text_error(response, "Not found", 404)

        item = get_fanart_item_by_image_filename(file_name)
        if item is None:
            return text_error(response, "Not found", 404)

        path = fanart_file_for(file_name)
        if not path.exists():
            return text_error(response, "Not found", 404)

        download_filename = _standardized_download_filename(
            str(item.get("uploader_username", "")),
            str(item.get("title", "untitled")),
            file_name,
        )
        return send_file(response, path, filename=download_filename)

    if len(tail) == 1:
        uploader_username = tail[0].strip()
        if not uploader_username:
            return text_error(response, "Not found", 404)

        username = current_user(request)
        can_delete = role_for_user(username) in {"superadmin", "admin"}
        items = list_fanart_items_by_uploader(uploader_username, limit=200)
        return render_html_template(
            request,
            response,
            "fanart-gallery.html",
            {
                "__GALLERY_TITLE__": f"@{escape(uploader_username)}",
                "__GALLERY_SUBTITLE__": "Fanart gallery",
                "__GALLERY_READER_HREF__": (
                    f"/fanart/{quote(uploader_username, safe='')}/reader"
                ),
                "__FANART_GRID_HTML__": _fanart_grid_html(
                    uploader_username,
                    items,
                    can_delete=can_delete,
                ),
            },
        )

    if len(tail) == 2 and tail[1] == "reader":
        uploader_username = tail[0].strip()
        if not uploader_username:
            return text_error(response, "Not found", 404)
        back_href = request.args.get("back", "").strip()
        back_href = back_href if back_href else "/?view=fanart"

        items = list_fanart_items_by_uploader(uploader_username, limit=500)
        bootstrap = _fanart_reader_bootstrap(
            uploader_username,
            items,
            request.args.get("item_id", "").strip(),
        )
        pages_obj = bootstrap.get("pages", [])
        if not isinstance(pages_obj, list) or not pages_obj:
            return text_error(response, "Not found", 404)

        bootstrap_json = json.dumps(
            bootstrap,
            ensure_ascii=True,
        ).replace("<", "\\u003c")

        initial_claimed_url = ""
        selected_index_obj = bootstrap.get("page_index", 1)
        selected_index: int
        if isinstance(selected_index_obj, int):
            selected_index = selected_index_obj
        elif isinstance(selected_index_obj, str):
            try:
                selected_index = int(selected_index_obj)
            except ValueError:
                selected_index = 1
        else:
            selected_index = 1
        pages_obj = bootstrap.get("pages", [])
        if isinstance(pages_obj, list):
            pages = cast(list[dict[str, object]], pages_obj)
            page_pos = selected_index - 1
            if page_pos >= 0 and page_pos < len(pages):
                image_url_obj = pages[page_pos].get("image_url", "")
                initial_claimed_url = str(image_url_obj).strip()

        return render_html_template(
            request,
            response,
            "reader.html",
            {
                "__READER_TITLE__": escape(
                    str(bootstrap.get("title", "Fanart Reader"))
                ),
                "__READER_BACK_HREF__": escape(back_href),
                "__READER_BACK_LABEL__": "Back to search",
                "__READER_WORK_HREF__": escape(
                    f"/fanart/{quote(uploader_username, safe='')}"
                ),
                "__READER_WORK_LABEL__": "Gallery",
                "__READER_REPORT_HIDDEN_ATTR__": "",
                "__READER_REPORT_TITLE__": "Report this image",
                "__READER_REPORT_WORK_ID__": "",
                "__READER_REPORT_WORK_TITLE__": escape(f"@{uploader_username} fanart"),
                "__READER_REPORT_CLAIMED_URL__": escape(initial_claimed_url),
                "__REPORT_ISSUE_OPTIONS_HTML__": report_issue_options_html(
                    "copyright-dmca"
                ),
                "__READER_BOOKMARK_HIDDEN_ATTR__": "hidden",
                "__READER_BOOTSTRAP_JSON__": bootstrap_json,
                "__READER_SCRIPT_SRC__": "/static/reader.js",
            },
        )

    return text_error(response, "Not found", 404)
