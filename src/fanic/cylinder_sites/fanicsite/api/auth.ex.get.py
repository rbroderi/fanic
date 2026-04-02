from fanic.cylinder_sites.common.protocols import RequestLike
from fanic.cylinder_sites.common.protocols import ResponseLike
from fanic.cylinder_sites.common.session import current_user
from fanic.cylinder_sites.common.responses import json_response
from fanic.cylinder_sites.common.security import route_tail


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    tail = route_tail(request, ["api", "auth"])
    if tail != ["me"]:
        return json_response(response, {"detail": "Not found"}, 404)

    username = current_user(request)
    return json_response(
        response,
        {
            "logged_in": username is not None,
            "username": username if username else "",
        },
    )
