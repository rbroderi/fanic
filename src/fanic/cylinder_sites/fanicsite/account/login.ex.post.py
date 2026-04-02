from fanic.cylinder_sites.common.protocols import RequestLike
from fanic.cylinder_sites.common.protocols import ResponseLike
from fanic.cylinder_sites.common.responses import redirect_see_other as _redirect
from fanic.cylinder_sites.common.security import enforce_https_termination
from fanic.cylinder_sites.common.responses import text_error
from fanic.cylinder_sites.common.security import validate_csrf
from fanic.settings import get_settings


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
