from html import escape

from fanic.cylinder_sites.common import RequestLike
from fanic.cylinder_sites.common import ResponseLike
from fanic.cylinder_sites.common import StatusReplacements
from fanic.cylinder_sites.common import render_html_template
from fanic.cylinder_sites.common import status_hidden
from fanic.cylinder_sites.common import status_visible
from fanic.cylinder_sites.editor_metadata import RATING_CHOICES
from fanic.cylinder_sites.editor_metadata import render_common_tag_datalist_replacements
from fanic.cylinder_sites.editor_metadata import render_options_html


def _status_for_work_upload_message(msg: str) -> StatusReplacements:
    match msg:
        case "uploaded":
            return status_visible("Fanart uploaded.", "success")
        case "uploaded-rating-elevated":
            return status_visible(
                "Fanart uploaded. Rating auto-elevated based on moderation detection.",
                "success",
            )
        case "invalid":
            return status_visible("Please complete all required fields.", "error")
        case "missing-file":
            return status_visible("Choose an image file to upload.", "error")
        case "policy":
            return status_visible("Upload rejected by file policy.", "error")
        case "blocked":
            return status_visible(
                "Upload blocked by moderation policy (photorealistic images are not allowed).",
                "error",
            )
        case "login-required":
            return status_visible("Login required before uploading fanart.", "error")
        case "terms":
            return status_visible(
                "You must agree to the Terms and Conditions before uploading.",
                "error",
            )
        case _:
            return status_hidden()


def render_upload_page(
    request: RequestLike,
    response: ResponseLike,
) -> ResponseLike:
    work_upload_msg = request.args.get("msg", "").strip()
    status = _status_for_work_upload_message(work_upload_msg)
    replacements = {
        "__UPLOAD_STATUS_TEXT__": status.text,
        "__UPLOAD_STATUS_CLASS__": status.css_class,
        "__UPLOAD_STATUS_HIDDEN_ATTR__": status.hidden_attr,
        "__TITLE__": escape(request.args.get("title", "").strip()),
        "__SUMMARY__": escape(request.args.get("summary", "").strip()),
        "__FANDOM__": escape(request.args.get("fandom", "").strip()),
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
