from typing import Any
from typing import cast

from fanic.auth0_client import auth0_config_from_settings
from fanic.auth0_client import build_oauth_client
from fanic.auth0_client import new_code_verifier
from fanic.cylinder_sites.common import RequestLike
from fanic.cylinder_sites.common import ResponseLike
from fanic.cylinder_sites.common import enforce_https_termination
from fanic.cylinder_sites.common import set_auth0_oauth_cookie
from fanic.cylinder_sites.common import text_error
from fanic.settings import get_settings


def _redirect(response: ResponseLike, location: str) -> ResponseLike:
    response.status_code = 303
    response.content_type = "text/plain; charset=utf-8"
    response.headers["Location"] = location
    response.set_data(f"See Other: {location}")
    return response


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    if request.path != "/account/auth0/login":
        return text_error(response, "Not found", 404)
    if not enforce_https_termination(request, response):
        return response

    settings = get_settings()
    if not settings.auth0_configured:
        return _redirect(response, "/account/login?msg=auth-disabled")

    config = auth0_config_from_settings(settings)
    code_verifier = new_code_verifier()
    client = cast(Any, build_oauth_client(config))

    next_url = request.args.get("next", "").strip()
    if not next_url.startswith("/") or next_url.startswith("//"):
        next_url = "/"

    extra: dict[str, object] = {
        "redirect_uri": config.callback_url,
        "code_verifier": code_verifier,
    }
    if config.audience:
        extra["audience"] = config.audience
    if config.connection:
        extra["connection"] = config.connection

    auth_url_result = client.create_authorization_url(
        config.authorization_endpoint,
        **extra,
    )
    authorization_url, state = cast(tuple[str, str], auth_url_result)
    set_auth0_oauth_cookie(
        response,
        state=state,
        code_verifier=code_verifier,
        next_url=next_url,
    )
    return _redirect(response, authorization_url)
