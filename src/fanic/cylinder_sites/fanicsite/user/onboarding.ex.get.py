from html import escape

from fanic.cylinder_sites.common.protocols import RequestLike
from fanic.cylinder_sites.common.protocols import ResponseLike
from fanic.cylinder_sites.common.responses import redirect_see_other as _redirect
from fanic.cylinder_sites.common.responses import render_html_template
from fanic.cylinder_sites.common.responses import text_error
from fanic.cylinder_sites.common.security import enforce_https_termination
from fanic.cylinder_sites.common.session import current_user
from fanic.cylinder_sites.fanicsite.user.onboarding_helpers import (
    onboarding_display_state,
)
from fanic.cylinder_sites.fanicsite.user.profile_get_helpers import onboarding_status
from fanic.repository.users import get_local_user
from fanic.repository.users import user_requires_onboarding


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
    status = onboarding_status(save_msg, requires_onboarding=True)

    local_user = get_local_user(username)
    display = onboarding_display_state(username, local_user)

    return render_html_template(
        request,
        response,
        "onboarding.html",
        {
            "__ONBOARDING_PAGE_TITLE__": "FANIC Onboarding",
            "__ONBOARDING_DISPLAY_NAME_VALUE__": escape(display.display_name),
            "__ONBOARDING_IS_OVER_18_YES_SELECTED_ATTR__": display.over_18_yes_selected,
            "__ONBOARDING_IS_OVER_18_NO_SELECTED_ATTR__": display.over_18_no_selected,
            "__ONBOARDING_STATUS__": status.text,
            "__ONBOARDING_STATUS_CLASS__": status.css_class,
            "__ONBOARDING_STATUS_HIDDEN_ATTR__": status.hidden_attr,
        },
    )
