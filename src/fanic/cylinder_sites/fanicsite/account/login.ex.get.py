from html import escape

from fanic.cylinder_sites.common.protocols import RequestLike
from fanic.cylinder_sites.common.protocols import ResponseLike
from fanic.cylinder_sites.common.protocols import StatusReplacements
from fanic.cylinder_sites.common.session import current_user
from fanic.cylinder_sites.common.responses import render_html_template
from fanic.cylinder_sites.common.protocols import status_for_message
from fanic.cylinder_sites.common.protocols import status_hidden
from fanic.cylinder_sites.common.protocols import status_visible
from fanic.cylinder_sites.common.responses import text_error


def _message_block(request: RequestLike) -> StatusReplacements:
    msg = request.args.get("msg", "")
    retry_after = request.args.get("retry_after", "").strip()
    username = current_user(request)

    if msg == "success":
        user_text = username if username else "user"
        return status_visible(f"Success: logged in as {user_text}.", "success")

    if msg == "locked":
        retry_value = retry_after if retry_after else "a few minutes"
        return status_visible(
            f"Too many failed login attempts. Try again in {retry_value} seconds.",
            "error",
        )

    mapped = status_for_message(
        msg,
        {
            "invalid": status_visible("Invalid username or password. Please try again.", "error"),
            "logged_out": status_visible("You have been logged out.", "info"),
            "csrf-invalid": status_visible("Invalid CSRF token. Please retry from the form page.", "error"),
            "https-required": status_visible("Secure HTTPS connection is required for login.", "error"),
            "auth-disabled": status_visible("Auth0 login is not enabled on this deployment.", "error"),
            "auth-email-unverified": status_visible(
                "Please verify your email address, then sign in again.",
                "error",
            ),
            "auth-failed": status_visible("Authentication failed. Please try again.", "error"),
            "auth-upstream-blocked": status_visible(
                "Authentication provider response was blocked or invalid. "
                "This is often caused by proxy or WAF challenges on the auth domain.",
                "error",
            ),
            "callback-invalid": status_visible("The login callback was invalid or expired. Please try again.", "error"),
        },
    )
    if mapped.hidden_attr == "":
        return mapped

    if username:
        return status_visible(f"Success: logged in as {username}.", "success")
    return status_hidden()


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    if request.path != "/account/login":
        return text_error(response, "Not found", 404)

    username = current_user(request)
    logged_in = username is not None
    login_message = _message_block(request)

    login_credentials_hidden_attr = "hidden" if logged_in else ""
    login_button_hidden_attr = "hidden" if logged_in else ""
    logout_hidden_attr = "" if logged_in else "hidden"
    return render_html_template(
        request,
        response,
        "login.html",
        {
            "__LOGIN_CREDENTIALS_HIDDEN_ATTR__": login_credentials_hidden_attr,
            "__LOGIN_BUTTON_HIDDEN_ATTR__": login_button_hidden_attr,
            "__LOGOUT_HIDDEN_ATTR__": logout_hidden_attr,
            "__LOGIN_MESSAGE_HIDDEN_ATTR__": login_message.hidden_attr,
            "__LOGIN_MESSAGE_CLASS__": login_message.css_class,
            "__LOGIN_MESSAGE__": escape(login_message.text),
        },
    )
