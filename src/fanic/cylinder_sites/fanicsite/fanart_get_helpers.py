from base64 import b64encode
from collections.abc import Sequence
from dataclasses import dataclass
from html import escape
from io import BytesIO
from pathlib import Path
from textwrap import dedent
from urllib.parse import quote
from zipfile import ZIP_DEFLATED
from zipfile import ZipFile

from fanic.cylinder_sites.common.protocols import ResponseLike
from fanic.cylinder_sites.common.responses import media_url
from fanic.cylinder_sites.common.responses import rating_badge_html
from fanic.repository.fanart import FanartCommentRow
from fanic.repository.fanart import FanartGalleryRow
from fanic.repository.fanart import FanartItemRow
from fanic.repository.fanart import fanart_file_for
from fanic.repository.users import get_local_user
from fanic.repository.users import get_local_user_by_display_name
from fanic.utils import slugify


@dataclass(frozen=True, slots=True)
class FanartCommentStatus:
    text: str
    css_class: str
    hidden_attr: str


def redirect_found(response: ResponseLike, location: str) -> ResponseLike:
    response.status_code = 302
    response.content_type = "text/plain; charset=utf-8"
    response.headers["Location"] = location
    response.set_data(f"Found: {location}")
    return response


def standardized_download_filename(
    work_owner_name: str,
    title: str,
    image_filename: str,
) -> str:
    owner_slug = slugify(work_owner_name).replace("-", "_")
    title_slug = slugify(title).replace("-", "_")
    safe_owner = owner_slug if owner_slug else "fanart"
    safe_title = title_slug if title_slug else "untitled"
    suffix = Path(image_filename).suffix.lower()
    safe_suffix = suffix if suffix else ".avif"
    return f"{safe_owner}_{safe_title}{safe_suffix}"


def work_grid_html(
    work_owner_profile_key: str,
    works: Sequence[FanartItemRow],
    *,
    can_delete: bool,
    active_gallery_slug: str = "",
) -> str:
    if not works:
        return '<p class="profile-meta">No fanart uploaded yet.</p>'

    safe_owner = quote(work_owner_profile_key, safe="")
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
        image_name = str(work.get("image_filename", "")).strip().lstrip("/")
        thumb_name = str(work.get("thumb_filename", "")).strip().lstrip("/")
        created_at = escape(str(work.get("created_at", "")))
        size_text = f"{work.get('width', 0)}x{work.get('height', 0)}"
        reader_href = f"/fanart/{safe_owner}/reader?item_id={safe_work_id}"
        if active_gallery_slug:
            reader_href = f"{reader_href}&gallery={quote(active_gallery_slug, safe='')}"
        download_href = (
            f"/fanart/download/{quote(image_name, safe='/')}?item_id={safe_work_id}" if image_name else reader_href
        )
        direct_image_url = f"/static/fanart/images/{quote(image_name, safe='/')}" if image_name else ""
        direct_thumb_url = f"/static/fanart/thumbs/{quote(thumb_name, safe='/')}" if thumb_name else ""
        claimed_url = direct_image_url if direct_image_url else direct_thumb_url if direct_thumb_url else reader_href
        report_href = (
            "/dmca?issue_type=copyright-dmca"
            f"&work_title={quote(title_raw, safe='')}"
            f"&claimed_url={quote(claimed_url, safe='')}"
        )
        hotlink_href = f"/fanart/file/{safe_work_id}"

        thumb_src = f"/static/fanart/thumbs/{quote(thumb_name, safe='/')}" if thumb_name else "/static/logo.png"

        delete_html = ""
        if can_delete:
            delete_html = dedent(
                f"""
                                <form method=\"post\" action=\"/fanart/{safe_owner}/{safe_work_id}/delete\" class=\"admin-delete-form\" data-confirm-message=\"Delete this fanart? This cannot be undone.\">
                                <button type=\"submit\" class=\"icon-delete-button\" title=\"Delete fanart\" aria-label=\"Delete fanart\">
                                <i class=\"fa-solid fa-trash\" aria-hidden=\"true\"></i>
                                </button>
                                </form>
                                """
            ).strip()

        parts.append(
            dedent(
                f"""
                <article class="card work-card">
                {delete_html}
                <a href="{reader_href}">
                <img class="work-cover" src="{thumb_src}" alt="{title}" loading="lazy" />
                </a>
                <h3><a href="{reader_href}">{title}</a></h3>
                <p class="work-meta">{rating_html} | {escape(size_text)}{fandom_html} | {created_at}</p>
                <p>{summary}</p>
                <p><a href="{download_href}">Download</a> | <a href="{hotlink_href}" target="_blank" rel="noopener noreferrer">Get link</a> | <a href="{report_href}">Report</a></p>
                </article>
                """
            ).strip()
        )

    return "".join(parts)


