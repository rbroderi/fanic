from __future__ import annotations

from html import escape

from fanic.cylinder_sites.common import (
    RequestLike,
    ResponseLike,
    current_user,
    render_html_template,
    text_error,
)
from fanic.repository import user_prefers_explicit


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    if request.path != "/profile":
        return text_error(response, "Not found", 404)

    username = current_user(request)
    save_msg = request.args.get("msg", "").strip()
    pref_status_text = "Preference saved." if save_msg == "saved" else ""
    pref_status_class = "success" if save_msg == "saved" else ""
    pref_status_hidden = "" if save_msg == "saved" else "hidden"

    if username is None:
        replacements = {
            "__PROFILE_STATUS__": "Not logged in.",
            "__PROFILE_STATUS_CLASS__": "error",
            "__PROFILE_DETAILS__": 'Use <a href="/login">Login</a> to sign in.',
            "__PROFILE_PREFS_HIDDEN_ATTR__": "hidden",
            "__PROFILE_VIEW_EXPLICIT_CHECKED_ATTR__": "",
            "__PROFILE_PREF_STATUS__": pref_status_text,
            "__PROFILE_PREF_STATUS_CLASS__": pref_status_class,
            "__PROFILE_PREF_STATUS_HIDDEN_ATTR__": pref_status_hidden,
        }
    else:
        view_explicit_checked = "checked" if user_prefers_explicit(username) else ""
        replacements = {
            "__PROFILE_STATUS__": "Logged in.",
            "__PROFILE_STATUS_CLASS__": "",
            "__PROFILE_DETAILS__": f"Username: {escape(username)}",
            "__PROFILE_PREFS_HIDDEN_ATTR__": "",
            "__PROFILE_VIEW_EXPLICIT_CHECKED_ATTR__": view_explicit_checked,
            "__PROFILE_PREF_STATUS__": pref_status_text,
            "__PROFILE_PREF_STATUS_CLASS__": pref_status_class,
            "__PROFILE_PREF_STATUS_HIDDEN_ATTR__": pref_status_hidden,
        }

    return render_html_template(request, response, "profile.html", replacements)
