from collections.abc import Sequence
from html import escape
from textwrap import dedent
from urllib.parse import quote

from fanic.cylinder_sites.common.responses import media_url
from fanic.cylinder_sites.common.responses import rating_badge_html
from fanic.repository.fanart import FanartItemRow
from fanic.repository.works import WorkListItem


def work_grid_html(
    works: Sequence[WorkListItem],
    can_delete: bool,
    *,
    back_href: str,
) -> str:
    if not works:
        return "<p>No works yet. Ingest a CBZ to get started.</p>"

    parts: list[str] = []
    for work in works:
        work_id = escape(str(work.get("id", "")))
        work_id_raw = str(work.get("id", "")).strip()
        if not work_id_raw:
            continue
        work_href = f"/comic/{quote(work_id_raw, safe='')}?back={quote(back_href, safe='')}"
        title = escape(str(work.get("title", "Untitled")))
        summary_raw = str(work.get("summary", ""))
        summary = escape(summary_raw if summary_raw else "No summary yet.")
        rating_html = rating_badge_html(work.get("rating", "Not Rated"))
        status = escape(str(work.get("status", "in_progress")))
        page_count = escape(str(work.get("page_count", 0)))
        cover_thumb_name = str(work.get("cover_thumb_filename", "")).strip()
        work_id_quoted = quote(str(work.get("id", "")), safe="")
        if cover_thumb_name:
            cover_src = media_url(f"/static/{work_id_quoted}/thumbs/{quote(cover_thumb_name, safe='/')}")
        else:
            cover_src = media_url("/static/logo.png")

        delete_html = ""
        if can_delete:
            delete_html = (
                dedent(
                    """
                <form method=\"post\" action=\"/comic/{work_id}/delete\" class=\"admin-delete-form\" data-confirm-message=\"Delete this comic? This cannot be undone.\">
                <button type=\"submit\" class=\"icon-delete-button\" title=\"Delete comic\" aria-label=\"Delete comic\">
                <i class=\"fa-solid fa-trash\" aria-hidden=\"true\"></i>
                </button>
                </form>
                """
                )
                .strip()
                .format(work_id=work_id)
            )

        parts.append(
            dedent(
                f"""
                <article class="card work-card">
                {delete_html}
                <a href="{work_href}">
                <img class="work-cover" src="{cover_src}" alt="{title} cover" loading="lazy" />
                </a>
                <h3><a href="{work_href}">{title}</a></h3>
                <p class="work-meta">{rating_html} | {status} | {page_count} pages</p>
                <p>{summary}</p>
                </article>
                """
            ).strip()
        )

    return "".join(parts)


def selected_attr(actual: str, expected: str) -> str:
    return "selected" if actual == expected else ""


def aria_current(is_current: bool) -> str:
    return 'aria-current="page"' if is_current else ""


def fanart_items_html(
    items: Sequence[FanartItemRow],
    *,
    back_href: str,
    can_delete: bool,
) -> str:
    if not items:
        return "<p>No fanart matches found.</p>"

    home_fanart_next = quote("/?view=fanart", safe="")
    parts: list[str] = []
    for row in items:
        uploader = str(row.get("uploader_username", "")).strip()
        if not uploader:
            continue
        display_name_raw = str(row.get("uploader_display_name", "")).strip()
        display_name = display_name_raw if display_name_raw else uploader
        item_id = str(row.get("id", "")).strip()
        if not item_id:
            continue

        safe_display_name = escape(display_name)
        safe_item_id = quote(item_id, safe="")
        profile_key = display_name if display_name else uploader
        safe_profile_key = quote(profile_key, safe="")
        uploader_gallery_href = f"/fanart/{safe_profile_key}"
        uploader_profile_href = f"/users/{quote(display_name, safe='')}"
        viewer_href = f"{uploader_gallery_href}/reader?item_id={safe_item_id}&back={quote(back_href, safe='')}"
        title_raw = str(row.get("title", "Untitled"))
        title = escape(title_raw)
        summary_raw = str(row.get("summary", "")).strip()
        summary = escape(summary_raw if summary_raw else "No summary yet.")
        rating_html = rating_badge_html(row.get("rating", "Not Rated"))
        created_at = escape(str(row.get("created_at", "")))
        image_name = str(row.get("image_filename", "")).strip().lstrip("/")
        thumb_name = str(row.get("thumb_filename", "")).strip().lstrip("/")
        direct_image_url = media_url(f"/static/fanart/images/{quote(image_name, safe='/')}") if image_name else ""
        direct_thumb_url = media_url(f"/static/fanart/thumbs/{quote(thumb_name, safe='/')}") if thumb_name else ""
        claimed_url = direct_image_url if direct_image_url else direct_thumb_url if direct_thumb_url else viewer_href
        report_href = (
            "/dmca?issue_type=copyright-dmca"
            f"&work_title={quote(title_raw, safe='')}"
            f"&claimed_url={quote(claimed_url, safe='')}"
        )
        hotlink_href = f"/fanart/file/{safe_item_id}"
        if thumb_name:
            thumb_src = media_url(f"/static/fanart/thumbs/{quote(thumb_name, safe='/')}")
        else:
            thumb_src = media_url("/static/logo.png")

        delete_html = ""
        if can_delete:
            delete_html = dedent(
                f"""
                <form method="post" action="/fanart/{safe_profile_key}/{safe_item_id}/delete?next={home_fanart_next}" class="admin-delete-form" data-confirm-message="Delete this fanart? This cannot be undone.">
                <button type="submit" class="icon-delete-button" title="Delete fanart" aria-label="Delete fanart">
                <i class="fa-solid fa-trash" aria-hidden="true"></i>
                </button>
                </form>
                """
            ).strip()

        parts.append(
            dedent(
                f"""
                <article class="card work-card">
                {delete_html}
                <a href="{viewer_href}">
                <img class="work-cover" src="{thumb_src}" alt="{safe_display_name} fanart preview" loading="lazy" />
                </a>
                <h3><a href="{viewer_href}">{title}</a></h3>
                <h3><a href="{uploader_profile_href}">@{safe_display_name}</a></h3>
                <p class="work-meta">{rating_html} | {created_at}</p>
                <p>{summary}</p>
                <p><a href="{hotlink_href}" target="_blank" rel="noopener noreferrer">Get link</a> | <a href="{report_href}">Report</a></p>
                </article>
                """
            ).strip()
        )

    return "".join(parts)
