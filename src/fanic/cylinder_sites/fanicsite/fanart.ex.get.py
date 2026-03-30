import json
from collections.abc import Sequence
from html import escape
from io import BytesIO
from pathlib import Path
from typing import cast
from urllib.parse import quote
from zipfile import ZIP_DEFLATED
from zipfile import ZipFile

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
from fanic.cylinder_sites.report_issues import report_issue_options_html
from fanic.repository import FanartGalleryRow
from fanic.repository import FanartItemRow
from fanic.repository import fanart_file_for
from fanic.repository import get_fanart_gallery_by_slug
from fanic.repository import get_fanart_item_by_image_filename
from fanic.repository import list_fanart_galleries_by_uploader
from fanic.repository import list_fanart_gallery_item_ids
from fanic.repository import list_fanart_items_by_uploader
from fanic.utils import slugify


def _redirect(response: ResponseLike, location: str) -> ResponseLike:
    response.status_code = 303
    response.content_type = "text/plain; charset=utf-8"
    response.headers["Location"] = location
    response.set_data(f"See Other: {location}")
    return response


def _standardized_download_filename(
    work_owner_username: str,
    title: str,
    image_filename: str,
) -> str:
    owner_slug = slugify(work_owner_username).replace("-", "_")
    title_slug = slugify(title).replace("-", "_")
    suffix = Path(image_filename).suffix.lower()
    safe_suffix = suffix if suffix else ".avif"
    return f"{owner_slug}_{title_slug}{safe_suffix}"


