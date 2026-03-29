import sqlite3

from fanic.cylinder_sites.common import RequestLike
from fanic.cylinder_sites.common import ResponseLike
from fanic.cylinder_sites.common import check_post_rate_limit
from fanic.cylinder_sites.common import current_user
from fanic.cylinder_sites.common import enforce_https_termination
from fanic.cylinder_sites.common import text_error
from fanic.cylinder_sites.common import validate_csrf
from fanic.repository import update_user_onboarding
from fanic.repository import user_requires_onboarding


def _redirect(response: ResponseLike, location: str) -> ResponseLike:
    response.status_code = 303
    response.content_type = "text/plain; charset=utf-8"
    response.headers["Location"] = location
    response.set_data(f"See Other: {location}")
    return response


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

    display_name = request.form.get("display_name", "").strip()
    is_over_18_raw = request.form.get("is_over_18", "").strip().lower()
    if is_over_18_raw not in {"yes", "no"}:
        return _redirect(response, "/user/onboarding?msg=onboarding-invalid")

    try:
        saved = update_user_onboarding(
            username,
            display_name=display_name,
            is_over_18=is_over_18_raw == "yes",
        )
    except sqlite3.IntegrityError:
        return _redirect(response, "/user/onboarding?msg=onboarding-name-taken")
    except ValueError:
        return _redirect(response, "/user/onboarding?msg=onboarding-invalid")

    if not saved:
        return _redirect(response, "/user/profile")

    return _redirect(response, "/user/profile")
