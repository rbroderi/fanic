from __future__ import annotations

from fanic.cylinder_sites.common import (
    ADMIN_PASSWORD,
    ADMIN_USERNAME,
    RequestLike,
    ResponseLike,
    clear_login_cookie,
    json_response,
    route_tail,
    set_login_cookie,
)


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    tail = route_tail(request, ["api", "auth"])
    if tail is None or len(tail) != 1:
        return json_response(response, {"detail": "Not found"}, 404)

    action = tail[0]

    if action == "login":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if username != ADMIN_USERNAME or password != ADMIN_PASSWORD:
            return json_response(response, {"detail": "Invalid credentials"}, 401)

        set_login_cookie(response, username)
        return json_response(response, {"ok": True, "username": username})

    if action == "logout":
        clear_login_cookie(response)
        return json_response(response, {"ok": True})

    return json_response(response, {"detail": "Not found"}, 404)