def _work_grid_html(
    work_owner_username: str,
    works: Sequence[FanartItemRow],
    *,
    can_delete: bool,
) -> str:
    if not works:
        return '<p class="profile-meta">No fanart uploaded yet.</p>'

    safe_owner = quote(work_owner_username, safe="")
    parts: list[str] = []
    for work in works:
        work_id = str(work.get("id", "")).strip()
        if not work_id:
            continue

        safe_work_id = quote(work_id, safe="")
        title_raw = str(work.get("title", "Untitled"))
        title = escape(title_raw)
        summary_raw = str(work.get("summary", "")).strip()
        summary = escape(summary_raw if summary_raw else "No summary yet.")
        fandom_raw = str(work.get("fandom", "")).strip()
        fandom_html = f" | fandom: {escape(fandom_raw)}" if fandom_raw else ""
        rating_html = rating_badge_html(work.get("rating", "Not Rated"))
        image_name = str(work.get("image_filename", "")).strip()
        thumb_name = str(work.get("thumb_filename", "")).strip()
        created_at = escape(str(work.get("created_at", "")))
        size_text = f"{work.get('width', 0)}x{work.get('height', 0)}"
        reader_href = f"/fanart/{safe_owner}/reader?item_id={safe_work_id}"
        download_href = f"/fanart/download/{quote(image_name, safe='/')}" if image_name else reader_href
        claimed_url = f"/static/fanart/images/{quote(image_name, safe='/')}" if image_name else reader_href
        report_href = (
            "/dmca?issue_type=copyright-dmca"
            f"&work_title={quote(title_raw, safe='')}"
            f"&claimed_url={quote(claimed_url, safe='')}"
        )
        hotlink_href = f"/static/fanart/images/{quote(image_name, safe='/')}" if image_name else reader_href

        thumb_src = f"/static/fanart/thumbs/{quote(thumb_name, safe='/')}" if thumb_name else "/static/logo.png"

        delete_html = ""
        if can_delete:
            delete_html = f"""
                <form method="post" action="/fanart/{safe_owner}/{safe_work_id}/delete" class="admin-delete-form" onsubmit="return confirm('Delete this fanart? This cannot be undone.');">
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
                                                <p><a href="{download_href}">Download</a> | <a href="#" data-copy-url="{hotlink_href}">Get link</a> | <a href="{report_href}">Report</a></p>
      </article>
    '''
        )

    return "".join(parts)


def _gallery_links_html(
    work_owner_username: str,
    galleries: Sequence[FanartGalleryRow],
    active_gallery_slug: str,
) -> str:
    safe_owner = quote(work_owner_username, safe="")
    all_current = ' aria-current="page"' if not active_gallery_slug else ""
    links = [f'<a href="/fanart/{safe_owner}"{all_current}>All fanart</a>']
    for gallery in galleries:
        slug = str(gallery.get("slug", "")).strip()
        name = escape(str(gallery.get("name", "Untitled")))
        count = int(gallery.get("item_count", 0))
        current = ' aria-current="page"' if slug == active_gallery_slug else ""
        links.append(f'<a href="/fanart/{safe_owner}?gallery={quote(slug, safe="")}"{current}>{name} ({count})</a>')
    return " | ".join(links)


def _gallery_create_form_html(work_owner_username: str) -> str:
    safe_owner = quote(work_owner_username, safe="")
    return (
        f'<form method="post" action="/fanart/{safe_owner}/galleries/create" class="inline-form">'
        '<label for="galleryName">Create gallery:</label> '
        '<input id="galleryName" type="text" name="gallery_name" maxlength="120" placeholder="e.g. Sketches" required /> '
        '<input type="text" name="gallery_description" maxlength="400" placeholder="Optional description" /> '
        '<button type="submit">Create</button>'
        "</form>"
    )


def _gallery_manage_form_html(
    work_owner_username: str,
    active_gallery: FanartGalleryRow | None,
    works: Sequence[FanartItemRow],
    selected_item_ids: set[str],
) -> str:
    if active_gallery is None:
        return ""

    gallery_name = escape(str(active_gallery.get("name", "Gallery")))
    gallery_slug = escape(str(active_gallery.get("slug", "")))
    safe_owner = quote(work_owner_username, safe="")
    lines: list[str] = [
        '<section class="card">',
        f"<h3>Manage {gallery_name}</h3>",
        (
            f'<form method="post" action="/fanart/{safe_owner}/galleries/update-items">'
            f'<input type="hidden" name="gallery_slug" value="{gallery_slug}" />'
        ),
    ]

    if not works:
        lines.append('<p class="profile-meta">No fanart uploaded yet.</p>')
    else:
        lines.append('<p class="profile-meta">Select which images belong in this gallery.</p>')
        lines.append('<div class="stack">')
        for work in works:
            item_id = str(work.get("id", "")).strip()
            if not item_id:
                continue
            title = escape(str(work.get("title", "Untitled")))
            checked_attr = " checked" if item_id in selected_item_ids else ""
            lines.append(
                '<label class="checkbox-inline">'
                f'<input type="checkbox" name="gallery_item_id" value="{escape(item_id)}"{checked_attr} /> '
                f"{title}"
                "</label>"
            )
        lines.append("</div>")
        lines.append('<p><button type="submit">Save gallery items</button></p>')

    lines.append("</form>")
    lines.append("</section>")
    return "".join(lines)


def _gallery_download_filename(work_owner_username: str) -> str:
    owner_slug = slugify(work_owner_username).replace("-", "_")
    safe_owner = owner_slug if owner_slug else "fanart"
    return f"{safe_owner}_fanart_gallery.cbz"


def _build_gallery_cbz_bytes(
    work_owner_username: str,
    works: Sequence[FanartItemRow],
) -> bytes:
    used_names: dict[str, int] = {}
    payload = BytesIO()

    with ZipFile(payload, "w", compression=ZIP_DEFLATED) as archive:
        for work in works:
            image_name = str(work.get("image_filename", "")).strip()
            if not image_name:
                continue

            image_path = fanart_file_for(image_name)
            if not image_path.exists() or not image_path.is_file():
                continue

            base_name = _standardized_download_filename(
                work_owner_username,
                str(work.get("title", "untitled")),
                image_name,
            )
            seen = used_names.get(base_name, 0)
            if seen == 0:
                archive_name = base_name
            else:
                stem = Path(base_name).stem
                suffix = Path(base_name).suffix
                archive_name = f"{stem}_{seen + 1}{suffix}"
            used_names[base_name] = seen + 1

            archive.write(image_path, arcname=archive_name)

    return payload.getvalue()


def _work_reader_bootstrap(
    work_owner_username: str,
    works: Sequence[FanartItemRow],
    requested_work_id: str,
) -> dict[str, object]:
    pages: list[dict[str, object]] = []
    selected_index = 1
    safe_owner = quote(work_owner_username, safe="")

    for work in works:
        work_id = str(work.get("id", "")).strip()
        image_name = str(work.get("image_filename", "")).strip()
        if not work_id or not image_name:
            continue

        thumb_name = str(work.get("thumb_filename", "")).strip()
        thumb_url = media_url(f"/static/fanart/thumbs/{quote(thumb_name, safe='/')}")
        if not thumb_name:
            thumb_url = media_url(f"/static/fanart/images/{quote(image_name, safe='/')}")
        page: dict[str, object] = {
            "index": len(pages) + 1,
            "id": work_id,
            "title": str(work.get("title", "Untitled")),
            "image_url": media_url(f"/static/fanart/images/{quote(image_name, safe='/')}"),
            "download_url": f"/fanart/download/{quote(image_name, safe='/')}",
            "thumb_url": thumb_url,
            "width": work.get("width"),
            "height": work.get("height"),
        }
        pages.append(page)
        if requested_work_id and work_id == requested_work_id:
            selected_index = len(pages)

    return {
        "mode": "fanart",
        "work_id": "",
        "title": f"@{_owner_display_name(work_owner_username, works)} fanart",
        "work_href": f"/fanart/{safe_owner}",
        "user_id": "anon",
        "page_index": selected_index,
        "pages": pages,
        "chapters": [],
    }


def _owner_display_name(work_owner_username: str, works: Sequence[FanartItemRow]) -> str:
    for work in works:
        display_name_raw = str(work.get("uploader_display_name", "")).strip()
        if display_name_raw:
            return display_name_raw
    return work_owner_username


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    tail = route_tail(request, ["fanart"])
    if tail is None:
        return text_error(response, "Not found", 404)

    if tail == []:
        return _redirect(response, "/?view=fanart")

    if len(tail) >= 2 and tail[0] == "download":
        file_name = "/".join(part for part in tail[1:] if part)
        if not file_name:
            return text_error(response, "Not found", 404)

        work = get_fanart_item_by_image_filename(file_name)
        if work is None:
            return text_error(response, "Not found", 404)

        path = fanart_file_for(file_name)
        if not path.exists():
            return text_error(response, "Not found", 404)

        download_filename = _standardized_download_filename(
            str(work.get("uploader_username", "")),
            str(work.get("title", "untitled")),
            file_name,
        )
        return send_file(response, path, filename=download_filename)

    if len(tail) == 3 and tail[1] == "download" and tail[2] == "cbz":
        work_owner_username = tail[0].strip()
        if not work_owner_username:
            return text_error(response, "Not found", 404)

        gallery_slug = request.args.get("gallery", "").strip()
        works = list_fanart_items_by_uploader(work_owner_username, limit=500)
        if gallery_slug:
            gallery = get_fanart_gallery_by_slug(work_owner_username, gallery_slug)
            if gallery is not None:
                gallery_item_ids = list_fanart_gallery_item_ids(str(gallery.get("id", "")))
                works = [work for work in works if str(work.get("id", "")) in gallery_item_ids]
        archive_bytes = _build_gallery_cbz_bytes(work_owner_username, works)
        if not archive_bytes:
            return text_error(response, "Not found", 404)

        response.status_code = 200
        response.content_type = "application/vnd.comicbook+zip"
        response.headers["Content-Disposition"] = (
            f'attachment; filename="{_gallery_download_filename(work_owner_username)}"'
        )
        response.set_data(archive_bytes)
        return response

    if len(tail) == 1:
        work_owner_username = tail[0].strip()
        if not work_owner_username:
            return text_error(response, "Not found", 404)

        username = current_user(request)
        can_manage_galleries = username == work_owner_username
        can_delete = role_for_user(username) in {"superadmin", "admin"}
        all_works = list_fanart_items_by_uploader(work_owner_username, limit=500)
        galleries = list_fanart_galleries_by_uploader(work_owner_username)
        active_gallery_slug = request.args.get("gallery", "").strip()
        active_gallery = None
        active_gallery_item_ids: set[str] = set()
        works = all_works
        if active_gallery_slug:
            active_gallery = get_fanart_gallery_by_slug(work_owner_username, active_gallery_slug)
            if active_gallery is not None:
                active_gallery_item_ids = list_fanart_gallery_item_ids(str(active_gallery.get("id", "")))
                works = [work for work in all_works if str(work.get("id", "")) in active_gallery_item_ids]
        owner_display_name = _owner_display_name(work_owner_username, works)
        subtitle = "Fanart gallery"
        if active_gallery is not None:
            active_name = str(active_gallery.get("name", "")).strip()
            subtitle = f"Fanart gallery - {active_name}" if active_name else "Fanart gallery"

        gallery_download_href = f"/fanart/{quote(work_owner_username, safe='')}/download/cbz"
        if active_gallery is not None:
            active_slug = str(active_gallery.get("slug", "")).strip()
            gallery_download_href = (
                f"/fanart/{quote(work_owner_username, safe='')}/download/cbz?gallery={quote(active_slug, safe='')}"
            )
        return render_html_template(
            request,
            response,
            "fanart-gallery.html",
            {
                "__GALLERY_TITLE__": f"@{escape(owner_display_name)}",
                "__GALLERY_SUBTITLE__": subtitle,
                "__GALLERY_READER_HREF__": (f"/fanart/{quote(work_owner_username, safe='')}/reader"),
                "__GALLERY_DOWNLOAD_CBZ_HREF__": gallery_download_href,
                "__FANART_GALLERY_LINKS_HTML__": _gallery_links_html(
                    work_owner_username,
                    galleries,
                    active_gallery_slug,
                ),
                "__FANART_GALLERY_CREATE_FORM_HIDDEN_ATTR__": "" if can_manage_galleries else "hidden",
                "__FANART_GALLERY_CREATE_FORM_HTML__": _gallery_create_form_html(work_owner_username),
                "__FANART_GALLERY_MANAGE_FORM_HIDDEN_ATTR__": (
                    "" if can_manage_galleries and active_gallery is not None else "hidden"
                ),
                "__FANART_GALLERY_MANAGE_FORM_HTML__": _gallery_manage_form_html(
                    work_owner_username,
                    active_gallery,
                    all_works,
                    active_gallery_item_ids,
                ),
                "__FANART_GRID_HTML__": _work_grid_html(
                    work_owner_username,
                    works,
                    can_delete=can_delete,
                ),
            },
        )

    if len(tail) == 2 and tail[1] == "reader":
        work_owner_username = tail[0].strip()
        if not work_owner_username:
            return text_error(response, "Not found", 404)
        back_href = request.args.get("back", "").strip()
        back_href = back_href if back_href else "/?view=fanart"

        works = list_fanart_items_by_uploader(work_owner_username, limit=500)
        owner_display_name = _owner_display_name(work_owner_username, works)
        bootstrap = _work_reader_bootstrap(
            work_owner_username,
            works,
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
                "__READER_TITLE__": escape(str(bootstrap.get("title", "Fanart Reader"))),
                "__READER_BACK_HREF__": escape(back_href),
                "__READER_BACK_LABEL__": "Back to search",
                "__READER_WORK_HREF__": escape(f"/fanart/{quote(work_owner_username, safe='')}"),
                "__READER_WORK_LABEL__": "Gallery",
                "__READER_DOWNLOAD_HIDDEN_ATTR__": "",
                "__READER_DOWNLOAD_HREF__": "#",
                "__READER_DOWNLOAD_LABEL__": "Download",
                "__READER_REPORT_HIDDEN_ATTR__": "",
                "__READER_REPORT_TITLE__": "Report this image",
                "__READER_REPORT_WORK_ID__": "",
                "__READER_REPORT_WORK_TITLE__": escape(f"@{owner_display_name} fanart"),
                "__READER_REPORT_CLAIMED_URL__": escape(initial_claimed_url),
                "__REPORT_ISSUE_OPTIONS_HTML__": report_issue_options_html("copyright-dmca"),
                "__READER_BOOKMARK_HIDDEN_ATTR__": "hidden",
                "__READER_BOOTSTRAP_JSON__": bootstrap_json,
                "__READER_SCRIPT_SRC__": "/static/reader.js",
            },
        )

    return text_error(response, "Not found", 404)
