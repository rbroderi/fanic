from __future__ import annotations

from html import escape

from fanic.cylinder_sites.common import RequestLike
from fanic.cylinder_sites.common import ResponseLike
from fanic.cylinder_sites.common import render_html_template
from fanic.cylinder_sites.common import text_error
from fanic.cylinder_sites.report_issues import normalize_report_issue_type
from fanic.cylinder_sites.report_issues import report_issue_options_html


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    if request.path != "/dmca":
        return text_error(response, "Not found", 404)

    msg = request.args.get("msg", "").strip()
    report_id = request.args.get("report_id", "").strip()

    if msg == "submitted":
        status_text = "Report submitted." + (
            f" Reference #{escape(report_id)}." if report_id else ""
        )
        status_class = "success"
        status_hidden = ""
    elif msg == "invalid":
        status_text = "Please complete all required fields and certify your claim."
        status_class = "error"
        status_hidden = ""
    else:
        status_text = ""
        status_class = ""
        status_hidden = "hidden"

    work_id = request.args.get("work_id", "").strip()
    work_title = request.args.get("work_title", "").strip()
    claimed_url = request.args.get("claimed_url", "").strip()
    issue_type = normalize_report_issue_type(
        request.args.get("issue_type", "copyright-dmca")
    )

    return render_html_template(
        request,
        response,
        "dmca.html",
        {
            "__DMCA_STATUS_TEXT__": status_text,
            "__DMCA_STATUS_CLASS__": status_class,
            "__DMCA_STATUS_HIDDEN_ATTR__": status_hidden,
            "__DMCA_WORK_ID__": escape(work_id),
            "__DMCA_WORK_TITLE__": escape(work_title),
            "__DMCA_CLAIMED_URL__": escape(claimed_url),
            "__REPORT_ISSUE_OPTIONS_HTML__": report_issue_options_html(issue_type),
        },
    )
