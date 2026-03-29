from urllib.parse import urlencode
from urllib.parse import urljoin

from fanic.auth0_client import auth0_config_from_settings
from fanic.cylinder_sites.common import RequestLike
from fanic.cylinder_sites.common import ResponseLike
from fanic.cylinder_sites.common import clear_auth0_oauth_cookie
from fanic.cylinder_sites.common import clear_login_cookie
from fanic.cylinder_sites.common import enforce_https_termination
from fanic.cylinder_sites.common import text_error
from fanic.cylinder_sites.common import validate_csrf
from fanic.settings import get_settings


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
    forwarded_proto = str(forwarded_proto_raw).split(",")[0].strip() if forwarded_proto_raw else ""
    forwarded_host_raw = headers.get("X-Forwarded-Host", "")
    host_header_raw = headers.get("Host", "")
    host_source = forwarded_host_raw if forwarded_host_raw else host_header_raw
    host = str(host_source).split(",")[0].strip() if host_source else ""
    if not host:
        return ""

    scheme = forwarded_proto if forwarded_proto else "https"
    return f"{scheme}://{host}/"


def _redirect(response: ResponseLike, location: str) -> ResponseLike:
    response.status_code = 303
    response.content_type = "text/plain; charset=utf-8"
    response.headers["Location"] = location
    response.set_data(f"See Other: {location}")
    return response


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    if request.path != "/account/logout":
        return text_error(response, "Not found", 404)

    if not enforce_https_termination(request, response):
        return response

    if not validate_csrf(request):
        return text_error(response, "Invalid CSRF token", 403)

    clear_login_cookie(response)
    clear_auth0_oauth_cookie(response)

    settings = get_settings()
    if not settings.auth0_configured:
        return _redirect(response, "/account/logged-out")

    config = auth0_config_from_settings(settings)
    return_to = urljoin(config.logout_return_url, "/account/logged-out")
    params = urlencode({"client_id": config.client_id, "returnTo": return_to})
    return _redirect(response, f"{config.logout_endpoint}?{params}")
