import json
from base64 import b64encode
from html import escape
from typing import cast
from urllib.parse import quote

from fanic.cylinder_sites.common.protocols import RequestLike
from fanic.cylinder_sites.common.protocols import ResponseLike
from fanic.cylinder_sites.common.responses import redirect_see_other as _redirect
from fanic.cylinder_sites.common.responses import render_html_template
from fanic.cylinder_sites.common.responses import send_file
from fanic.cylinder_sites.common.responses import site_logo_html
from fanic.cylinder_sites.common.responses import text_error
from fanic.cylinder_sites.common.security import route_tail
from fanic.cylinder_sites.common.session import current_user
from fanic.cylinder_sites.common.session import role_for_user
from fanic.cylinder_sites.fanicsite.fanart_get_helpers import (
    build_gallery_cbz_bytes as _build_gallery_cbz_bytes,
)
from fanic.cylinder_sites.fanicsite.fanart_get_helpers import (
    fanart_comment_status as _fanart_comment_status,
)
from fanic.cylinder_sites.fanicsite.fanart_get_helpers import (
    fanart_comments_html as _fanart_comments_html,
)
from fanic.cylinder_sites.fanicsite.fanart_get_helpers import (
    gallery_create_form_html as _gallery_create_form_html,
)
from fanic.cylinder_sites.fanicsite.fanart_get_helpers import (
    gallery_download_filename as _gallery_download_filename,
)
from fanic.cylinder_sites.fanicsite.fanart_get_helpers import (
    gallery_links_html as _gallery_links_html,
)
from fanic.cylinder_sites.fanicsite.fanart_get_helpers import (
    gallery_manage_form_html as _gallery_manage_form_html,
)
from fanic.cylinder_sites.fanicsite.fanart_get_helpers import (
    owner_display_name as _owner_display_name,
)
from fanic.cylinder_sites.fanicsite.fanart_get_helpers import (
    owner_profile_key as _owner_profile_key,
)
from fanic.cylinder_sites.fanicsite.fanart_get_helpers import (
    redirect_found as _redirect_found,
)
from fanic.cylinder_sites.fanicsite.fanart_get_helpers import (
    resolve_owner_username as _resolve_owner_username,
)
from fanic.cylinder_sites.fanicsite.fanart_get_helpers import (
    standardized_download_filename as _standardized_download_filename,
)
from fanic.cylinder_sites.fanicsite.fanart_get_helpers import (
    work_grid_html as _work_grid_html,
)
from fanic.cylinder_sites.fanicsite.fanart_get_helpers import (
    work_reader_bootstrap as _work_reader_bootstrap,
)
from fanic.cylinder_sites.report_issues import report_issue_options_html
from fanic.cylinder_sites.user_roles import is_privileged_role
from fanic.repository.fanart import FanartItemRow
from fanic.repository.fanart import fanart_file_for
from fanic.repository.fanart import get_fanart_gallery_by_slug
from fanic.repository.fanart import get_fanart_item
from fanic.repository.fanart import get_fanart_item_by_image_filename
from fanic.repository.fanart import list_fanart_comments
from fanic.repository.fanart import list_fanart_galleries_by_uploader
from fanic.repository.fanart import list_fanart_gallery_item_ids
from fanic.repository.fanart import list_fanart_items_by_uploader


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

        uploader_username = str(work.get("uploader_username", "")).strip()
        uploader_display_name = str(work.get("uploader_display_name", "")).strip()
        if not uploader_display_name and uploader_username:
            uploader_display_name = _owner_profile_key(uploader_username)

        download_filename = _standardized_download_filename(
            uploader_display_name if uploader_display_name else uploader_username,
            str(work.get("title", "untitled")),
            file_name,
        )
        download_response = send_file(response, path, filename=download_filename)
        download_response.headers["Cache-Control"] = "no-store"
        return download_response

    if len(tail) == 2 and tail[0] == "file":
        item_id = tail[1].strip()
        if not item_id:
            return text_error(response, "Not found", 404)

        item = get_fanart_item(item_id)
        if item is None:
            return text_error(response, "Not found", 404)

        image_name = str(item.get("image_filename", "")).strip().lstrip("/")
        if image_name:
            return _redirect_found(
                response,
                f"/static/fanart/images/{quote(image_name, safe='/')}",
            )

        thumb_name = str(item.get("thumb_filename", "")).strip().lstrip("/")
        if thumb_name:
            return _redirect_found(
                response,
                f"/static/fanart/thumbs/{quote(thumb_name, safe='/')}",
            )

        return text_error(response, "Not found", 404)

    if len(tail) == 3 and tail[1] == "download" and tail[2] == "cbz":
        work_owner_key = tail[0].strip()
        work_owner_username = _resolve_owner_username(work_owner_key)
        if not work_owner_username:
            return text_error(response, "Not found", 404)

        gallery_slug = request.args.get("gallery", "").strip()
        works = list_fanart_items_by_uploader(work_owner_username, limit=500)
        owner_display_name = _owner_display_name(work_owner_username, works)
        if gallery_slug:
            gallery = get_fanart_gallery_by_slug(work_owner_username, gallery_slug)
            if gallery is not None:
                gallery_item_ids = list_fanart_gallery_item_ids(str(gallery.get("id", "")))
                works = [work for work in works if str(work.get("id", "")) in gallery_item_ids]
        archive_bytes, archive_file_count = _build_gallery_cbz_bytes(
            owner_display_name,
            works,
        )
        if archive_file_count < 1:
            return text_error(response, "Not found", 404)

        response.status_code = 200
        response.content_type = "application/vnd.comicbook+zip"
        response.headers["Content-Disposition"] = (
            f'attachment; filename="{_gallery_download_filename(owner_display_name)}"'
        )
        response.set_data(archive_bytes)
        return response

    if len(tail) == 1:
        work_owner_key = tail[0].strip()
        work_owner_username = _resolve_owner_username(work_owner_key)
        if not work_owner_username:
            return text_error(response, "Not found", 404)
        work_owner_profile_key = _owner_profile_key(work_owner_username)

        username = current_user(request)
        can_manage_galleries = username == work_owner_username
        can_delete = is_privileged_role(role_for_user(username))
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

        gallery_download_href = f"/fanart/{quote(work_owner_profile_key, safe='')}/download/cbz"
        if active_gallery is not None:
            active_slug = str(active_gallery.get("slug", "")).strip()
            gallery_download_href = (
                f"/fanart/{quote(work_owner_profile_key, safe='')}/download/cbz?gallery={quote(active_slug, safe='')}"
            )
        return render_html_template(
            request,
            response,
            "fanart-gallery.html",
            {
                "__GALLERY_TITLE__": f"@{escape(owner_display_name)}",
                "__GALLERY_SUBTITLE__": subtitle,
                "__GALLERY_READER_HREF__": (f"/fanart/{quote(work_owner_profile_key, safe='')}/reader"),
                "__GALLERY_DOWNLOAD_CBZ_HREF__": gallery_download_href,
                "__FANART_GALLERY_LINKS_HTML__": _gallery_links_html(
                    work_owner_profile_key,
                    galleries,
                    active_gallery_slug,
                ),
                "__FANART_GALLERY_CREATE_FORM_HIDDEN_ATTR__": "" if can_manage_galleries else "hidden",
                "__FANART_GALLERY_CREATE_FORM_HTML__": _gallery_create_form_html(work_owner_profile_key),
                "__FANART_GALLERY_MANAGE_FORM_HIDDEN_ATTR__": (
                    "" if can_manage_galleries and active_gallery is not None else "hidden"
                ),
                "__FANART_GALLERY_MANAGE_FORM_HTML__": _gallery_manage_form_html(
                    work_owner_profile_key,
                    active_gallery,
                    all_works,
                    active_gallery_item_ids,
                ),
                "__FANART_GRID_HTML__": _work_grid_html(
                    work_owner_profile_key,
                    works,
                    can_delete=can_delete,
                    active_gallery_slug=active_gallery_slug,
                ),
            },
        )

    if len(tail) == 2 and tail[1] == "reader":
        work_owner_key = tail[0].strip()
        work_owner_username = _resolve_owner_username(work_owner_key)
        if not work_owner_username:
            return text_error(response, "Not found", 404)
        work_owner_profile_key = _owner_profile_key(work_owner_username)
        back_href = request.args.get("back", "").strip()
        back_href = back_href if back_href else "/?view=fanart"

        all_works = list_fanart_items_by_uploader(work_owner_username, limit=500)
        works = all_works
        active_gallery_slug = ""
        requested_gallery_slug = request.args.get("gallery", "").strip()
        if requested_gallery_slug:
            gallery = get_fanart_gallery_by_slug(
                work_owner_username,
                requested_gallery_slug,
            )
            if gallery is not None:
                gallery_item_ids = list_fanart_gallery_item_ids(str(gallery.get("id", "")))
                works = [work for work in all_works if str(work.get("id", "")) in gallery_item_ids]
                active_gallery_slug = requested_gallery_slug

        owner_display_name = _owner_display_name(
            work_owner_username,
            works if works else all_works,
        )
        bootstrap = _work_reader_bootstrap(
            work_owner_profile_key,
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
        bootstrap_b64 = b64encode(bootstrap_json.encode("utf-8")).decode("ascii")

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

        reader_work_href = f"/fanart/{quote(work_owner_profile_key, safe='')}"
        if active_gallery_slug:
            reader_work_href = f"{reader_work_href}?gallery={quote(active_gallery_slug, safe='')}"

        requested_item_id = request.args.get("item_id", "").strip()
        selected_item: FanartItemRow | None = None
        if requested_item_id:
            for work in works:
                if str(work.get("id", "")).strip() == requested_item_id:
                    selected_item = work
                    break
        if selected_item is None and works:
            selected_item = works[0]

        fanart_item_id = ""
        fanart_meta_line = ""
        fanart_meta_summary = ""
        fanart_comments_markup = '<p class="profile-meta">No comments yet.</p>'
        if selected_item is not None:
            fanart_item_id = str(selected_item.get("id", "")).strip()
            title_text = str(selected_item.get("title", "Untitled")).strip()
            rating_text = str(selected_item.get("rating", "Not Rated")).strip()
            fandom_text = str(selected_item.get("fandom", "")).strip()
            width_obj = selected_item.get("width")
            height_obj = selected_item.get("height")
            dimensions = ""
            if width_obj is not None and height_obj is not None:
                dimensions = f"{int(width_obj)}x{int(height_obj)}"
            meta_parts: list[str] = [f"title: {title_text}", f"rating: {rating_text}"]
            if fandom_text:
                meta_parts.append(f"fandom: {fandom_text}")
            if dimensions:
                meta_parts.append(f"size: {dimensions}")
            fanart_meta_line = " | ".join(meta_parts)
            summary_text = str(selected_item.get("summary", "")).strip()
            fanart_meta_summary = summary_text if summary_text else "No summary provided."
            if fanart_item_id:
                fanart_comments = list_fanart_comments(fanart_item_id)
                fanart_comments_markup = _fanart_comments_html(fanart_comments)

        comment_status = _fanart_comment_status(request.args.get("msg", ""))
        comment_text = comment_status.text
        comment_class = comment_status.css_class
        comment_hidden_attr = comment_status.hidden_attr
        query_parts: list[str] = []
        if requested_item_id:
            query_parts.append(f"item_id={quote(requested_item_id, safe='')}")
        if active_gallery_slug:
            query_parts.append(f"gallery={quote(active_gallery_slug, safe='')}")
        next_href = f"/fanart/{quote(work_owner_profile_key, safe='')}/reader"
        if query_parts:
            next_href = f"{next_href}?{'&'.join(query_parts)}"

        reader_direct_image_href = initial_claimed_url
        if not reader_direct_image_href and fanart_item_id:
            reader_direct_image_href = f"/fanart/file/{quote(fanart_item_id, safe='')}"

        reader_initial_thumb_href = ""
        if isinstance(pages_obj, list):
            pages = cast(list[dict[str, object]], pages_obj)
            page_pos = selected_index - 1
            if page_pos >= 0 and page_pos < len(pages):
                thumb_url_obj = pages[page_pos].get("thumb_url", "")
                reader_initial_thumb_href = str(thumb_url_obj).strip()
        if not reader_initial_thumb_href:
            reader_initial_thumb_href = reader_direct_image_href

        return render_html_template(
            request,
            response,
            "reader.html",
            {
                "__SITE_LOGO_HTML__": site_logo_html(
                    home_href="/?view=fanart",
                    include_title_wrapper=False,
                ),
                "__READER_TITLE__": escape(str(bootstrap.get("title", "Fanart Reader"))),
                "__READER_BACK_HREF__": escape(back_href),
                "__READER_BACK_LABEL__": "Back to search",
                "__READER_WORK_HREF__": escape(reader_work_href),
                "__READER_WORK_LABEL__": "Gallery",
                "__READER_DIRECT_IMAGE_HREF__": escape(reader_direct_image_href),
                "__READER_INITIAL_IMAGE_SRC__": escape(reader_direct_image_href),
                "__READER_INITIAL_THUMB_SRC__": escape(reader_initial_thumb_href),
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
                "__READER_META_SECTION_HIDDEN_ATTR__": "",
                "__READER_META_LINE__": escape(fanart_meta_line),
                "__READER_META_SUMMARY__": escape(fanart_meta_summary),
                "__READER_COMMENT_STATUS_TEXT__": escape(comment_text),
                "__READER_COMMENT_STATUS_CLASS__": escape(comment_class),
                "__READER_COMMENT_STATUS_HIDDEN_ATTR__": comment_hidden_attr,
                "__READER_COMMENT_FORM_ACTION__": f"/fanart/{quote(work_owner_profile_key, safe='')}/reader/comments",
                "__READER_FANART_ITEM_ID__": escape(fanart_item_id),
                "__READER_FANART_NEXT_HREF__": escape(next_href),
                "__READER_FANART_COMMENTS_HTML__": fanart_comments_markup,
                "__READER_BOOTSTRAP_JSON__": bootstrap_json,
                "__READER_BOOTSTRAP_B64__": bootstrap_b64,
                "__READER_SCRIPT_SRC__": "/static/reader.js?v=20260402-reader-js-fix4",
            },
        )

    return text_error(response, "Not found", 404)
