from collections.abc import Mapping
from collections.abc import Sequence
from html import escape
from typing import Literal
from urllib.parse import quote

from fanic.cylinder_sites.common.responses import STATIC_ROOT
from fanic.cylinder_sites.common.responses import media_url
from fanic.repository.fanart import list_fanart_galleries_by_uploader
from fanic.repository.fanart import list_fanart_gallery_item_ids


def render_profile_shared_sections(replacements: dict[str, str]) -> str:
    html = (STATIC_ROOT / "profile-shared-sections.html").read_text(encoding="utf-8")
    for marker, value in replacements.items():
        html = html.replace(marker, value)
    return html


def render_uploaded_works_html(
    works: Sequence[Mapping[str, object]],
    *,
    include_stats: bool,
) -> str:
    if not works:
        return '<p class="profile-meta">No uploaded works yet.</p>'

    items: list[str] = []
    for work in works:
        work_id = escape(str(work.get("id", "")))
        title = escape(str(work.get("title", "Untitled")))
        page_count = escape(str(work.get("page_count", 0)))
        status = escape(str(work.get("status", "in_progress")))
        if include_stats:
            kudos_count = escape(str(work.get("kudos_count", 0)))
            comments_count = escape(str(work.get("comments_count", 0)))
            metadata = f"({status}, {page_count} pages, {kudos_count} kudos, {comments_count} comments)"
        else:
            metadata = f"({status}, {page_count} pages)"
        items.append(f'<li><a href="/comic/{work_id}">{title}</a> <span class="profile-meta">{metadata}</span></li>')
    return '<ul class="work-links">' + "".join(items) + "</ul>"


def render_bookmarks_html(bookmarks: Sequence[Mapping[str, object]]) -> str:
    if not bookmarks:
        return '<p class="profile-meta">No bookmarks yet.</p>'

    items: list[str] = []
    for row in bookmarks:
        work_id = escape(str(row.get("work_id", "")))
        work_title = escape(str(row.get("work_title", "Untitled")))
        author_username = str(row.get("author_username", "unknown"))
        author_display_name_raw = str(row.get("author_display_name", "")).strip()
        author_display_name = author_display_name_raw if author_display_name_raw else author_username
        author_profile_href = f"/users/{quote(author_display_name, safe='')}"
        message = escape(str(row.get("message", "")))
        page_index = escape(str(row.get("page_index", 1)))
        message_html = f' <span class="profile-meta">- {message}</span>' if message else ""
        items.append(
            f'<li><a href="/tools/reader/{work_id}">{work_title}</a> '
            f'<span class="profile-meta">by <a href="{author_profile_href}">{escape(author_display_name)}</a> (saved at page {page_index})</span>'
            f"{message_html}</li>"
        )
    return '<ul class="work-links">' + "".join(items) + "</ul>"


def render_fanart_html(
    uploader_username: str,
    uploader_profile_key: str,
    fanart_items: Sequence[Mapping[str, object]],
    *,
    profile_kind: Literal["private", "public"],
) -> str:
    if not fanart_items:
        return '<p class="profile-meta">No fanart uploaded yet.</p>'

    gallery_meta_by_item_id: dict[str, tuple[str, str]] = {}
    galleries = list_fanart_galleries_by_uploader(uploader_username)
    for gallery in galleries:
        gallery_id = str(gallery.get("id", "")).strip()
        gallery_name = str(gallery.get("name", "")).strip()
        gallery_slug = str(gallery.get("slug", "")).strip()
        if not gallery_id or not gallery_slug:
            continue
        resolved_name = gallery_name if gallery_name else gallery_slug
        for item_id in list_fanart_gallery_item_ids(gallery_id):
            if item_id not in gallery_meta_by_item_id:
                gallery_meta_by_item_id[item_id] = (resolved_name, gallery_slug)

    safe_uploader = quote(uploader_profile_key, safe="")
    grouped_items: dict[str, list[str]] = {}
    group_order: list[str] = []

    def _add_grouped_item(group_name: str, item_html: str) -> None:
        if group_name not in grouped_items:
            grouped_items[group_name] = []
            group_order.append(group_name)
        grouped_items[group_name].append(item_html)

    for row in fanart_items:
        title = escape(str(row.get("title", "Untitled")))
        item_id = str(row.get("id", "")).strip()
        if item_id:
            gallery_name = "Ungrouped"
            gallery_slug = ""
            gallery_meta = gallery_meta_by_item_id.get(item_id)
            if gallery_meta is not None:
                gallery_name, gallery_slug = gallery_meta

            if profile_kind == "private":
                safe_item_id = quote(item_id, safe="")
                link_href = f"/fanart/{safe_uploader}/reader?item_id={safe_item_id}"
                if gallery_slug:
                    link_href = f"{link_href}&gallery={quote(gallery_slug, safe='')}"
            else:
                link_href = f"/users/{safe_uploader}/gallery/all"
                if gallery_slug:
                    link_href = f"/users/{safe_uploader}/gallery/{quote(gallery_slug, safe='')}"

            _add_grouped_item(
                gallery_name,
                f'<li><a href="{link_href}">{title}</a></li>',
            )
            continue

        image_name = quote(str(row.get("image_filename", "")).strip(), safe="/")
        _add_grouped_item(
            "Ungrouped",
            f'<li><a href="{media_url(f"/static/fanart/images/{image_name}")}">{title}</a></li>',
        )

    sections: list[str] = []
    ordered_groups = [name for name in group_order if name != "Ungrouped"]
    if "Ungrouped" in grouped_items:
        ordered_groups.append("Ungrouped")

    for group_name in ordered_groups:
        label = escape(group_name)
        section_items = "".join(grouped_items[group_name])
        sections.append(f'<section class="stack"><h4>{label}</h4><ul class="work-links">{section_items}</ul></section>')
    return "".join(sections)
