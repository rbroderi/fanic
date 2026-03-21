from __future__ import annotations

from fanic.cylinder_sites.common import (
    RequestLike,
    ResponseLike,
    current_user,
    text_error,
)
from fanic.repository import set_user_prefers_explicit


def _redirect(response: ResponseLike, location: str) -> ResponseLike:
    response.status_code = 303
    response.content_type = "text/plain; charset=utf-8"
    response.headers["Location"] = location
    response.set_data(f"See Other: {location}")
    return response


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    if request.path != "/profile":
        return text_error(response, "Not found", 404)

    username = current_user(request)
    if not username:
        return text_error(response, "Forbidden", 403)

    view_explicit = request.form.get("view_explicit_rated", "") == "on"
    set_user_prefers_explicit(username, view_explicit)
    return _redirect(response, "/profile?msg=saved")
