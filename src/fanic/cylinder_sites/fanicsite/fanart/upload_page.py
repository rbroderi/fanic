import json
from html import escape

from fanic.cylinder_sites.common.protocols import RequestLike
from fanic.cylinder_sites.common.protocols import ResponseLike
from fanic.cylinder_sites.common.protocols import StatusReplacements
from fanic.cylinder_sites.common.protocols import status_for_message
from fanic.cylinder_sites.common.protocols import status_visible
from fanic.cylinder_sites.common.responses import render_html_template
from fanic.cylinder_sites.common.session import current_user
from fanic.cylinder_sites.common.session import role_for_user
from fanic.cylinder_sites.editor_metadata import RATING_CHOICES
from fanic.cylinder_sites.editor_metadata import render_common_tag_datalist_replacements
from fanic.cylinder_sites.editor_metadata import render_options_html
from fanic.cylinder_sites.user_roles import is_privileged_role


def _status_for_work_upload_message(msg: str) -> StatusReplacements:
    return status_for_message(
        msg,
        {
            "uploaded": status_visible("Fanart uploaded.", "success"),
            "uploaded-rating-elevated": status_visible(
                "Fanart uploaded. Rating was auto-promoted to Explicit based on moderation.",
                "success",
            ),
            "invalid": status_visible("Please complete all required fields.", "error"),
            "missing-file": status_visible("Choose an image file to upload.", "error"),
            "policy": status_visible("Upload rejected by file policy.", "error"),
            "blocked": status_visible(
                "Upload blocked by moderation policy (photorealistic images are not allowed).",
                "error",
            ),
            "login-required": status_visible("Login required before uploading fanart.", "error"),
            "terms": status_visible("You must agree to the Terms and Conditions before uploading.", "error"),
        },
    )


def render_upload_page(
    request: RequestLike,
    response: ResponseLike,
) -> ResponseLike:
    work_upload_msg = request.args.get("msg", "").strip()
    status = _status_for_work_upload_message(work_upload_msg)
    moderation_detail = request.args.get("moderation_detail", "").strip()
    username = current_user(request)
    is_admin_user = is_privileged_role(role_for_user(username))
    show_moderation_detail = bool(work_upload_msg == "blocked" and moderation_detail and is_admin_user)

    moderation_detail_text = ""
    if show_moderation_detail:
        try:
            parsed = json.loads(moderation_detail)
            moderation_detail_text = json.dumps(parsed, ensure_ascii=True, indent=2)
        except json.JSONDecodeError:
            moderation_detail_text = moderation_detail

    replacements = {
        "__UPLOAD_STATUS_TEXT__": status.text,
        "__UPLOAD_STATUS_CLASS__": status.css_class,
        "__UPLOAD_STATUS_HIDDEN_ATTR__": status.hidden_attr,
        "__UPLOAD_MODERATION_DETAIL_HIDDEN_ATTR__": "" if show_moderation_detail else "hidden",
        "__UPLOAD_MODERATION_DETAIL_TEXT__": escape(moderation_detail_text),
        "__UPLOAD_TOKEN__": escape(request.args.get("upload_token", "").strip()),
        "__TITLE__": escape(request.args.get("title", "").strip()),
        "__SUMMARY__": escape(request.args.get("summary", "").strip()),
        "__FANDOM__": escape(request.args.get("fandom", "").strip()),
        "__TAGS__": escape(request.args.get("tags", "").strip()),
        "__RATING_OPTIONS_HTML__": render_options_html(
            RATING_CHOICES,
            request.args.get("rating", "Not Rated").strip(),
        ),
    }
    replacements.update(render_common_tag_datalist_replacements())

    return render_html_template(
        request,
        response,
        "fanart-upload.html",
        replacements,
    )
