from __future__ import annotations

from fanic.cylinder_sites.common import (
    RequestLike,
    ResponseLike,
    clear_login_cookie,
    text_error,
)


def _redirect(response: ResponseLike, location: str) -> ResponseLike:
    response.status_code = 303
    response.content_type = "text/plain; charset=utf-8"
    response.headers["Location"] = location
    response.set_data(f"See Other: {location}")
    return response


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    if request.path != "/logout":
        return text_error(response, "Not found", 404)

    clear_login_cookie(response)
    return _redirect(response, "/login?msg=logged_out")
