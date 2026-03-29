import sqlite3
import tomllib
from pathlib import Path
from tempfile import TemporaryDirectory

from fanic.cylinder_sites.common import RequestLike
from fanic.cylinder_sites.common import ResponseLike
from fanic.cylinder_sites.common import check_post_rate_limit
from fanic.cylinder_sites.common import current_user
from fanic.cylinder_sites.common import enforce_https_termination
from fanic.cylinder_sites.common import text_error
from fanic.cylinder_sites.common import validate_csrf
from fanic.repository import set_user_prefers_explicit
from fanic.repository import set_user_prefers_mature
from fanic.repository import set_user_theme_preference
from fanic.repository import update_user_profile_details


def _redirect(response: ResponseLike, location: str) -> ResponseLike:
    response.status_code = 303
    response.content_type = "text/plain; charset=utf-8"
    response.headers["Location"] = location
    response.set_data(f"See Other: {location}")
    return response


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

    profile_action = request.form.get("profile_action", "preferences").strip()
    if profile_action == "display-name":
        display_name = request.form.get("display_name", "").strip()
        is_over_18_raw = request.form.get("is_over_18", "").strip().lower()
        if is_over_18_raw not in {"yes", "no"}:
            return _redirect(response, "/user/profile?msg=display-name-invalid")
        try:
            updated = update_user_profile_details(
                username,
                display_name=display_name,
                is_over_18=is_over_18_raw == "yes",
            )
        except sqlite3.IntegrityError:
            return _redirect(response, "/user/profile?msg=display-name-taken")
        except ValueError:
            return _redirect(response, "/user/profile?msg=display-name-invalid")

        if not updated:
            return _redirect(response, "/user/profile?msg=display-name-invalid")

        return _redirect(response, "/user/profile?msg=display-name-saved")

    if profile_action == "theme":
        custom_theme_enabled = request.form.get("custom_theme_enabled", "") == "on"
        theme_upload = request.files.get("theme_toml")
        uploaded_toml_text: str | None = None

        if theme_upload is not None and theme_upload.filename:
            try:
                with TemporaryDirectory() as temp_dir:
                    upload_path = Path(temp_dir) / "theme.toml"
                    theme_upload.save(upload_path)
                    uploaded_toml_text = upload_path.read_text(encoding="utf-8")
                _ = tomllib.loads(uploaded_toml_text)
            except (OSError, UnicodeDecodeError):
                return _redirect(response, "/user/profile?msg=theme_upload_error")
            except tomllib.TOMLDecodeError:
                return _redirect(response, "/user/profile?msg=theme_parse_error")

        set_user_theme_preference(
            username,
            enabled=custom_theme_enabled,
            toml_text=uploaded_toml_text,
        )
        return _redirect(response, "/user/profile?msg=theme_saved")

    view_mature = request.form.get("view_mature_rated", "") == "on"
    view_explicit = request.form.get("view_explicit_rated", "") == "on"
    set_user_prefers_mature(username, view_mature)
    set_user_prefers_explicit(username, view_explicit)
    return _redirect(response, "/user/profile?msg=saved")
