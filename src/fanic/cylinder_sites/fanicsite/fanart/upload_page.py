from html import escape

from fanic.cylinder_sites.common.protocols import RequestLike
from fanic.cylinder_sites.common.protocols import ResponseLike
from fanic.cylinder_sites.common.protocols import StatusReplacements
from fanic.cylinder_sites.common.responses import render_html_template
from fanic.cylinder_sites.common.protocols import status_for_message
from fanic.cylinder_sites.common.protocols import status_visible
from fanic.cylinder_sites.editor_metadata import RATING_CHOICES
from fanic.cylinder_sites.editor_metadata import render_common_tag_datalist_replacements
from fanic.cylinder_sites.editor_metadata import render_options_html


def _status_for_work_upload_message(msg: str) -> StatusReplacements:
    return status_for_message(
        msg,
        {
            "uploaded": status_visible("Fanart uploaded.", "success"),
            "uploaded-rating-elevated": status_visible(
                "Fanart uploaded. Rating auto-elevated based on moderation detection.",
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
