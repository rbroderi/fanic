from html import escape

from fanic.cylinder_sites.common.protocols import RequestLike
from fanic.cylinder_sites.common.protocols import ResponseLike
from fanic.cylinder_sites.common.responses import redirect_see_other as _redirect
from fanic.cylinder_sites.common.session import current_user
from fanic.cylinder_sites.common.security import enforce_https_termination
from fanic.cylinder_sites.common.responses import render_html_template
from fanic.cylinder_sites.common.responses import text_error
from fanic.repository.users import get_auth0_email_verified_for_username
from fanic.repository.users import get_local_user
from fanic.repository.users import user_requires_onboarding


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    if request.path != "/account/verify-email":
        return text_error(response, "Not found", 404)

    if not enforce_https_termination(request, response):
        return response

    username = current_user(request)
    if not username:
        return text_error(response, "Forbidden", 403)

    email_verified = get_auth0_email_verified_for_username(username)
    if email_verified:
        if user_requires_onboarding(username):
            return _redirect(response, "/user/onboarding?msg=onboarding-required")
        return _redirect(response, "/user/profile")

    local_user = get_local_user(username)
    email_text = ""
    if local_user is not None and local_user["email"]:
        email_text = str(local_user["email"])

    msg = request.args.get("msg", "").strip()
    status_text = "Please verify your email address before continuing."
    status_class = "error"
    if msg == "still-unverified":
        status_text = (
            "Still waiting for verification. Please check your email inbox and spam folder, then click refresh."
        )
    elif msg == "verify-required":
        status_text = "Please verify your email address before continuing."

    return render_html_template(
        request,
        response,
        "verify_email.html",
        {
            "__VERIFY_EMAIL_PAGE_TITLE__": "Verify Email",
            "__VERIFY_EMAIL_STATUS__": escape(status_text),
            "__VERIFY_EMAIL_STATUS_CLASS__": status_class,
            "__VERIFY_EMAIL_EMAIL_HINT_HIDDEN_ATTR__": "" if email_text else "hidden",
            "__VERIFY_EMAIL_EMAIL_HINT__": escape(email_text),
        },
    )
