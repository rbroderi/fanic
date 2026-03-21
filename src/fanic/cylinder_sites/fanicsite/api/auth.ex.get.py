from __future__ import annotations

from fanic.cylinder_sites.common import (
    RequestLike,
    ResponseLike,
    current_user,
    json_response,
    route_tail,
)


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    tail = route_tail(request, ["api", "auth"])
    if tail != ["me"]:
        return json_response(response, {"detail": "Not found"}, 404)

    username = current_user(request)
    return json_response(
        response,
        {
            "logged_in": username is not None,
            "username": username or "",
        },
    )
