import sqlite3

from fanic.cylinder_sites.common.protocols import RequestLike
from fanic.cylinder_sites.common.protocols import ResponseLike
from fanic.cylinder_sites.common.rate_limit import check_post_rate_limit
from fanic.cylinder_sites.common.responses import redirect_see_other as _redirect
from fanic.cylinder_sites.common.responses import text_error
from fanic.cylinder_sites.common.security import enforce_https_termination
from fanic.cylinder_sites.common.security import validate_csrf
from fanic.cylinder_sites.common.session import current_user
from fanic.cylinder_sites.fanicsite.user.profile_post_helpers import (
    parse_display_name_form,
)
from fanic.cylinder_sites.fanicsite.user.profile_post_helpers import (
    parse_preference_form,
)
from fanic.cylinder_sites.fanicsite.user.profile_post_helpers import parse_theme_enabled
from fanic.cylinder_sites.fanicsite.user.profile_post_helpers import (
    profile_action_from_form,
)
from fanic.cylinder_sites.fanicsite.user.profile_post_helpers import read_uploaded_theme
from fanic.repository.users import set_user_prefers_explicit
from fanic.repository.users import set_user_prefers_mature
from fanic.repository.users import set_user_theme_preference
from fanic.repository.users import update_user_profile_details


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    if request.path != "/user/profile":
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

    profile_action = profile_action_from_form(request.form)
    if profile_action == "display-name":
        display_name_form = parse_display_name_form(request.form)
        if display_name_form is None:
            return _redirect(response, "/user/profile?msg=display-name-invalid")
        try:
            updated = update_user_profile_details(
                username,
                display_name=display_name_form.display_name,
                is_over_18=display_name_form.is_over_18,  # nosemgrep
            )
        except sqlite3.IntegrityError:
            return _redirect(response, "/user/profile?msg=display-name-taken")
        except ValueError:
            return _redirect(response, "/user/profile?msg=display-name-invalid")

        if not updated:
            return _redirect(response, "/user/profile?msg=display-name-invalid")

        return _redirect(response, "/user/profile?msg=display-name-saved")

    if profile_action == "theme":
        custom_theme_enabled = parse_theme_enabled(request.form)
        upload_result = read_uploaded_theme(request.files.get("theme_toml"))
        if upload_result.error_code:
            return _redirect(response, f"/user/profile?msg={upload_result.error_code}")

        set_user_theme_preference(
            username,
            enabled=custom_theme_enabled,
            toml_text=upload_result.toml_text,
        )
        return _redirect(response, "/user/profile?msg=theme_saved")

    preference_form = parse_preference_form(request.form)
    set_user_prefers_mature(username, preference_form.view_mature)
    set_user_prefers_explicit(username, preference_form.view_explicit)
    return _redirect(response, "/user/profile?msg=saved")
