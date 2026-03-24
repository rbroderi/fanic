from __future__ import annotations

from fanic.cylinder_sites.common import (
    RequestLike,
    ResponseLike,
    route_tail,
    safe_static_path,
    send_file,
    text_error,
)


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    tail = route_tail(request, ["static"])
    if tail is None or len(tail) == 0:
        return text_error(response, "Not found", 404)

    file_path = safe_static_path("/".join(tail))
    if file_path is None:
        return text_error(response, "Not found", 404)

    return send_file(response, file_path)

