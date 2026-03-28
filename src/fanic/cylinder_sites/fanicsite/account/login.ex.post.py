from fanic.cylinder_sites.common import RequestLike
from fanic.cylinder_sites.common import ResponseLike
from fanic.cylinder_sites.common import enforce_https_termination
from fanic.cylinder_sites.common import text_error
from fanic.cylinder_sites.common import validate_csrf
from fanic.settings import get_settings


def _redirect(response: ResponseLike, location: str) -> ResponseLike:
    response.status_code = 303
    response.content_type = "text/plain; charset=utf-8"
    response.headers["Location"] = location
    response.set_data(f"See Other: {location}")
    return response


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    if request.path != "/account/login":
        return text_error(response, "Not found", 404)

    if not enforce_https_termination(request, response):
        return response

    if not validate_csrf(request):
        return _redirect(response, "/account/login?msg=csrf-invalid")

    settings = get_settings()
    if not settings.auth0_configured:
        return _redirect(response, "/account/login?msg=auth-disabled")

    next_url = request.form.get("next", "").strip()
    if next_url.startswith("/") and not next_url.startswith("//"):
        return _redirect(response, f"/account/auth0/login?next={next_url}")
    return _redirect(response, "/account/auth0/login")
