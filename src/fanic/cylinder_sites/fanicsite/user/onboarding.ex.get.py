from html import escape

from fanic.cylinder_sites.common import RequestLike
from fanic.cylinder_sites.common import ResponseLike
from fanic.cylinder_sites.common import current_user
from fanic.cylinder_sites.common import enforce_https_termination
from fanic.cylinder_sites.common import render_html_template
from fanic.cylinder_sites.common import text_error
from fanic.repository import get_local_user
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

    username = current_user(request)
    if not username:
        return text_error(response, "Forbidden", 403)

    if not user_requires_onboarding(username):
        return _redirect(response, "/user/profile")

    save_msg = request.args.get("msg", "").strip()
    onboarding_status_text = ""
    onboarding_status_class = ""
    onboarding_status_hidden = "hidden"
    if save_msg == "onboarding-required":
        onboarding_status_text = "Please finish onboarding before using the rest of the site."
        onboarding_status_class = "error"
        onboarding_status_hidden = ""
    elif save_msg == "onboarding-invalid":
        onboarding_status_text = "Display name must use only letters and numbers, and age selection is required."
        onboarding_status_class = "error"
        onboarding_status_hidden = ""
    elif save_msg == "onboarding-name-taken":
        onboarding_status_text = "That display name is already in use."
        onboarding_status_class = "error"
        onboarding_status_hidden = ""

    local_user = get_local_user(username)
    display_name = username
    is_over_18: bool | None = None
    if local_user is not None:
        display_name = local_user["display_name"]
        is_over_18 = local_user["is_over_18"]

    over_18_yes_selected = "selected" if is_over_18 is True else ""
    over_18_no_selected = "selected" if is_over_18 is False else ""

    return render_html_template(
        request,
        response,
        "onboarding.html",
        {
            "__ONBOARDING_PAGE_TITLE__": "FANIC Onboarding",
            "__ONBOARDING_DISPLAY_NAME_VALUE__": escape(display_name),
            "__ONBOARDING_IS_OVER_18_YES_SELECTED_ATTR__": over_18_yes_selected,
            "__ONBOARDING_IS_OVER_18_NO_SELECTED_ATTR__": over_18_no_selected,
            "__ONBOARDING_STATUS__": onboarding_status_text,
            "__ONBOARDING_STATUS_CLASS__": onboarding_status_class,
            "__ONBOARDING_STATUS_HIDDEN_ATTR__": onboarding_status_hidden,
        },
    )