def gallery_links_html(
    work_owner_profile_key: str,
    galleries: Sequence[FanartGalleryRow],
    active_gallery_slug: str,
) -> str:
    safe_owner = quote(work_owner_profile_key, safe="")
    all_current = ' aria-current="page"' if not active_gallery_slug else ""
    links = [f'<a href="/fanart/{safe_owner}"{all_current}>All fanart</a>']
    for gallery in galleries:
        slug = str(gallery.get("slug", "")).strip()
        if not slug:
            continue
        name = escape(str(gallery.get("name", "Gallery")))
        count = int(gallery.get("item_count", 0))
        current = ' aria-current="page"' if slug == active_gallery_slug else ""
        links.append(f'<a href="/fanart/{safe_owner}?gallery={quote(slug, safe="")}"{current}>{name} ({count})</a>')
    return " | ".join(links)


def gallery_create_form_html(work_owner_profile_key: str) -> str:
    safe_owner = quote(work_owner_profile_key, safe="")
    return (
        f'<form method="post" action="/fanart/{safe_owner}/galleries/create" class="inline-form">'
        '<label for="galleryName">Create gallery:</label> '
        '<input id="galleryName" type="text" name="gallery_name" maxlength="120" placeholder="e.g. Sketches" required /> '
        '<input type="text" name="gallery_description" maxlength="400" placeholder="Optional description" /> '
        '<button type="submit">Create</button>'
        "</form>"
    )


def gallery_manage_form_html(
    work_owner_profile_key: str,
    active_gallery: FanartGalleryRow | None,
    works: Sequence[FanartItemRow],
    selected_item_ids: set[str],
) -> str:
    if active_gallery is None:
        return ""

    gallery_name = escape(str(active_gallery.get("name", "Gallery")))
    gallery_slug = escape(str(active_gallery.get("slug", "")))
    gallery_item_count = int(active_gallery.get("item_count", 0))
    safe_owner = quote(work_owner_profile_key, safe="")
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
            checkbox_id = f"gallery-item-{escape(item_id)}"
            lines.append(
                f'<label class="checkbox-inline" for="{checkbox_id}">'
                f'<input id="{checkbox_id}" type="checkbox" name="gallery_item_id" value="{escape(item_id)}"{checked_attr} /> '
                f"{title}"
                "</label>"
            )
        lines.append("</div>")
        lines.append('<p><button type="submit">Save gallery items</button></p>')

    lines.append("</form>")
    delete_confirm_attr = ""
    if gallery_item_count > 0:
        delete_confirm_attr = ' data-confirm-message="This gallery has assigned images. Deleting it will move all items to Ungrouped. Continue?"'
    lines.append(
        f'<form method="post" action="/fanart/{safe_owner}/galleries/delete"{delete_confirm_attr}>'
        f'<input type="hidden" name="gallery_slug" value="{gallery_slug}" />'
        '<p><button type="submit" class="danger">Trash gallery</button></p>'
        "</form>"
    )
    lines.append("</section>")
    return "".join(lines)


def gallery_download_filename(work_owner_name: str) -> str:
    owner_slug = slugify(work_owner_name).replace("-", "_")
    safe_owner = owner_slug if owner_slug else "fanart"
    return f"{safe_owner}_fanart_gallery.cbz"


