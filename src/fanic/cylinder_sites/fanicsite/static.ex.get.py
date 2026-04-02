from fanic.cylinder_sites.common.protocols import RequestLike
from fanic.cylinder_sites.common.protocols import ResponseLike
from fanic.cylinder_sites.common.security import route_tail
from fanic.cylinder_sites.common.security import safe_static_path
from fanic.cylinder_sites.common.responses import send_file
from fanic.cylinder_sites.common.responses import text_error


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    tail = route_tail(request, ["static"])
    if tail is None or len(tail) == 0:
        return text_error(response, "Not found", 404)

    file_path = safe_static_path("/".join(tail))
    if file_path is None:
        return text_error(response, "Not found", 404)

    return send_file(response, file_path)
