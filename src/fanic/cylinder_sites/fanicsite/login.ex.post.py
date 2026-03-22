from __future__ import annotations

from fanic.cylinder_sites.common import RequestLike
from fanic.cylinder_sites.common import ResponseLike
from fanic.cylinder_sites.common import auth_lockout_seconds_remaining
from fanic.cylinder_sites.common import clear_auth_failures
from fanic.cylinder_sites.common import enforce_https_termination
from fanic.cylinder_sites.common import record_auth_failure
from fanic.cylinder_sites.common import role_for_user
from fanic.cylinder_sites.common import set_login_cookie
from fanic.cylinder_sites.common import text_error
from fanic.cylinder_sites.common import validate_csrf
from fanic.cylinder_sites.common import verify_admin_password


def _redirect(response: ResponseLike, location: str) -> ResponseLike:
    response.status_code = 303
    response.content_type = "text/plain; charset=utf-8"
    response.headers["Location"] = location
    response.set_data(f"See Other: {location}")
    return response


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    if request.path != "/login":
        return text_error(response, "Not found", 404)

    if not enforce_https_termination(request, response):
        return response

    if not validate_csrf(request):
        return _redirect(response, "/login?msg=csrf-invalid")

    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")

    lockout_remaining = auth_lockout_seconds_remaining(request, username)
    if lockout_remaining > 0:
        return _redirect(response, f"/login?msg=locked&retry_after={lockout_remaining}")

    role = role_for_user(username)
    allowed_role = role in {"superadmin", "admin"}
    password_ok = verify_admin_password(password)
    if not allowed_role or not password_ok:
        _ = record_auth_failure(request, username)
        return _redirect(response, "/login?msg=invalid")

    clear_auth_failures(request, username)
    set_login_cookie(response, username)
    return _redirect(response, "/login?msg=success")
