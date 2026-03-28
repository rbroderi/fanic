from fanic.cylinder_sites.common import RequestLike
from fanic.cylinder_sites.common import ResponseLike
from fanic.cylinder_sites.common import auth_lockout_seconds_remaining
from fanic.cylinder_sites.common import clear_auth_failures
from fanic.cylinder_sites.common import clear_login_cookie
from fanic.cylinder_sites.common import enforce_https_termination
from fanic.cylinder_sites.common import json_response
from fanic.cylinder_sites.common import record_auth_failure
from fanic.cylinder_sites.common import role_for_user
from fanic.cylinder_sites.common import route_tail
from fanic.cylinder_sites.common import set_login_cookie
from fanic.cylinder_sites.common import verify_admin_password


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    tail = route_tail(request, ["api", "auth"])
    if tail is None or len(tail) != 1:
        return json_response(response, {"detail": "Not found"}, 404)

    action = tail[0]

    if action == "login":
        if not enforce_https_termination(request, response):
            return response

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        lockout_remaining = auth_lockout_seconds_remaining(request, username)
        if lockout_remaining > 0:
            return json_response(
                response,
                {"detail": "Too many attempts", "retry_after": lockout_remaining},
                429,
            )

        role = role_for_user(username)
        allowed_role = role in {"superadmin", "admin"}
        password_ok = verify_admin_password(password)
        if not allowed_role or not password_ok:
            _ = record_auth_failure(request, username)
            return json_response(response, {"detail": "Invalid credentials"}, 401)

        clear_auth_failures(request, username)
        set_login_cookie(response, username)
        return json_response(response, {"ok": True, "username": username})

    if action == "logout":
        clear_login_cookie(response)
        return json_response(response, {"ok": True})

    return json_response(response, {"detail": "Not found"}, 404)
