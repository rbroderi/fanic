import sqlite3
from typing import cast

from fanic.cylinder_sites.common import RequestLike
from fanic.cylinder_sites.common import ResponseLike
from fanic.cylinder_sites.common import current_user
from fanic.cylinder_sites.common import enforce_https_termination
from fanic.cylinder_sites.common import role_for_user
from fanic.cylinder_sites.common import text_error
from fanic.cylinder_sites.common import validate_csrf
from fanic.cylinder_sites.user_roles import ManagedUserRole
from fanic.cylinder_sites.user_roles import is_privileged_role
from fanic.repository import UserRole
from fanic.repository import create_user
from fanic.repository import delete_user
from fanic.repository import get_local_user
from fanic.repository import set_user_active
from fanic.repository import set_user_role


def _redirect(response: ResponseLike, location: str) -> ResponseLike:
    response.status_code = 303
    response.content_type = "text/plain; charset=utf-8"
    response.headers["Location"] = location
    response.set_data(f"See Other: {location}")
    return response


def _redirect_msg(response: ResponseLike, msg: str) -> ResponseLike:
    return _redirect(response, f"/admin/users?msg={msg}")


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    if request.path != "/admin/users":
        return text_error(response, "Not found", 404)

    if not enforce_https_termination(request, response):
        return response

    if not validate_csrf(request):
        return text_error(response, "Invalid CSRF token", 403)

    actor_username = current_user(request)
    actor_role = role_for_user(actor_username)
    if not is_privileged_role(actor_role):
        return text_error(response, "Forbidden", 403)

    action = request.form.get("user_action", "").strip()

    if action == "create":
        username = request.form.get("username", "").strip()
        display_name = request.form.get("display_name", "").strip()
        email_raw = request.form.get("email", "").strip()
        role = request.form.get("role", ManagedUserRole.USER.value).strip()
        active_raw = request.form.get("active", "0").strip()
        managed_role = ManagedUserRole.from_value(role)
        if managed_role is None:
            return _redirect_msg(response, "invalid")
        role_value = cast(UserRole, managed_role.value)

        if role_value == ManagedUserRole.SUPERADMIN.value and actor_role != ManagedUserRole.SUPERADMIN.value:
            return _redirect_msg(response, "forbidden-action")

        resolved_display_name = display_name if display_name else username
        email = email_raw if email_raw else None
        active = False if active_raw == "0" else True

        try:
            create_user(
                username,
                display_name=resolved_display_name,
                email=email,
                role=role_value,
                active=active,
            )
        except sqlite3.IntegrityError:
            return _redirect_msg(response, "exists")
        except ValueError:
            return _redirect_msg(response, "invalid")

        return _redirect_msg(response, "created")

    target_username = request.form.get("target_username", "").strip()
    if not target_username:
        return _redirect_msg(response, "invalid")

    target_user = get_local_user(target_username)
    if target_user is None:
        return _redirect_msg(response, "not-found")

    if target_user["role"] == ManagedUserRole.SUPERADMIN.value and actor_role != ManagedUserRole.SUPERADMIN.value:
        return _redirect_msg(response, "forbidden-action")

    if actor_username is not None and target_username == actor_username and action in {"set-active", "remove"}:
        return _redirect_msg(response, "self-action-blocked")

    if action == "set-role":
        role = request.form.get("role", "").strip()
        managed_role = ManagedUserRole.from_value(role)
        if managed_role is None:
            return _redirect_msg(response, "invalid")
        role_value = cast(UserRole, managed_role.value)
        if role_value == ManagedUserRole.SUPERADMIN.value and actor_role != ManagedUserRole.SUPERADMIN.value:
            return _redirect_msg(response, "forbidden-action")
        try:
            updated = set_user_role(target_username, role_value)
        except ValueError:
            return _redirect_msg(response, "invalid")
        return _redirect_msg(response, "updated" if updated else "not-found")

    if action == "set-active":
        active_raw = request.form.get("active", "").strip()
        if active_raw not in {"0", "1"}:
            return _redirect_msg(response, "invalid")
        updated = set_user_active(target_username, active_raw == "1")
        return _redirect_msg(response, "updated" if updated else "not-found")

    if action == "remove":
        try:
            deleted = delete_user(target_username)
        except ValueError:
            return _redirect_msg(response, "invalid")
        return _redirect_msg(response, "removed" if deleted else "not-found")

    return _redirect_msg(response, "invalid")
