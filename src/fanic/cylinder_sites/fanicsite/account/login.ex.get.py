from dataclasses import dataclass
from html import escape

from fanic.cylinder_sites.common import RequestLike
from fanic.cylinder_sites.common import ResponseLike
from fanic.cylinder_sites.common import current_user
from fanic.cylinder_sites.common import render_html_template
from fanic.cylinder_sites.common import text_error


@dataclass(frozen=True, slots=True)
class LoginMessage:
    text: str
    css_class: str


def _message_block(request: RequestLike) -> LoginMessage:
    msg = request.args.get("msg", "")
    retry_after = request.args.get("retry_after", "").strip()
    username = current_user(request)

    match msg:
        case "invalid":
            return LoginMessage(
                "Invalid username or password. Please try again.", "error"
            )
        case "success":
            user_text = username if username else "user"
            return LoginMessage(f"Success: logged in as {user_text}.", "success")
        case "logged_out":
            return LoginMessage("You have been logged out.", "info")
        case "csrf-invalid":
            return LoginMessage(
                "Invalid CSRF token. Please retry from the form page.", "error"
            )
        case "https-required":
            return LoginMessage(
                "Secure HTTPS connection is required for login.", "error"
            )
        case "locked":
            retry_value = retry_after if retry_after else "a few minutes"
            return LoginMessage(
                f"Too many failed login attempts. Try again in {retry_value} seconds.",
                "error",
            )
        case _:
            if username:
                return LoginMessage(f"Success: logged in as {username}.", "success")
            return LoginMessage("", "")


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    if request.path != "/account/login":
        return text_error(response, "Not found", 404)

    username = current_user(request)
    logged_in = username is not None
    login_message = _message_block(request)

    login_credentials_hidden_attr = "hidden" if logged_in else ""
    login_button_hidden_attr = "hidden" if logged_in else ""
    logout_hidden_attr = "" if logged_in else "hidden"
    login_message_hidden_attr = "" if login_message.text else "hidden"

    return render_html_template(
        request,
        response,
        "login.html",
        {
            "__LOGIN_CREDENTIALS_HIDDEN_ATTR__": login_credentials_hidden_attr,
            "__LOGIN_BUTTON_HIDDEN_ATTR__": login_button_hidden_attr,
            "__LOGOUT_HIDDEN_ATTR__": logout_hidden_attr,
            "__LOGIN_MESSAGE_HIDDEN_ATTR__": login_message_hidden_attr,
            "__LOGIN_MESSAGE_CLASS__": login_message.css_class,
            "__LOGIN_MESSAGE__": escape(login_message.text),
        },
    )

