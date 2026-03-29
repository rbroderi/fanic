from dataclasses import dataclass
from html import escape

from fanic.cylinder_sites.common import RequestLike
from fanic.cylinder_sites.common import ResponseLike
from fanic.cylinder_sites.common import render_html_template
from fanic.cylinder_sites.editor_metadata import RATING_CHOICES
from fanic.cylinder_sites.editor_metadata import render_options_html


@dataclass(frozen=True, slots=True)
class StatusMessage:
    text: str
    css_class: str
    hidden_attr: str


def _status_for_work_upload_message(msg: str) -> StatusMessage:
    match msg:
        case "uploaded":
            return StatusMessage("Fanart uploaded.", "success", "")
        case "uploaded-rating-elevated":
            return StatusMessage(
                "Fanart uploaded. Rating auto-elevated based on moderation detection.",
                "success",
                "",
            )
        case "invalid":
            return StatusMessage("Please complete all required fields.", "error", "")
        case "missing-file":
            return StatusMessage("Choose an image file to upload.", "error", "")
        case "policy":
            return StatusMessage("Upload rejected by file policy.", "error", "")
        case "blocked":
            return StatusMessage(
                "Upload blocked by moderation policy (photorealistic images are not allowed).",
                "error",
                "",
            )
        case "login-required":
            return StatusMessage("Login required before uploading fanart.", "error", "")
        case "terms":
            return StatusMessage(
                "You must agree to the Terms and Conditions before uploading.",
                "error",
                "",
            )
        case _:
            return StatusMessage("", "", "hidden")


def render_upload_page(
    request: RequestLike,
    response: ResponseLike,
) -> ResponseLike:
    work_upload_msg = request.args.get("msg", "").strip()
    status = _status_for_work_upload_message(work_upload_msg)
    return render_html_template(
        request,
        response,
        "fanart-upload.html",
        {
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
        },
    )
