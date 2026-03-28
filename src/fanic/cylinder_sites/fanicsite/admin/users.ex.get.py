from collections.abc import Sequence
from dataclasses import dataclass
from html import escape
from textwrap import dedent

from fanic.cylinder_sites.common import RequestLike
from fanic.cylinder_sites.common import ResponseLike
from fanic.cylinder_sites.common import current_user
from fanic.cylinder_sites.common import render_html_template
from fanic.cylinder_sites.common import role_for_user
from fanic.cylinder_sites.common import text_error
from fanic.cylinder_sites.user_roles import ManagedUserRole
from fanic.cylinder_sites.user_roles import is_privileged_role
from fanic.repository import LocalUserRow
from fanic.repository import count_local_users
from fanic.repository import list_local_users

USERS_PER_PAGE = 50


@dataclass(frozen=True, slots=True)
class StatusReplacements:
    text: str
    css_class: str
    hidden_attr: str


def _status_replacements(msg: str) -> StatusReplacements:
    match msg:
        case "created":
            return StatusReplacements("User created.", "success", "")
        case "updated":
            return StatusReplacements("User updated.", "success", "")
        case "removed":
            return StatusReplacements("User removed.", "success", "")
        case "invalid":
            return StatusReplacements("Invalid user action.", "error", "")
        case "not-found":
            return StatusReplacements("User not found.", "error", "")
        case "exists":
            return StatusReplacements("Username already exists.", "error", "")
        case "forbidden-action":
            return StatusReplacements(
                "You do not have permission for that action.",
                "error",
                "",
            )
        case "self-action-blocked":
            return StatusReplacements(
                "You cannot deactivate or remove your own account from this screen.",
                "error",
                "",
            )
        case _:
            return StatusReplacements("", "", "hidden")


def _role_options_html(selected_role: str) -> str:
    selected_role_enum = ManagedUserRole.from_value(selected_role)
    selected = selected_role_enum.value if selected_role_enum else ""
    options: list[str] = []
    for role in ManagedUserRole:
        selected_attr = " selected" if selected == role.value else ""
        options.append(f'<option value="{escape(role.value)}"{selected_attr}>{escape(role.label())}</option>')
    return "".join(options)


def _users_rows_html(users: Sequence[LocalUserRow], *, actor_username: str, actor_role: str) -> str:
    if not users:
        return '<p class="profile-meta">No users found.</p>'

    rows: list[str] = []
    for user in users:
        username = user["username"]
        display_name = user["display_name"]
        email = user["email"] if user["email"] is not None else ""
        role = user["role"]
        active = user["active"]

        safe_username = escape(username)
        safe_display_name = escape(display_name)
        safe_email = escape(email) if email else "-"
        safe_created_at = escape(user["created_at"])

        role_select_disabled = ""
        if role == ManagedUserRole.SUPERADMIN.value and actor_role != ManagedUserRole.SUPERADMIN.value:
            role_select_disabled = " disabled"

        deactivate_disabled = ""
        remove_disabled = ""
        if username == actor_username:
            deactivate_disabled = " disabled"
            remove_disabled = " disabled"
        if role == ManagedUserRole.SUPERADMIN.value and actor_role != ManagedUserRole.SUPERADMIN.value:
            deactivate_disabled = " disabled"
            remove_disabled = " disabled"

        state_text = "Active" if active else "Inactive"
        target_active = "0" if active else "1"
        toggle_label = "Deactivate" if active else "Reactivate"

        rows.append(
            dedent(
                f"""\
                <article class="card comment-card">
                <p><strong>{safe_display_name}</strong> <span class="profile-meta">({safe_username})</span></p>
                <p class="profile-meta">Email: {safe_email}</p>
                <p class="profile-meta">Created: {safe_created_at} | Status: {escape(state_text)} | Role: {escape(role)}</p>
                <form class="upload-form" method="post" action="/admin/users">
                <input type="hidden" name="target_username" value="{safe_username}" />
                <input type="hidden" name="user_action" value="set-role" />
                <label>Role</label>
                <select name="role"{role_select_disabled}>
                {_role_options_html(role)}
                </select>
                <button type="submit">Save role</button>
                </form>
                <form class="upload-form" method="post" action="/admin/users">
                <input type="hidden" name="target_username" value="{safe_username}" />
                <input type="hidden" name="user_action" value="set-active" />
                <input type="hidden" name="active" value="{escape(target_active)}" />
                <button type="submit" class="button-muted"{deactivate_disabled}>{escape(toggle_label)}</button>
                </form>
                <form class="upload-form" method="post" action="/admin/users">
                <input type="hidden" name="target_username" value="{safe_username}" />
                <input type="hidden" name="user_action" value="remove" />
                <button type="submit" class="button-danger" onclick="return confirm('Remove this user account?');"{remove_disabled}>Remove user</button>
                </form>
                </article>
                """
            ).strip()
        )

    return "".join(rows)


def _pagination_html(page: int, total_pages: int, msg: str) -> str:
    if total_pages <= 1:
        return ""
    parts: list[str] = ['<nav class="pagination">']
    if page > 1:
        prev_qs = f"?page={page - 1}&msg={escape(msg)}" if msg else f"?page={page - 1}"
        parts.append(f'<a href="/admin/users{prev_qs}">&laquo; Previous</a>')
    parts.append(f"<span>Page {page} of {total_pages}</span>")
    if page < total_pages:
        next_qs = f"?page={page + 1}&msg={escape(msg)}" if msg else f"?page={page + 1}"
        parts.append(f'<a href="/admin/users{next_qs}">Next &raquo;</a>')
    parts.append("</nav>")
    return " ".join(parts)


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    if request.path != "/admin/users":
        return text_error(response, "Not found", 404)

    actor_username = current_user(request)
    actor_role = role_for_user(actor_username)
    if not is_privileged_role(actor_role):
        return text_error(response, "Forbidden", 403)

    msg = request.args.get("msg", "").strip()
    status = _status_replacements(msg)
    actor_name = actor_username if actor_username else ""

    page_raw = request.args.get("page", "1").strip()
    try:
        page = max(1, int(page_raw))
    except ValueError:
        page = 1

    total_users = count_local_users()
    total_pages = max(1, (total_users + USERS_PER_PAGE - 1) // USERS_PER_PAGE)
    if page > total_pages:
        page = total_pages
    offset = (page - 1) * USERS_PER_PAGE

    replacements = {
        "__USERS_STATUS_TEXT__": escape(status.text),
        "__USERS_STATUS_CLASS__": escape(status.css_class),
        "__USERS_STATUS_HIDDEN_ATTR__": status.hidden_attr,
        "__USERS_ROLE_OPTIONS__": _role_options_html(ManagedUserRole.USER.value),
        "__USERS_ROWS_HTML__": _users_rows_html(
            list_local_users(offset=offset, limit=USERS_PER_PAGE),
            actor_username=actor_name,
            actor_role=actor_role,
        ),
        "__USERS_PAGINATION_HTML__": _pagination_html(page, total_pages, msg),
    }
    return render_html_template(request, response, "users-admin.html", replacements)
