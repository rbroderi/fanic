from urllib.parse import quote

from fanic.cylinder_sites.common import RequestLike
from fanic.cylinder_sites.common import ResponseLike
from fanic.cylinder_sites.common import current_user
from fanic.cylinder_sites.common import enforce_https_termination
from fanic.cylinder_sites.common import role_for_user
from fanic.cylinder_sites.common import route_tail
from fanic.cylinder_sites.common import text_error
from fanic.cylinder_sites.common import validate_csrf
from fanic.repository import delete_fanart_item
from fanic.repository import get_fanart_item


def _redirect(response: ResponseLike, location: str) -> ResponseLike:
    response.status_code = 303
    response.content_type = "text/plain; charset=utf-8"
    response.headers["Location"] = location
    response.set_data(f"See Other: {location}")
    return response


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    tail = route_tail(request, ["fanart"])
    if tail is None:
        return text_error(response, "Not found", 404)

    if not enforce_https_termination(request, response):
        return response

    if not validate_csrf(request):
        return text_error(response, "Invalid CSRF token", 403)

    if len(tail) == 3 and tail[2] == "delete":
        username = current_user(request)
        if role_for_user(username) not in {"superadmin", "admin"}:
            return text_error(response, "Forbidden", 403)

        work_owner_username = tail[0].strip()
        work_id = tail[1].strip()
        if not work_owner_username or not work_id:
            return text_error(response, "Not found", 404)

        work = get_fanart_item(work_id)
        if work is None:
            return text_error(response, "Not found", 404)
        work_owner = str(work.get("uploader_username", "")).strip()
        if work_owner != work_owner_username:
            return text_error(response, "Not found", 404)

        _ = delete_fanart_item(work_id)
        return _redirect(
            response,
            f"/fanart/{quote(work_owner_username, safe='')}?msg=deleted",
        )

    return text_error(response, "Not found", 404)
