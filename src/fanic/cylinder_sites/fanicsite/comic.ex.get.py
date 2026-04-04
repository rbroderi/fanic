from collections.abc import Callable
from collections.abc import Mapping
from collections.abc import Sequence
from dataclasses import dataclass
from html import escape
from typing import TYPE_CHECKING
from typing import Any
from typing import cast
from urllib.parse import quote
from urllib.parse import urlencode

if TYPE_CHECKING:
    from _typeshed import ConvertibleToInt
else:
    type ConvertibleToInt = int | str | bytes

from fanic.cylinder_sites.common.protocols import RequestLike
from fanic.cylinder_sites.common.protocols import ResponseLike
from fanic.cylinder_sites.common.responses import media_url
from fanic.cylinder_sites.common.responses import rating_badge_html
from fanic.cylinder_sites.common.responses import render_html_template
from fanic.cylinder_sites.common.responses import text_error
from fanic.cylinder_sites.common.security import route_tail
from fanic.cylinder_sites.common.session import current_user
from fanic.cylinder_sites.common.session import role_for_user
from fanic.cylinder_sites.editor_gallery import render_editor_chapters_html
from fanic.cylinder_sites.editor_gallery import render_editor_page_gallery_html
from fanic.cylinder_sites.editor_metadata import RATING_CHOICES
from fanic.cylinder_sites.editor_metadata import render_common_tag_datalist_replacements
from fanic.cylinder_sites.editor_metadata import render_options_html
from fanic.cylinder_sites.editor_metadata import selected_attr
from fanic.cylinder_sites.fanicsite.comic_get_helpers import (
    can_edit_work as _can_edit_work,
)
from fanic.cylinder_sites.fanicsite.comic_get_helpers import (
    comment_cards_html as _comment_cards_html,
)
from fanic.cylinder_sites.fanicsite.comic_get_helpers import (
    status_for_edit_message as _status_for_edit_message,
)
from fanic.cylinder_sites.fanicsite.comic_get_helpers import (
    status_for_work_message as _status_for_work_message,
)
from fanic.cylinder_sites.fanicsite.comic_get_helpers import (
    tag_names_csv as _tag_names_csv,
)
from fanic.cylinder_sites.fanicsite.comic_get_helpers import (
    version_metadata_html as _version_metadata_html,
)
from fanic.cylinder_sites.fanicsite.comic_get_helpers import (
    work_versions_list_html as _work_versions_list_html,
)
from fanic.cylinder_sites.report_issues import report_issue_options_html
from fanic.cylinder_sites.user_roles import is_privileged_role
from fanic.repository.works import can_view_work
from fanic.repository.works import get_page_files
from fanic.repository.works import get_work
from fanic.repository.works import get_work_version_manifest
from fanic.repository.works import has_user_kudoed_work
from fanic.repository.works import list_work_chapters
from fanic.repository.works import list_work_comments
from fanic.repository.works import list_work_page_rows
from fanic.repository.works import list_work_versions
from fanic.repository.works import load_progress
from fanic.repository.works import work_kudos_count


@dataclass(frozen=True, slots=True)
class ComicGetDependencies:
    get_work: Callable[[str], dict[str, Any] | None]
    current_user: Callable[[RequestLike], str | None]
    can_view_work: Callable[[str | None, dict[str, Any]], bool]
    role_for_user: Callable[[str | None], str]
    get_page_files: Callable[[str, int], Mapping[str, object] | None]
    list_work_comments: Callable[[str], Sequence[object]]
    work_kudos_count: Callable[[str], int]
    has_user_kudoed_work: Callable[[str, str | None], bool]
    load_progress: Callable[[str, str], int]
    list_work_versions: Callable[[str, int], Sequence[Mapping[str, object]]]
    get_work_version_manifest: Callable[[str, str], dict[str, object] | None]
    render_html_template: Callable[..., ResponseLike]


def _runtime_deps() -> ComicGetDependencies:
    return ComicGetDependencies(
        get_work=get_work,
        current_user=current_user,
        can_view_work=can_view_work,
        role_for_user=role_for_user,
        get_page_files=get_page_files,
        list_work_comments=list_work_comments,
        work_kudos_count=work_kudos_count,
        has_user_kudoed_work=has_user_kudoed_work,
        load_progress=load_progress,
        list_work_versions=list_work_versions,
        get_work_version_manifest=get_work_version_manifest,
        render_html_template=render_html_template,
    )


