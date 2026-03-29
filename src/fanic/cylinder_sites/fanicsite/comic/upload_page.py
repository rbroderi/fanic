import json
from html import escape
from typing import TYPE_CHECKING
from typing import Any
from typing import cast

if TYPE_CHECKING:
    from _typeshed import ConvertibleToInt
else:
    type ConvertibleToInt = int | str | bytes

from fanic.cylinder_sites.common import RequestLike
from fanic.cylinder_sites.common import ResponseLike
from fanic.cylinder_sites.common import current_user
from fanic.cylinder_sites.common import render_html_template
from fanic.cylinder_sites.editor_gallery import render_editor_chapters_html
from fanic.cylinder_sites.editor_gallery import render_editor_page_gallery_html
from fanic.cylinder_sites.editor_metadata import RATING_CHOICES
from fanic.cylinder_sites.editor_metadata import render_common_tag_datalist_replacements
from fanic.cylinder_sites.editor_metadata import render_options_html
from fanic.cylinder_sites.editor_metadata import selected_attr


def _as_csv(value: object) -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in cast(list[Any], value) if str(item).strip())
    if isinstance(value, str):
        return value
    return ""


def _status_class(kind: str) -> str:
    if kind == "error":
        return "error"
    if kind == "success":
        return "success"
    return ""


def render_upload_page(
    request: RequestLike,
    response: ResponseLike,
    *,
    metadata: dict[str, object] | None = None,
    show_metadata_form: bool = False,
    upload_token: str = "",
    editor_work_id: str = "",
    editor_title: str = "",
    editor_summary: str = "",
    editor_rating: str = "Not Rated",
    editor_status: str = "in_progress",
    editor_language: str = "en",
    editor_pages: list[dict[str, ConvertibleToInt]] | None = None,
    editor_chapters: list[dict[str, ConvertibleToInt]] | None = None,
    upload_status_text: str = "",
    upload_status_kind: str = "",
    ingest_status: str = "",
    ingest_status_kind: str = "",
    result_payload: dict[str, object] | None = None,
    form_action: str = "",
) -> ResponseLike:
    user = current_user(request)
    logged_in = user is not None

    data = metadata if metadata else {}
    pages: list[dict[str, ConvertibleToInt]] = editor_pages if editor_pages else []
    chapters: list[dict[str, ConvertibleToInt]] = editor_chapters if editor_chapters else []
    resolved_form_action = form_action.strip() if form_action.strip() else request.path
    if resolved_form_action != "/comic/upload":
        resolved_form_action = "/comic/upload"
    status_text = upload_status_text if upload_status_text else ingest_status
    status_kind = upload_status_kind if upload_status_kind else ingest_status_kind

    replacements = {
        "__LOGIN_REQUIRED_HIDDEN_ATTR__": "hidden" if logged_in else "",
        "__UPLOAD_HIDDEN_ATTR__": "" if logged_in else "hidden",
        "__AUTH_STATUS__": f"Logged in as {user}." if logged_in and user else "Not logged in.",
        "__AUTH_STATUS_CLASS__": "" if logged_in else "error",
        "__METADATA_FORM_HIDDEN_ATTR__": "" if show_metadata_form else "hidden",
        "__INGEST_FORM_ACTION__": escape(resolved_form_action),
        "__UPLOAD_TOKEN__": escape(upload_token),
        "__EDITOR_WORK_ID__": escape(editor_work_id),
        "__EDITOR_TERMS_REQUIRED_ATTR__": "required" if not editor_work_id else "",
        "__EDITOR_TITLE__": escape(editor_title),
        "__EDITOR_SUMMARY__": escape(editor_summary),
        "__EDITOR_RATING_OPTIONS_HTML__": render_options_html(
            RATING_CHOICES,
            editor_rating,
        ),
        "__EDITOR_RATING_VALUE__": escape(editor_rating),
        "__EDITOR_STATUS_IN_PROGRESS_SELECTED__": selected_attr(
            editor_status,
            "in_progress",
        ),
        "__EDITOR_STATUS_COMPLETE_SELECTED__": selected_attr(editor_status, "complete"),
        "__EDITOR_STATUS_VALUE__": escape(editor_status),
        "__EDITOR_LANGUAGE__": escape(editor_language),
        "__EDITOR_LINKS_HIDDEN_ATTR__": "" if editor_work_id else "hidden",
        "__EDITOR_WORK_HREF__": f"/comic/{escape(editor_work_id)}",
        "__EDITOR_READER_HREF__": f"/tools/reader/{escape(editor_work_id)}",
        "__EDITOR_MANAGER_HIDDEN_ATTR__": "" if editor_work_id else "hidden",
        "__EDITOR_PAGE_GALLERY_HTML__": render_editor_page_gallery_html(
            editor_work_id,
            pages,
            chapters,
        ),
        "__EDITOR_CHAPTERS_HTML__": render_editor_chapters_html(
            editor_work_id,
            chapters,
            form_action=resolved_form_action,
            action_field_name="action",
            update_action_value="editor-update-chapter",
            delete_action_value="editor-delete-chapter",
        ),
        "__INGEST_STATUS__": escape(status_text),
        "__INGEST_STATUS_CLASS__": _status_class(status_kind),
        "__INGEST_STATUS_HIDDEN_ATTR__": "" if status_text else "hidden",
        "__META_TITLE__": escape(str(data.get("title", ""))),
        "__META_SUMMARY__": escape(str(data.get("summary", ""))),
        "__META_RATING_OPTIONS_HTML__": render_options_html(
            RATING_CHOICES,
            str(data.get("rating", "Not Rated")),
        ),
        "__META_WARNINGS__": escape(_as_csv(data.get("warnings", ""))),
        "__META_LANGUAGE__": escape(str(data.get("language", "en"))),
        "__META_SERIES__": escape(str(data.get("series", ""))),
        "__META_SERIES_INDEX__": escape(str(data.get("series_index", ""))),
        "__META_PUBLISHED_AT__": escape(str(data.get("published_at", ""))),
        "__META_FANDOMS__": escape(_as_csv(data.get("fandoms", ""))),
        "__META_RELATIONSHIPS__": escape(_as_csv(data.get("relationships", ""))),
        "__META_CHARACTERS__": escape(_as_csv(data.get("characters", ""))),
        "__META_FREEFORM_TAGS__": escape(_as_csv(data.get("freeform_tags", ""))),
        "__STATUS_IN_PROGRESS_SELECTED__": selected_attr(
            str(data.get("status", "in_progress")),
            "in_progress",
        ),
        "__STATUS_COMPLETE_SELECTED__": selected_attr(
            str(data.get("status", "in_progress")),
            "complete",
        ),
    }
    replacements.update(render_common_tag_datalist_replacements())

    if result_payload is not None:
        replacements["__INGEST_RESULT_HIDDEN_ATTR__"] = ""
        replacements["__INGEST_RESULT__"] = escape(json.dumps(result_payload, ensure_ascii=True, indent=2))
    else:
        replacements["__INGEST_RESULT_HIDDEN_ATTR__"] = "hidden"
        replacements["__INGEST_RESULT__"] = ""

    return render_html_template(
        request,
        response,
        "comic-upload.html",
        replacements,
    )
