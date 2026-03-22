from __future__ import annotations

from html import escape

from fanic.cylinder_sites.common import RequestLike
from fanic.cylinder_sites.common import ResponseLike
from fanic.cylinder_sites.common import current_user
from fanic.cylinder_sites.common import render_html_template
from fanic.cylinder_sites.common import text_error


def _message_block(request: RequestLike) -> tuple[str, str]:
    msg = request.args.get("msg", "")
    retry_after = request.args.get("retry_after", "").strip()
    username = current_user(request)

    if msg == "invalid":
        return ("Invalid username or password. Please try again.", "error")

    if msg == "success":
        user_text = username if username else "user"
        return (f"Success: logged in as {user_text}.", "success")

    if msg == "logged_out":
        return ("You have been logged out.", "info")

    if msg == "csrf-invalid":
        return ("Invalid CSRF token. Please retry from the form page.", "error")

    if msg == "https-required":
        return (
            "Secure HTTPS connection is required for login.",
            "error",
        )

    if msg == "locked":
        retry_value = retry_after if retry_after else "a few minutes"
        return (
            f"Too many failed login attempts. Try again in {retry_value} seconds.",
            "error",
        )

    if username:
        return (f"Success: logged in as {username}.", "success")

    return ("", "")


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    if request.path != "/login":
        return text_error(response, "Not found", 404)

    username = current_user(request)
    logged_in = username is not None
    login_message, login_message_class = _message_block(request)

    login_credentials_hidden_attr = "hidden" if logged_in else ""
    login_button_hidden_attr = "hidden" if logged_in else ""
    logout_hidden_attr = "" if logged_in else "hidden"
    login_message_hidden_attr = "" if login_message else "hidden"

    return render_html_template(
        request,
        response,
        "login.html",
        {
            "__LOGIN_CREDENTIALS_HIDDEN_ATTR__": login_credentials_hidden_attr,
            "__LOGIN_BUTTON_HIDDEN_ATTR__": login_button_hidden_attr,
            "__LOGOUT_HIDDEN_ATTR__": logout_hidden_attr,
            "__LOGIN_MESSAGE_HIDDEN_ATTR__": login_message_hidden_attr,
            "__LOGIN_MESSAGE_CLASS__": login_message_class,
            "__LOGIN_MESSAGE__": escape(login_message),
        },
    )