def _main_with_deps(
    request: RequestLike,
    response: ResponseLike,
    deps: ComicGetDependencies,
) -> ResponseLike:
    tail = route_tail(request, ["comic"])
    if tail is None:
        return text_error(response, "Not found", 404)

    if len(tail) == 2 and tail[1] == "edit":
        work_id = tail[0]
        work = get_work(work_id)
        if not work:
            return text_error(response, "Work not found", 404)

        username = current_user(request)
        if not can_view_work(username, work):
            return text_error(response, "Work not found", 404)

        uploader = str(work.get("uploader_username") if work.get("uploader_username") else "")
        user_role = role_for_user(username)
        if not _can_edit_work(
            username,
            uploader,
            is_admin=is_privileged_role(user_role),
        ):
            return text_error(response, "Forbidden", 403)

        tags = work.get("tags", [])
        warnings_tags = _tag_names_csv(tags, "archive_warning")
        warnings_text = warnings_tags if warnings_tags else str(work.get("warnings", ""))

        save_msg = request.args.get("msg", "").strip()
        edit_status = _status_for_edit_message(save_msg)

        pages = cast(list[dict[str, Any]], list_work_page_rows(work_id))
        chapters = cast(list[dict[str, Any]], list_work_chapters(work_id))
        # Normalize TypedDict rows to plain dict rows for editor helper signatures.
        gallery_pages: list[dict[str, ConvertibleToInt]] = []
        for page in pages:
            page_index_obj = page.get("page_index")
            if page_index_obj is None:
                page_index_obj = page.get("page_number", 0)
            image_filename_obj = page.get("image_filename")
            if image_filename_obj is None:
                image_filename_obj = page.get("filename", "")
            thumb_filename_obj = page.get("thumb_filename")
            if thumb_filename_obj is None:
                thumb_filename_obj = page.get("thumb", "")
            gallery_pages.append(
                {
                    "page_index": int(page_index_obj),
                    "image_filename": str(image_filename_obj),
                    "thumb_filename": str(thumb_filename_obj),
                }
            )

        gallery_chapters: list[dict[str, ConvertibleToInt]] = []
        for chapter in chapters:
            chapter_index_obj = chapter.get("chapter_index")
            if chapter_index_obj is None:
                chapter_index_obj = chapter.get("number", 0)
            gallery_chapters.append(
                {
                    "id": int(chapter.get("id", 0)),
                    "chapter_index": int(chapter_index_obj),
                    "title": str(chapter.get("title", "Untitled Chapter")),
                    "start_page": int(chapter.get("start_page", 1)),
                    "end_page": int(chapter.get("end_page", 1)),
                }
            )

        return render_html_template(
            request,
            response,
            "work-edit.html",
            {
                "__WORK_ID__": escape(work_id),
                "__EDIT_TITLE__": escape(str(work.get("title", "Untitled"))),
                "__EDIT_SUMMARY__": escape(str(work.get("summary", ""))),
                "__EDIT_RATING_OPTIONS_HTML__": render_options_html(
                    RATING_CHOICES,
                    str(work.get("rating", "Not Rated")),
                ),
                "__EDIT_WARNINGS__": escape(warnings_text),
                "__EDIT_LANGUAGE__": escape(str(work.get("language", "en"))),
                "__EDIT_SERIES__": escape(str(work.get("series_name", "") if work.get("series_name", "") else "")),
                "__EDIT_SERIES_INDEX__": escape(
                    str(work.get("series_index", "") if work.get("series_index", "") else "")
                ),
                "__EDIT_PUBLISHED_AT__": escape(
                    str(work.get("published_at", "") if work.get("published_at", "") else "")
                ),
                "__EDIT_FANDOMS__": escape(_tag_names_csv(tags, "fandom")),
                "__EDIT_RELATIONSHIPS__": escape(_tag_names_csv(tags, "relationship")),
                "__EDIT_CHARACTERS__": escape(_tag_names_csv(tags, "character")),
                "__EDIT_FREEFORM_TAGS__": escape(_tag_names_csv(tags, "freeform")),
                "__STATUS_IN_PROGRESS_SELECTED__": selected_attr(str(work.get("status", "in_progress")), "in_progress"),
                "__STATUS_COMPLETE_SELECTED__": selected_attr(str(work.get("status", "in_progress")), "complete"),
                "__EDIT_STATUS_TEXT__": edit_status.text,
                "__EDIT_STATUS_CLASS__": edit_status.css_class,
                "__EDIT_STATUS_HIDDEN_ATTR__": edit_status.hidden_attr,
                "__EDITOR_WORK_ID__": escape(work_id),
                "__EDITOR_TITLE__": escape(str(work.get("title", "Untitled"))),
                "__EDITOR_SUMMARY__": escape(str(work.get("summary", ""))),
                "__EDITOR_RATING_OPTIONS_HTML__": render_options_html(
                    RATING_CHOICES,
                    str(work.get("rating", "Not Rated")),
                ),
                "__EDITOR_STATUS_IN_PROGRESS_SELECTED__": selected_attr(
                    str(work.get("status", "in_progress")), "in_progress"
                ),
                "__EDITOR_STATUS_COMPLETE_SELECTED__": selected_attr(
                    str(work.get("status", "in_progress")), "complete"
                ),
                "__EDITOR_LANGUAGE__": escape(str(work.get("language", "en"))),
                "__EDITOR_PAGE_GALLERY_HTML__": render_editor_page_gallery_html(
                    work_id,
                    gallery_pages,
                    gallery_chapters,
                ),
                "__EDITOR_CHAPTERS_HTML__": render_editor_chapters_html(
                    work_id,
                    gallery_chapters,
                    form_action=f"/comic/{work_id}/edit",
                    action_field_name="edit_action",
                    update_action_value="editor-update-chapter",
                    delete_action_value="editor-delete-chapter",
                    delete_confirm_message="Delete this chapter?",
                ),
                **render_common_tag_datalist_replacements(),
            },
        )

    back_href = request.args.get("back", "").strip()

    if len(tail) in {2, 3} and tail[1] == "versions":
        work_id = tail[0]
        work = deps.get_work(work_id)
        if not work:
            return text_error(response, "Work not found", 404)

        username = deps.current_user(request)
        if not deps.can_view_work(username, work):
            return text_error(response, "Work not found", 404)

        reader_query = {"back": back_href} if back_href else {}
        reader_query_string = urlencode(reader_query)
        reader_href = (
            f"/tools/reader/{escape(work_id)}?{reader_query_string}"
            if reader_query_string
            else f"/tools/reader/{escape(work_id)}"
        )
        versions = deps.list_work_versions(work_id, 50)
        if not versions:
            work_href = f"/comic/{escape(work_id)}"
            if back_href:
                work_href += f"?back={quote(back_href, safe='')}"
            return deps.render_html_template(
                request,
                response,
                "work-versions.html",
                {
                    "__WORK_TITLE__": escape(str(work.get("title", "Untitled"))),
                    "__WORK_HREF__": work_href,
                    "__WORK_READER_HREF__": reader_href,
                    "__WORK_VERSIONS_LIST_HTML__": '<p class="profile-meta">No versions recorded yet.</p>',
                    "__VERSION_STATUS__": "No versions recorded yet.",
                    "__VERSION_STATUS_CLASS__": "",
                    "__VERSION_READER_HREF__": reader_href,
                    "__VERSION_METADATA_HTML__": '<p class="profile-meta">No snapshot metadata available.</p>',
                },
            )

        selected_version_id = ""
        if len(tail) == 3:
            selected_version_id = tail[2]
        if not selected_version_id:
            selected_version_id = str(versions[0].get("version_id", ""))

        version_manifest = deps.get_work_version_manifest(work_id, selected_version_id)
        if version_manifest is None:
            return text_error(response, "Version not found", 404)

        version_reader_query = {"version_id": selected_version_id}
        if back_href:
            version_reader_query["back"] = back_href
        version_reader_query_string = urlencode(version_reader_query)
        version_reader_href = f"/tools/reader/{escape(work_id)}?{version_reader_query_string}"
        work_href = f"/comic/{escape(work_id)}"
        if back_href:
            work_href += f"?back={quote(back_href, safe='')}"
        return deps.render_html_template(
            request,
            response,
            "work-versions.html",
            {
                "__WORK_TITLE__": escape(str(work.get("title", "Untitled"))),
                "__WORK_HREF__": work_href,
                "__WORK_READER_HREF__": reader_href,
                "__WORK_VERSIONS_LIST_HTML__": _work_versions_list_html(
                    work_id,
                    selected_version_id,
                    back_href=back_href,
                ),
                "__VERSION_STATUS__": escape(f"Viewing version {selected_version_id}"),
                "__VERSION_STATUS_CLASS__": "success",
                "__VERSION_READER_HREF__": version_reader_href,
                "__VERSION_METADATA_HTML__": _version_metadata_html(version_manifest),
            },
        )

    if len(tail) != 1:
        return text_error(response, "Not found", 404)

    work_id = tail[0]
    work = deps.get_work(work_id)
    if not work:
        return text_error(response, "Work not found", 404)

    username = deps.current_user(request)
    if not deps.can_view_work(username, work):
        return text_error(response, "Work not found", 404)

    title = escape(str(work.get("title", "Untitled")))
    summary_raw = str(work.get("summary", ""))
    summary = escape(summary_raw if summary_raw else "No summary provided.")
    rating_html = rating_badge_html(work.get("rating", "Not Rated"))
    status = escape(str(work.get("status", "in_progress")))
    page_count = escape(str(work.get("page_count", 0)))
    cover_page_index_raw = work.get("cover_page_index", 1)
    if isinstance(cover_page_index_raw, int):
        cover_page_index = cover_page_index_raw
    elif isinstance(cover_page_index_raw, str):
        stripped_cover = cover_page_index_raw.strip()
        cover_page_index = int(stripped_cover) if stripped_cover else 1
    else:
        cover_page_index = 1
    cover_files = deps.get_page_files(work_id, cover_page_index)
    cover_image_name = str(cover_files["image"]).strip() if cover_files else ""
    work_id_quoted = quote(work_id, safe="")
    if cover_image_name:
        cover_src = media_url(f"/static/{work_id_quoted}/pages/{quote(cover_image_name, safe='/')}")
    else:
        cover_src = media_url("/static/logo.png")

    tags_obj = work.get("tags", [])
    tag_html = ""
    if isinstance(tags_obj, list):
        rendered_tags: list[str] = []
        for tag_obj in cast(list[Any], tags_obj):
            if isinstance(tag_obj, dict):
                tag = cast(dict[str, Any], tag_obj)
                tag_type = escape(str(tag.get("type", "tag")))
                tag_name = escape(str(tag.get("name", "")))
                rendered_tags.append(f'<span class="tag">{tag_type}: {tag_name}</span>')
        tag_html = "".join(rendered_tags)

    uploader = str(work.get("uploader_username") if work.get("uploader_username") else "")
    user_role = deps.role_for_user(username)
    is_admin = is_privileged_role(user_role)
    can_edit = _can_edit_work(username, uploader, is_admin=is_admin)
    can_delete = is_admin
    comments = cast(list[dict[str, Any]], list(deps.list_work_comments(work_id)))
    kudos = deps.work_kudos_count(work_id)
    has_kudoed = deps.has_user_kudoed_work(work_id, username)
    progress_user_id = username if username else "anon"
    bookmark_page_index = deps.load_progress(work_id, progress_user_id)

    msg = request.args.get("msg", "").strip()
    work_status = _status_for_work_message(msg)

    reader_query = {"back": back_href} if back_href else {}
    reader_query_string = urlencode(reader_query)
    reader_href = (
        f"/tools/reader/{escape(work_id)}?{reader_query_string}"
        if reader_query_string
        else f"/tools/reader/{escape(work_id)}"
    )
    versions_href = f"/comic/{escape(work_id)}/versions"
    if back_href:
        versions_href += f"?back={quote(back_href, safe='')}"

    return deps.render_html_template(
        request,
        response,
        "work.html",
        {
            "__WORK_TITLE__": title,
            "__WORK_SUMMARY__": summary,
            "__WORK_META__": f"{rating_html} | {status} | {page_count} pages",
            "__WORK_COVER_SRC__": cover_src,
            "__WORK_READ_HREF__": reader_href,
            "__WORK_DOWNLOAD_HREF__": f"/api/comic/{escape(work_id)}/download",
            "__WORK_VERSIONS_HREF__": versions_href,
            "__WORK_TAGS_HTML__": tag_html,
            "__EDIT_METADATA_HREF__": f"/comic/{escape(work_id)}/edit",
            "__EDIT_METADATA_HIDDEN_ATTR__": "" if can_edit else "hidden",
            "__ADMIN_DELETE_HIDDEN_ATTR__": "" if can_delete else "hidden",
            "__WORK_ID__": escape(work_id),
            "__WORK_KUDOS_COUNT__": escape(str(kudos)),
            "__KUDOS_DISABLED_ATTR__": "disabled" if (not username or has_kudoed) else "",
            "__WORK_STATUS_TEXT__": work_status.text,
            "__WORK_STATUS_CLASS__": work_status.css_class,
            "__WORK_STATUS_HIDDEN_ATTR__": work_status.hidden_attr,
            "__COMMENTS_HTML__": _comment_cards_html(comments),
            "__REPORT_ISSUE_OPTIONS_HTML__": report_issue_options_html("copyright-dmca"),
            "__DMCA_WORK_ID__": escape(work_id),
            "__DMCA_WORK_TITLE__": title,
            "__DMCA_CLAIMED_URL__": f"/comic/{escape(work_id)}",
            "__WORK_BOOKMARK_WORK_ID__": escape(work_id),
            "__WORK_BOOKMARK_USER_ID__": escape(progress_user_id),
            "__WORK_BOOKMARK_PAGE_INDEX__": escape(str(bookmark_page_index)),
        },
    )


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    return _main_with_deps(request, response, _runtime_deps())


def main_with_deps(
    request: RequestLike,
    response: ResponseLike,
    deps: ComicGetDependencies,
) -> ResponseLike:
    return _main_with_deps(request, response, deps)
