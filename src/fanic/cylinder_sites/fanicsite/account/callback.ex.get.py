from typing import Any
from typing import cast

from fanic.auth0_client import auth0_config_from_settings
from fanic.auth0_client import build_oauth_client
from fanic.cylinder_sites.common import RequestLike
from fanic.cylinder_sites.common import ResponseLike
from fanic.cylinder_sites.common import clear_auth0_oauth_cookie
from fanic.cylinder_sites.common import enforce_https_termination
from fanic.cylinder_sites.common import read_auth0_oauth_state
from fanic.cylinder_sites.common import set_login_cookie
from fanic.cylinder_sites.common import text_error
from fanic.repository import get_or_create_user_for_auth0_identity
from fanic.settings import get_settings


def _redirect(response: ResponseLike, location: str) -> ResponseLike:
    response.status_code = 303
    response.content_type = "text/plain; charset=utf-8"
    response.headers["Location"] = location
    response.set_data(f"See Other: {location}")
    return response


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    if request.path != "/account/callback":
        return text_error(response, "Not found", 404)
    if not enforce_https_termination(request, response):
        return response

    settings = get_settings()
    if not settings.auth0_configured:
        return _redirect(response, "/account/login?msg=auth-disabled")

    error = request.args.get("error", "").strip()
    if error:
        return _redirect(response, "/account/login?msg=auth-failed")

    oauth_state = read_auth0_oauth_state(request)
    if oauth_state is None:
        return _redirect(response, "/account/login?msg=callback-invalid")

    returned_state = request.args.get("state", "").strip()
    code = request.args.get("code", "").strip()
    if not returned_state or returned_state != oauth_state["state"] or not code:
        clear_auth0_oauth_cookie(response)
        return _redirect(response, "/account/login?msg=callback-invalid")

    config = auth0_config_from_settings(settings)
    client = cast(Any, build_oauth_client(config))

    try:
        token_obj = client.fetch_token(
            config.token_endpoint,
            code=code,
            redirect_uri=config.callback_url,
            code_verifier=oauth_state["code_verifier"],
        )
        token = cast(dict[str, object], token_obj)
        userinfo_response = client.get(config.userinfo_endpoint, token=token)
        userinfo = cast(dict[str, object], userinfo_response.json())
    except Exception:
        clear_auth0_oauth_cookie(response)
        return _redirect(response, "/account/login?msg=auth-failed")

    subject = str(userinfo.get("sub", "")).strip()
    email_obj = userinfo.get("email")
    user_name_obj = userinfo.get("name")
    nickname_obj = userinfo.get("nickname")
    name_obj = user_name_obj if user_name_obj else nickname_obj
    if not name_obj:
        name_obj = email_obj if email_obj else "user"
    email = str(email_obj).strip() if isinstance(email_obj, str) else None
    email_verified = bool(userinfo.get("email_verified", False))
    display_name = str(name_obj).strip()

    if not subject:
        clear_auth0_oauth_cookie(response)
        return _redirect(response, "/account/login?msg=auth-failed")

    username = get_or_create_user_for_auth0_identity(
        subject=subject,
        email=email,
        email_verified=email_verified,
        display_name=display_name,
    )

    clear_auth0_oauth_cookie(response)
    set_login_cookie(response, username)

    next_url = oauth_state.get("next_url", "/").strip()
    if not next_url.startswith("/") or next_url.startswith("//"):
        next_url = "/"
    return _redirect(response, next_url)