def build_gallery_cbz_bytes(
    work_owner_name: str,
    works: Sequence[FanartItemRow],
) -> tuple[bytes, int]:
    used_names: dict[str, int] = {}
    added_files = 0
    payload = BytesIO()

    with ZipFile(payload, "w", compression=ZIP_DEFLATED) as archive:
        for work in works:
            image_name = str(work.get("image_filename", "")).strip().lstrip("/")
            if not image_name:
                continue

            image_path = fanart_file_for(image_name)
            if not image_path.exists() or not image_path.is_file():
                continue

            base_name = standardized_download_filename(
                work_owner_name,
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
            added_files += 1

    return payload.getvalue(), added_files


def work_reader_bootstrap(
    work_owner_profile_key: str,
    works: Sequence[FanartItemRow],
    requested_work_id: str,
) -> dict[str, object]:
    pages: list[dict[str, object]] = []
    selected_index = 1
    safe_owner = quote(work_owner_profile_key, safe="")

    for work in works:
        work_id = str(work.get("id", "")).strip()
        image_name = str(work.get("image_filename", "")).strip().lstrip("/")
        if not work_id or not image_name:
            continue

        thumb_name = str(work.get("thumb_filename", "")).strip().lstrip("/")
        thumb_url = media_url(f"/static/fanart/thumbs/{quote(thumb_name, safe='/')}")
        if not thumb_name:
            thumb_url = media_url(f"/static/fanart/images/{quote(image_name, safe='/')}")
        page: dict[str, object] = {
            "index": len(pages) + 1,
            "id": work_id,
            "title": str(work.get("title", "Untitled")),
            "image_url": media_url(f"/static/fanart/images/{quote(image_name, safe='/')}"),
            "download_url": (f"/fanart/download/{quote(image_name, safe='/')}?item_id={quote(work_id, safe='')}"),
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
        "title": f"@{owner_display_name(work_owner_profile_key, works)} fanart",
        "work_href": f"/fanart/{safe_owner}",
        "user_id": "anon",
        "page_index": selected_index,
        "pages": pages,
        "chapters": [],
    }


def owner_display_name(work_owner_username: str, works: Sequence[FanartItemRow]) -> str:
    for work in works:
        display_name_raw = str(work.get("uploader_display_name", "")).strip()
        if display_name_raw:
            return display_name_raw
    return work_owner_username


def resolve_owner_username(owner_key: str) -> str | None:
    normalized_owner_key = owner_key.strip()
    if not normalized_owner_key:
        return None

    local_user = get_local_user(normalized_owner_key)
    if local_user is not None:
        username = str(local_user.get("username", "")).strip()
        if username:
            return username

    local_user = get_local_user_by_display_name(normalized_owner_key)
    if local_user is not None:
        username = str(local_user.get("username", "")).strip()
        if username:
            return username

    return normalized_owner_key


def owner_profile_key(work_owner_username: str) -> str:
    local_user = get_local_user(work_owner_username)
    if local_user is None:
        return work_owner_username

    display_name = str(local_user.get("display_name", "")).strip()
    if display_name:
        return display_name
    return work_owner_username


def fanart_comment_status(msg: str) -> FanartCommentStatus:
    normalized_msg = msg.strip()
    match normalized_msg:
        case "comment-saved":
            return FanartCommentStatus("Comment posted.", "success", "")
        case "comment-empty":
            return FanartCommentStatus("Comment cannot be empty.", "error", "")
        case "login-required":
            return FanartCommentStatus("Login required before commenting.", "error", "")
        case _:
            return FanartCommentStatus("", "", "hidden")


def fanart_comments_html(comments: list[FanartCommentRow]) -> str:
    if not comments:
        return '<p class="profile-meta">No comments yet.</p>'

    rendered: list[str] = []
    for comment in comments:
        display_name = escape(str(comment.get("commenter_display_name", comment["username"])))
        created_at = escape(str(comment["created_at"]))
        body = escape(str(comment["body"])).replace("\n", "<br />")
        rendered.append(
            '<article class="card comment-card">'
            f'<p class="comment-meta"><strong>{display_name}</strong> | {created_at}</p>'
            f"<p>{body}</p>"
            "</article>"
        )
    return "".join(rendered)


def image_data_url(image_bytes: bytes, *, mime_type: str) -> str:
    encoded = b64encode(image_bytes).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"
