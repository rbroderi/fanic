from __future__ import annotations

from urllib.parse import quote

from fanic.cylinder_sites.common import RequestLike
from fanic.cylinder_sites.common import ResponseLike
from fanic.cylinder_sites.common import check_post_rate_limit
from fanic.cylinder_sites.common import current_user
from fanic.cylinder_sites.common import enforce_https_termination
from fanic.cylinder_sites.common import text_error
from fanic.cylinder_sites.common import validate_csrf
from fanic.cylinder_sites.common import validate_field_lengths
from fanic.cylinder_sites.feedback_categories import feedback_category_label
from fanic.cylinder_sites.feedback_categories import normalize_feedback_category
from fanic.repository import add_dmca_report


def _redirect(response: ResponseLike, location: str) -> ResponseLike:
    response.status_code = 303
    response.content_type = "text/plain; charset=utf-8"
    response.headers["Location"] = location
    response.set_data(f"See Other: {location}")
    return response


def _is_non_empty(value: str) -> bool:
    return bool(value.strip())


def _combined_details(summary: str, details: str) -> str:
    clean_summary = summary.strip()
    clean_details = details.strip()
    return f"Summary:\n{clean_summary}\n\nDetails:\n{clean_details}"


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    if request.path != "/feedback":
        return text_error(response, "Not found", 404)

    if not enforce_https_termination(request, response):
        return response

    if not validate_csrf(request):
        return text_error(response, "Invalid CSRF token", 403)

    retry_after = check_post_rate_limit(request)
    if retry_after:
        response.headers["Retry-After"] = str(retry_after)
        return text_error(response, "Too many requests. Please try again later.", 429)

    reporter_name = request.form.get("reporter_name", "").strip()
    reporter_email = request.form.get("reporter_email", "").strip()
    category = normalize_feedback_category(request.form.get("category", ""))
    page_url = request.form.get("page_url", "").strip()
    summary = request.form.get("summary", "").strip()
    details = request.form.get("details", "").strip()
    screenshot_url = request.form.get("screenshot_url", "").strip()

    length_error = validate_field_lengths(
        {
            "reporter_name": reporter_name,
            "reporter_email": reporter_email,
            "page_url": page_url,
            "summary": summary,
            "details": details,
            "screenshot_url": screenshot_url,
        },
        short={"reporter_name", "reporter_email", "summary"},
        url={"page_url", "screenshot_url"},
        long={"details"},
    )
    if length_error:
        return _redirect(response, "/feedback?msg=invalid")

    if (
        not _is_non_empty(reporter_name)
        or not _is_non_empty(reporter_email)
        or not _is_non_empty(category)
        or not _is_non_empty(summary)
        or not _is_non_empty(details)
    ):
        return _redirect(response, "/feedback?msg=invalid")

    report_id = add_dmca_report(
        work_id=None,
        work_title="",
        issue_type=category,
        reporter_name=reporter_name,
        reporter_email=reporter_email,
        reason=feedback_category_label(category),
        claimed_url=page_url,
        evidence_url=screenshot_url,
        details=_combined_details(summary, details),
        reporter_username=current_user(request),
        source_path=request.path,
    )
    return _redirect(
        response,
        f"/feedback?msg=submitted&report_id={quote(str(report_id))}",
    )
