from __future__ import annotations

from fanic.cylinder_sites.common import RequestLike
from fanic.cylinder_sites.common import ResponseLike
from fanic.cylinder_sites.common import clear_login_cookie
from fanic.cylinder_sites.common import enforce_https_termination
from fanic.cylinder_sites.common import text_error
from fanic.cylinder_sites.common import validate_csrf


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
    return _redirect(response, "/account/login?msg=logged_out")

