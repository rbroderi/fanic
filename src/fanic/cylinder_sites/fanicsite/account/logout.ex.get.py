from urllib.parse import urlencode
from urllib.parse import urljoin

from fanic.auth0_client import auth0_config_from_settings
from fanic.cylinder_sites.common import RequestLike
from fanic.cylinder_sites.common import ResponseLike
from fanic.cylinder_sites.common import clear_auth0_oauth_cookie
from fanic.cylinder_sites.common import clear_login_cookie
from fanic.cylinder_sites.common import text_error
from fanic.settings import get_settings


def _redirect(response: ResponseLike, location: str) -> ResponseLike:
    response.status_code = 303
    response.content_type = "text/plain; charset=utf-8"
    response.headers["Location"] = location
    response.set_data(f"See Other: {location}")
    return response


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    if request.path != "/account/logout":
        return text_error(response, "Not found", 404)

    clear_login_cookie(response)
    clear_auth0_oauth_cookie(response)

    settings = get_settings()
    if not settings.auth0_configured:
        return _redirect(response, "/account/logged-out")

    config = auth0_config_from_settings(settings)
    return_to = urljoin(config.logout_return_url, "/account/logged-out")
    params = urlencode({"client_id": config.client_id, "returnTo": return_to})
    return _redirect(response, f"{config.logout_endpoint}?{params}")
