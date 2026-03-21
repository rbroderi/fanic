from __future__ import annotations

from fanic.cylinder_sites.common import (
    ADMIN_PASSWORD,
    ADMIN_USERNAME,
    RequestLike,
    ResponseLike,
    set_login_cookie,
    text_error,
)


def _redirect(response: ResponseLike, location: str) -> ResponseLike:
    response.status_code = 303
    response.content_type = "text/plain; charset=utf-8"
    response.headers["Location"] = location
    response.set_data(f"See Other: {location}")
    return response


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    if request.path != "/login":
        return text_error(response, "Not found", 404)

    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")

    if username != ADMIN_USERNAME or password != ADMIN_PASSWORD:
        return _redirect(response, "/login?msg=invalid")

    set_login_cookie(response, username)
    return _redirect(response, "/login?msg=success")
