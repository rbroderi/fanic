from dataclasses import dataclass
from html import escape
from urllib.parse import urljoin
from urllib.parse import urlparse

from fanic.cylinder_sites.common import RequestLike
from fanic.cylinder_sites.common import ResponseLike
from fanic.cylinder_sites.common import render_html_template
from fanic.cylinder_sites.common import text_error
from fanic.cylinder_sites.report_issues import normalize_report_issue_type
from fanic.cylinder_sites.report_issues import report_issue_options_html


@dataclass(frozen=True, slots=True)
class StatusReplacements:
    text: str
    css_class: str
    hidden_attr: str


def _status_replacements(msg: str, report_id: str) -> StatusReplacements:
    match msg:
        case "submitted":
            return StatusReplacements(
                "Report submitted."
                + (f" Reference #{escape(report_id)}." if report_id else ""),
                "success",
                "",
            )
        case "invalid":
            return StatusReplacements(
                "Please complete all required fields and certify your claim.",
                "error",
                "",
            )
        case _:
            return StatusReplacements("", "", "hidden")


def _request_base_url(request: RequestLike) -> str:
    host_url_raw = getattr(request, "host_url", "")
    host_url = host_url_raw.strip() if isinstance(host_url_raw, str) else ""
    if host_url:
        return host_url

    url_root_raw = getattr(request, "url_root", "")
    url_root = url_root_raw.strip() if isinstance(url_root_raw, str) else ""
    if url_root:
        return url_root

    headers = getattr(request, "headers", None)
    if headers is None or not hasattr(headers, "get"):
        return ""

    forwarded_proto_raw = headers.get("X-Forwarded-Proto", "")
    forwarded_proto = (
        str(forwarded_proto_raw).split(",")[0].strip() if forwarded_proto_raw else ""
    )
    forwarded_host_raw = headers.get("X-Forwarded-Host", "")
    host_header_raw = headers.get("Host", "")
    host_source = forwarded_host_raw if forwarded_host_raw else host_header_raw
    host = str(host_source).split(",")[0].strip() if host_source else ""
    if not host:
        return ""

    scheme = forwarded_proto if forwarded_proto else "https"
    return f"{scheme}://{host}/"


def _normalize_claimed_url(request: RequestLike, claimed_url: str) -> str:
    cleaned = claimed_url.strip()
    if not cleaned:
        return ""

    parsed = urlparse(cleaned)
    if parsed.scheme and parsed.netloc:
        return cleaned

    base_url = _request_base_url(request)
    if not base_url:
        return cleaned

    if cleaned.startswith("/"):
        return urljoin(base_url, cleaned)

    if cleaned.startswith("works/"):
        return urljoin(base_url, f"/{cleaned}")

    return cleaned


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    if request.path != "/dmca":
        return text_error(response, "Not found", 404)

    msg = request.args.get("msg", "").strip()
    report_id = request.args.get("report_id", "").strip()
    status = _status_replacements(msg, report_id)

    work_id = request.args.get("work_id", "").strip()
    work_title = request.args.get("work_title", "").strip()
    claimed_url = _normalize_claimed_url(
        request,
        request.args.get("claimed_url", ""),
    )
    issue_type = normalize_report_issue_type(
        request.args.get("issue_type", "copyright-dmca")
    )

    return render_html_template(
        request,
        response,
        "dmca.html",
        {
            "__DMCA_STATUS_TEXT__": status.text,
            "__DMCA_STATUS_CLASS__": status.css_class,
            "__DMCA_STATUS_HIDDEN_ATTR__": status.hidden_attr,
            "__DMCA_WORK_ID__": escape(work_id),
            "__DMCA_WORK_TITLE__": escape(work_title),
            "__DMCA_CLAIMED_URL__": escape(claimed_url),
            "__REPORT_ISSUE_OPTIONS_HTML__": report_issue_options_html(issue_type),
        },
    )
