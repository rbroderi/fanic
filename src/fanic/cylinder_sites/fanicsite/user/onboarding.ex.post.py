import sqlite3

from fanic.cylinder_sites.common.protocols import RequestLike
from fanic.cylinder_sites.common.protocols import ResponseLike
from fanic.cylinder_sites.common.rate_limit import check_post_rate_limit
from fanic.cylinder_sites.common.responses import redirect_see_other as _redirect
from fanic.cylinder_sites.common.responses import text_error
from fanic.cylinder_sites.common.security import enforce_https_termination
from fanic.cylinder_sites.common.security import validate_csrf
from fanic.cylinder_sites.common.session import current_user
from fanic.cylinder_sites.fanicsite.user.onboarding_helpers import parse_onboarding_form
from fanic.repository.users import update_user_onboarding
from fanic.repository.users import user_requires_onboarding


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    if request.path != "/user/onboarding":
        return text_error(response, "Not found", 404)

    if not enforce_https_termination(request, response):
        return response

    if not validate_csrf(request):
        return text_error(response, "Invalid CSRF token", 403)

    retry_after = check_post_rate_limit(request)
    if retry_after:
        response.headers["Retry-After"] = str(retry_after)
        return text_error(response, "Too many requests. Please try again later.", 429)

    username = current_user(request)
    if not username:
        return text_error(response, "Forbidden", 403)

    if not user_requires_onboarding(username):
        return _redirect(response, "/user/profile")

    form_data = parse_onboarding_form(request.form)
    if form_data is None:
        return _redirect(response, "/user/onboarding?msg=onboarding-invalid")

    try:
        saved = update_user_onboarding(
            username,
            display_name=form_data.display_name,
            is_over_18=form_data.is_over_18,
        )
    except sqlite3.IntegrityError:
        return _redirect(response, "/user/onboarding?msg=onboarding-name-taken")
    except ValueError:
        return _redirect(response, "/user/onboarding?msg=onboarding-invalid")

    if not saved:
        return _redirect(response, "/user/profile")

    return _redirect(response, "/user/profile")
