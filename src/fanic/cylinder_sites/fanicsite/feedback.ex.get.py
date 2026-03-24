from dataclasses import dataclass
from html import escape

from fanic.cylinder_sites.common import RequestLike
from fanic.cylinder_sites.common import ResponseLike
from fanic.cylinder_sites.common import render_html_template
from fanic.cylinder_sites.common import text_error
from fanic.cylinder_sites.feedback_categories import feedback_category_options_html
from fanic.cylinder_sites.feedback_categories import normalize_feedback_category


@dataclass(frozen=True, slots=True)
class StatusReplacements:
    text: str
    css_class: str
    hidden_attr: str


def _status_replacements(msg: str, report_id: str) -> StatusReplacements:
    match msg:
        case "submitted":
            suffix = f" Reference #{escape(report_id)}." if report_id else ""
            return StatusReplacements(f"Feedback submitted.{suffix}", "success", "")
        case "invalid":
            return StatusReplacements(
                "Please complete all required fields.",
                "error",
                "",
            )
        case _:
            return StatusReplacements("", "", "hidden")


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    if request.path != "/feedback":
        return text_error(response, "Not found", 404)

    msg = request.args.get("msg", "").strip()
    report_id = request.args.get("report_id", "").strip()
    status = _status_replacements(msg, report_id)

    page_url = request.args.get("page_url", "").strip()
    category = normalize_feedback_category(request.args.get("category", "usability-ux"))

    return render_html_template(
        request,
        response,
        "feedback.html",
        {
            "__FEEDBACK_STATUS_TEXT__": status.text,
            "__FEEDBACK_STATUS_CLASS__": status.css_class,
            "__FEEDBACK_STATUS_HIDDEN_ATTR__": status.hidden_attr,
            "__FEEDBACK_PAGE_URL__": escape(page_url),
            "__FEEDBACK_CATEGORY_OPTIONS_HTML__": feedback_category_options_html(
                category
            ),
        },
    )
