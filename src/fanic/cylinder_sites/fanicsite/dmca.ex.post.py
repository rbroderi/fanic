from urllib.parse import quote

from fanic.cylinder_sites.common import RequestLike
from fanic.cylinder_sites.common import ResponseLike
from fanic.cylinder_sites.common import check_post_rate_limit
from fanic.cylinder_sites.common import current_user
from fanic.cylinder_sites.common import enforce_https_termination
from fanic.cylinder_sites.common import text_error
from fanic.cylinder_sites.common import validate_csrf
from fanic.cylinder_sites.common import validate_field_lengths
from fanic.cylinder_sites.report_issues import normalize_report_issue_type
from fanic.cylinder_sites.report_issues import report_issue_label
from fanic.repository import add_dmca_report


def _redirect(response: ResponseLike, location: str) -> ResponseLike:
    response.status_code = 303
    response.content_type = "text/plain; charset=utf-8"
    response.headers["Location"] = location
    response.set_data(f"See Other: {location}")
    return response


def _is_non_empty(value: str) -> bool:
    return bool(value.strip())


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    if request.path != "/dmca":
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
    issue_type = normalize_report_issue_type(request.form.get("issue_type", ""))
    claimed_url = request.form.get("claimed_url", "").strip()
    details = request.form.get("details", "").strip()
    attest = request.form.get("attest", "").strip().lower()

    length_error = validate_field_lengths(
        {
            "reporter_name": reporter_name,
            "reporter_email": reporter_email,
            "claimed_url": claimed_url,
            "details": details,
        },
        short={"reporter_name", "reporter_email"},
        url={"claimed_url"},
        long={"details"},
    )
    if length_error:
        return _redirect(response, "/dmca?msg=invalid")

    if (
        not _is_non_empty(reporter_name)
        or not _is_non_empty(reporter_email)
        or not _is_non_empty(issue_type)
        or not _is_non_empty(claimed_url)
        or not _is_non_empty(details)
        or attest not in {"on", "true", "1", "yes"}
    ):
        return _redirect(response, "/dmca?msg=invalid")

    reason = report_issue_label(issue_type)
    work_id = request.form.get("work_id", "").strip()
    work_title = request.form.get("work_title", "").strip()
    evidence_url = request.form.get("evidence_url", "").strip()

    report_id = add_dmca_report(
        work_id=work_id if work_id else None,
        work_title=work_title,
        issue_type=issue_type,
        reporter_name=reporter_name,
        reporter_email=reporter_email,
        reason=reason,
        claimed_url=claimed_url,
        evidence_url=evidence_url,
        details=details,
        reporter_username=current_user(request),
        source_path=request.path,
    )
    return _redirect(response, f"/dmca?msg=submitted&report_id={quote(str(report_id))}")
