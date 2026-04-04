"""users repository domain implementation."""

import re
import sqlite3
import uuid
from typing import Literal
from typing import NotRequired
from typing import TypedDict

from fanic.db import get_connection
from fanic.settings import get_settings
from fanic.type_coercion import as_int

UserRole = Literal["superadmin", "admin", "user", "guest"]

MANAGED_USER_ROLES: set[UserRole] = {"superadmin", "admin", "user"}

DISPLAY_NAME_PATTERN = re.compile(r"^[A-Za-z0-9]+$")


class UserThemePreference(TypedDict):
    enabled: bool
    toml_text: str


class LocalUserRow(TypedDict):
    username: str
    display_name: str
    email: str | None
    is_over_18: bool | None
    age_gate_completed: bool
    role: UserRole
    active: bool
    created_at: str


class AuthIdentityRow(TypedDict):
    provider: str
    subject: str
    username: str
    email: str | None
    email_verified: bool
    created_at: str


class RecentReadingHistoryRow(TypedDict):
    work_id: str
    work_title: str
    page_index: int
    updated_at: str


class UserBookmarkRow(TypedDict):
    username: str
    work_id: str
    work_title: str
    author_username: str
    author_display_name: NotRequired[str]
    page_index: int
    message: str
    updated_at: str
    rating: str
    status: str


class NotificationRow(TypedDict):
    id: int
    username: str
    actor_username: str
    actor_display_name: NotRequired[str]
    work_id: str
    kind: str
    message: str
    href: str
    is_read: bool
    created_at: str


def _normalize_user_role(role: object) -> UserRole:
    normalized = str(role).strip().lower()
    if normalized == "superadmin":
        return "superadmin"
    if normalized == "admin":
        return "admin"
    if normalized == "user":
        return "user"
    return "guest"


def _validate_managed_role(role: UserRole) -> UserRole:
    normalized_role = _normalize_user_role(role)
    if normalized_role not in MANAGED_USER_ROLES:
        raise ValueError("Role must be one of: superadmin, admin, user")
    return normalized_role


def _validate_display_name(display_name: str) -> str:
    normalized_display_name = display_name.strip()
    if not normalized_display_name:
        raise ValueError("display_name must not be empty")
    if not DISPLAY_NAME_PATTERN.fullmatch(normalized_display_name):
        raise ValueError("display_name must contain only letters and numbers")
    return normalized_display_name


def _sanitize_display_name(display_name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", display_name.strip())


def _email_in_use_by_other_username(email: str, username: str) -> bool:
    normalized_email = email.strip().lower()
    normalized_username = username.strip()
    if not normalized_email or not normalized_username:
        return False

    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT 1
            FROM users
            WHERE lower(COALESCE(email, '')) = ?
              AND username <> ?
            LIMIT 1
            """,
            (normalized_email, normalized_username),
        ).fetchone()
    return row is not None


def _display_name_in_use_by_other_username(display_name: str, username: str) -> bool:
    normalized_display_name = display_name.strip().lower()
    normalized_username = username.strip()
    if not normalized_display_name or not normalized_username:
        return False

    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT 1
            FROM users
            WHERE lower(display_name) = ?
              AND username <> ?
            LIMIT 1
            """,
            (normalized_display_name, normalized_username),
        ).fetchone()
    return row is not None


def upsert_user(
    user_id: str,
    username: str,
    *,
    display_name: str,
    email: str | None,
    active: bool,
    role: UserRole,
    is_over_18: bool | None = None,
    age_gate_completed: bool = True,
) -> None:
    normalized_role = _validate_managed_role(role)
    normalized_username = username.strip()
    normalized_display_name = _validate_display_name(display_name)
    normalized_email = email.strip().lower() if isinstance(email, str) else ""
    stored_email = normalized_email if normalized_email else None
    if _display_name_in_use_by_other_username(
        normalized_display_name,
        normalized_username,
    ):
        raise sqlite3.IntegrityError("display_name already exists")
    if stored_email and _email_in_use_by_other_username(stored_email, normalized_username):
        raise sqlite3.IntegrityError("email already exists")

    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO users (id, username, display_name, email, is_over_18, age_gate_completed, active, role)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                username = excluded.username,
                display_name = excluded.display_name,
                email = excluded.email,
                is_over_18 = excluded.is_over_18,
                age_gate_completed = excluded.age_gate_completed,
                active = excluded.active,
                role = excluded.role
            """,
            (
                user_id,
                username,
                normalized_display_name,
                stored_email,
                None if is_over_18 is None else (1 if is_over_18 else 0),
                1 if age_gate_completed else 0,
                1 if active else 0,
                normalized_role,
            ),
        )


def _next_available_display_name(seed: str, username: str) -> str:
    base = _sanitize_display_name(seed)
    if not base:
        base = "User"
    candidate = base
    counter = 2
    while _display_name_in_use_by_other_username(candidate, username):
        candidate = f"{base}{counter}"
        counter += 1
    return candidate


def ensure_local_user(username: str, *, role: UserRole = "user") -> None:
    normalized_username = username.strip()
    if not normalized_username:
        return
    resolved_display_name = _next_available_display_name(
        normalized_username,
        normalized_username,
    )
    upsert_user(
        normalized_username,
        normalized_username,
        display_name=resolved_display_name,
        email=None,
        active=True,
        role=role,
    )


def create_user(
    username: str,
    *,
    display_name: str,
    email: str | None = None,
    is_over_18: bool | None = None,
    age_gate_completed: bool = True,
    role: UserRole = "user",
    active: bool = True,
) -> None:
    normalized_username = username.strip()
    if not normalized_username:
        raise ValueError("username must not be empty")

    normalized_display_name = _validate_display_name(display_name)

    normalized_role = _validate_managed_role(role)
    normalized_email = email.strip().lower() if isinstance(email, str) else ""
    stored_email = normalized_email if normalized_email else None
    if _display_name_in_use_by_other_username(normalized_display_name, normalized_username):
        raise sqlite3.IntegrityError("display_name already exists")
    if stored_email and _email_in_use_by_other_username(stored_email, normalized_username):
        raise sqlite3.IntegrityError("email already exists")

    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO users (id, username, display_name, email, is_over_18, age_gate_completed, active, role)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                normalized_username,
                normalized_username,
                normalized_display_name,
                stored_email,
                None if is_over_18 is None else (1 if is_over_18 else 0),
                1 if age_gate_completed else 0,
                1 if active else 0,
                normalized_role,
            ),
        )


def set_user_role(username: str, role: UserRole) -> bool:
    normalized_username = username.strip()
    if not normalized_username:
        raise ValueError("username must not be empty")

    normalized_role = _validate_managed_role(role)
    with get_connection() as connection:
        cursor = connection.execute(
            "UPDATE users SET role = ? WHERE username = ?",
            (normalized_role, normalized_username),
        )
    return cursor.rowcount > 0


def set_user_active(username: str, active: bool) -> bool:
    normalized_username = username.strip()
    if not normalized_username:
        raise ValueError("username must not be empty")

    with get_connection() as connection:
        cursor = connection.execute(
            "UPDATE users SET active = ? WHERE username = ?",
            (1 if active else 0, normalized_username),
        )
    return cursor.rowcount > 0


def get_user_role(username: str | None) -> UserRole:
    normalized_username = username.strip() if isinstance(username, str) else ""
    if not normalized_username:
        return "guest"

    with get_connection() as connection:
        row = connection.execute(
            "SELECT role, active FROM users WHERE username = ?",
            (normalized_username,),
        ).fetchone()

    if not row:
        return "guest"
    if not bool(int(row["active"])):
        return "guest"
    return _normalize_user_role(row["role"])


def get_local_user(username: str) -> LocalUserRow | None:
    normalized_username = username.strip()
    if not normalized_username:
        return None

    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT username, display_name, email, is_over_18, age_gate_completed, role, active, created_at
            FROM users
            WHERE username = ?
            """,
            (normalized_username,),
        ).fetchone()

    if not row:
        return None

    return {
        "username": str(row["username"]),
        "display_name": str(row["display_name"]),
        "email": str(row["email"]) if row["email"] is not None else None,
        "is_over_18": None if row["is_over_18"] is None else bool(int(row["is_over_18"])),
        "age_gate_completed": bool(int(row["age_gate_completed"])),
        "role": _normalize_user_role(row["role"]),
        "active": bool(int(row["active"])),
        "created_at": str(row["created_at"]),
    }


def get_local_user_by_display_name(display_name: str) -> LocalUserRow | None:
    normalized_display_name = display_name.strip().lower()
    if not normalized_display_name:
        return None

    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT username, display_name, email, is_over_18, age_gate_completed, role, active, created_at
            FROM users
            WHERE lower(display_name) = ?
            """,
            (normalized_display_name,),
        ).fetchone()

    if not row:
        return None

    return {
        "username": str(row["username"]),
        "display_name": str(row["display_name"]),
        "email": str(row["email"]) if row["email"] is not None else None,
        "is_over_18": None if row["is_over_18"] is None else bool(int(row["is_over_18"])),
        "age_gate_completed": bool(int(row["age_gate_completed"])),
        "role": _normalize_user_role(row["role"]),
        "active": bool(int(row["active"])),
        "created_at": str(row["created_at"]),
    }


def _local_user_by_email(email: str) -> LocalUserRow | None:
    normalized_email = email.strip().lower()
    if not normalized_email:
        return None
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT username, display_name, email, is_over_18, age_gate_completed, role, active, created_at
            FROM users
            WHERE lower(COALESCE(email, '')) = ?
            ORDER BY
                CASE role
                    WHEN 'superadmin' THEN 0
                    WHEN 'admin' THEN 1
                    WHEN 'user' THEN 2
                    ELSE 3
                END,
                username COLLATE NOCASE ASC
            LIMIT 1
            """,
            (normalized_email,),
        ).fetchone()
    if not row:
        return None
    return {
        "username": str(row["username"]),
        "display_name": str(row["display_name"]),
        "email": str(row["email"]) if row["email"] is not None else None,
        "is_over_18": None if row["is_over_18"] is None else bool(int(row["is_over_18"])),
        "age_gate_completed": bool(int(row["age_gate_completed"])),
        "role": _normalize_user_role(row["role"]),
        "active": bool(int(row["active"])),
        "created_at": str(row["created_at"]),
    }


def get_auth_identity(provider: str, subject: str) -> AuthIdentityRow | None:
    normalized_provider = provider.strip().lower()
    normalized_subject = subject.strip()
    if not normalized_provider or not normalized_subject:
        return None
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT provider, subject, username, email, email_verified, created_at
            FROM auth_identities
            WHERE provider = ? AND subject = ?
            """,
            (normalized_provider, normalized_subject),
        ).fetchone()
    if not row:
        return None
    return {
        "provider": str(row["provider"]),
        "subject": str(row["subject"]),
        "username": str(row["username"]),
        "email": str(row["email"]) if row["email"] is not None else None,
        "email_verified": bool(int(row["email_verified"])),
        "created_at": str(row["created_at"]),
    }


def get_auth0_email_verified_for_username(username: str) -> bool | None:
    normalized_username = username.strip()
    if not normalized_username:
        return None

    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT email_verified
            FROM auth_identities
            WHERE provider = 'auth0' AND username = ?
            ORDER BY updated_at DESC, created_at DESC
            LIMIT 1
            """,
            (normalized_username,),
        ).fetchone()

    if row is None:
        return None
    return bool(int(row["email_verified"]))


def upsert_auth_identity(
    *,
    provider: str,
    subject: str,
    username: str,
    email: str | None,
    email_verified: bool,
) -> None:
    normalized_provider = provider.strip().lower()
    normalized_subject = subject.strip()
    normalized_username = username.strip()
    normalized_email = email.strip().lower() if isinstance(email, str) else ""
    stored_email = normalized_email if normalized_email else None
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO auth_identities (provider, subject, username, email, email_verified)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(provider, subject) DO UPDATE SET
                username = excluded.username,
                email = excluded.email,
                email_verified = excluded.email_verified,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                normalized_provider,
                normalized_subject,
                normalized_username,
                stored_email,
                1 if email_verified else 0,
            ),
        )


def get_or_create_user_for_auth0_identity(
    *,
    subject: str,
    email: str | None,
    email_verified: bool,
    display_name: str,
) -> str:
    settings = get_settings()
    superadmin_email = settings.auth0_superadmin_email.strip().lower()
    normalized_email = email.strip().lower() if isinstance(email, str) else ""
    normalized_subject = subject.strip()
    if not normalized_subject:
        raise ValueError("subject must not be empty")

    existing_identity = get_auth_identity("auth0", normalized_subject)
    if existing_identity is not None:
        username = existing_identity["username"]
        existing_user = get_local_user(username)
        if existing_user is not None:
            desired_role: UserRole = (
                "superadmin" if normalized_email and normalized_email == superadmin_email else existing_user["role"]
            )
            onboarding_completed = bool(existing_user["age_gate_completed"]) and existing_user["is_over_18"] is not None
            if onboarding_completed:
                resolved_display_name = existing_user["display_name"]
            else:
                preferred_display_name = display_name.strip() if display_name.strip() else existing_user["display_name"]
                resolved_display_name = _next_available_display_name(
                    preferred_display_name,
                    username,
                )
            candidate_email = normalized_email if normalized_email else existing_user["email"]
            resolved_email = candidate_email
            if isinstance(candidate_email, str) and _email_in_use_by_other_username(candidate_email, username):
                resolved_email = existing_user["email"]
            upsert_user(
                username,
                username,
                display_name=resolved_display_name,
                email=resolved_email,
                active=True,
                role=desired_role,
                is_over_18=existing_user["is_over_18"],
                age_gate_completed=existing_user["age_gate_completed"],
            )
            upsert_auth_identity(
                provider="auth0",
                subject=normalized_subject,
                username=username,
                email=resolved_email,
                email_verified=email_verified,
            )
            return username

    local_user = _local_user_by_email(normalized_email) if normalized_email else None
    if local_user is not None:
        username = local_user["username"]
        desired_role = "superadmin" if normalized_email == superadmin_email else local_user["role"]
        onboarding_completed = bool(local_user["age_gate_completed"]) and local_user["is_over_18"] is not None
        if onboarding_completed:
            resolved_display_name = local_user["display_name"]
        else:
            preferred_display_name = display_name.strip() if display_name.strip() else local_user["display_name"]
            resolved_display_name = _next_available_display_name(
                preferred_display_name,
                username,
            )
        resolved_email = normalized_email if normalized_email else local_user["email"]
        upsert_user(
            username,
            username,
            display_name=resolved_display_name,
            email=resolved_email,
            active=True,
            role=desired_role,
            is_over_18=local_user["is_over_18"],
            age_gate_completed=local_user["age_gate_completed"],
        )
        upsert_auth_identity(
            provider="auth0",
            subject=normalized_subject,
            username=username,
            email=resolved_email,
            email_verified=email_verified,
        )
        return username

    username = str(uuid.uuid4())
    desired_role = "superadmin" if normalized_email == superadmin_email else "user"
    preferred_display_name = display_name.strip() if display_name.strip() else username
    final_display_name = _next_available_display_name(preferred_display_name, username)
    stored_email = normalized_email if normalized_email else None
    create_user(
        username,
        display_name=final_display_name,
        email=stored_email,
        is_over_18=None,
        age_gate_completed=False,
        role=desired_role,
        active=True,
    )
    upsert_auth_identity(
        provider="auth0",
        subject=normalized_subject,
        username=username,
        email=stored_email,
        email_verified=email_verified,
    )
    return username


def count_local_users() -> int:
    with get_connection() as connection:
        row = connection.execute("SELECT COUNT(*) FROM users").fetchone()
        return int(row[0]) if row else 0


def list_local_users(*, offset: int = 0, limit: int = 0) -> list[LocalUserRow]:
    sql = """
        SELECT username, display_name, email, is_over_18, age_gate_completed, role, active, created_at
        FROM users
        ORDER BY
            CASE role
                WHEN 'superadmin' THEN 0
                WHEN 'admin' THEN 1
                WHEN 'user' THEN 2
                ELSE 3
            END,
            username COLLATE NOCASE ASC
    """
    params: list[int] = []
    if limit > 0:
        sql += " LIMIT ? OFFSET ?"
        params.extend([limit, offset])

    with get_connection() as connection:
        rows = connection.execute(sql, params).fetchall()

    return [
        {
            "username": str(row["username"]),
            "display_name": str(row["display_name"]),
            "email": str(row["email"]) if row["email"] is not None else None,
            "is_over_18": None if row["is_over_18"] is None else bool(int(row["is_over_18"])),
            "age_gate_completed": bool(int(row["age_gate_completed"])),
            "role": _normalize_user_role(row["role"]),
            "active": bool(int(row["active"])),
            "created_at": str(row["created_at"]),
        }
        for row in rows
    ]


def update_user_onboarding(
    username: str,
    *,
    display_name: str,
    is_over_18: bool,
) -> bool:
    normalized_username = username.strip()
    if not normalized_username:
        raise ValueError("username must not be empty")

    normalized_display_name = _validate_display_name(display_name)

    if _display_name_in_use_by_other_username(normalized_display_name, normalized_username):
        raise sqlite3.IntegrityError("display_name already exists")

    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE users
            SET display_name = ?,
                is_over_18 = ?,
                age_gate_completed = 1
            WHERE username = ?
                            AND (age_gate_completed = 0 OR is_over_18 IS NULL)
            """,
            (
                normalized_display_name,
                1 if is_over_18 else 0,
                normalized_username,
            ),
        )
    return cursor.rowcount > 0


def update_user_display_name(username: str, *, display_name: str) -> bool:
    normalized_username = username.strip()
    if not normalized_username:
        raise ValueError("username must not be empty")

    normalized_display_name = _validate_display_name(display_name)

    if _display_name_in_use_by_other_username(normalized_display_name, normalized_username):
        raise sqlite3.IntegrityError("display_name already exists")

    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE users
            SET display_name = ?
            WHERE username = ?
            """,
            (normalized_display_name, normalized_username),
        )
    return cursor.rowcount > 0


def update_user_profile_details(
    username: str,
    *,
    display_name: str,
    is_over_18: bool,
) -> bool:
    normalized_username = username.strip()
    if not normalized_username:
        raise ValueError("username must not be empty")

    normalized_display_name = _validate_display_name(display_name)

    if _display_name_in_use_by_other_username(normalized_display_name, normalized_username):
        raise sqlite3.IntegrityError("display_name already exists")

    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE users
            SET display_name = ?,
                is_over_18 = ?,
                age_gate_completed = 1
            WHERE username = ?
            """,
            (
                normalized_display_name,
                1 if is_over_18 else 0,
                normalized_username,
            ),
        )
    return cursor.rowcount > 0


def user_requires_onboarding(username: str) -> bool:
    normalized_username = username.strip()
    if not normalized_username:
        return False

    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT age_gate_completed, is_over_18
            FROM users
            WHERE username = ?
            """,
            (normalized_username,),
        ).fetchone()

    if row is None:
        return False
    if not bool(int(row["age_gate_completed"])):
        return True
    return row["is_over_18"] is None


def user_is_under_18(username: str) -> bool:
    normalized_username = username.strip()
    if not normalized_username:
        return False

    with get_connection() as connection:
        row = connection.execute(
            "SELECT is_over_18 FROM users WHERE username = ?",
            (normalized_username,),
        ).fetchone()

    if row is None:
        return False
    is_over_18_raw = row["is_over_18"]
    if is_over_18_raw is None:
        return False
    return not bool(int(is_over_18_raw))


def delete_user(username: str) -> bool:
    normalized_username = username.strip()
    if not normalized_username:
        raise ValueError("username must not be empty")

    with get_connection() as connection:
        connection.execute(
            "DELETE FROM user_preferences WHERE username = ?",
            (normalized_username,),
        )
        cursor = connection.execute(
            "DELETE FROM users WHERE username = ?",
            (normalized_username,),
        )
    return cursor.rowcount > 0


def user_prefers_mature(username: str | None) -> bool:
    if not username:
        return False

    with get_connection() as connection:
        row = connection.execute(
            "SELECT view_mature_rated FROM user_preferences WHERE username = ?",
            (username,),
        ).fetchone()
        if not row:
            return False
        return bool(int(row["view_mature_rated"]))


def user_prefers_explicit(username: str | None) -> bool:
    if not username:
        return False

    with get_connection() as connection:
        row = connection.execute(
            "SELECT view_explicit_rated FROM user_preferences WHERE username = ?",
            (username,),
        ).fetchone()
        if not row:
            return False
        return bool(int(row["view_explicit_rated"]))


def set_user_prefers_explicit(username: str, enabled: bool) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO user_preferences (username, view_mature_rated, view_explicit_rated, custom_theme_enabled, custom_theme_toml)
            VALUES (?, 0, ?, 0, NULL)
            ON CONFLICT(username) DO UPDATE SET
                view_explicit_rated = excluded.view_explicit_rated,
                updated_at = CURRENT_TIMESTAMP
            """,
            (username, 1 if enabled else 0),
        )


def set_user_prefers_mature(username: str, enabled: bool) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO user_preferences (username, view_mature_rated, view_explicit_rated, custom_theme_enabled, custom_theme_toml)
            VALUES (?, ?, 0, 0, NULL)
            ON CONFLICT(username) DO UPDATE SET
                view_mature_rated = excluded.view_mature_rated,
                updated_at = CURRENT_TIMESTAMP
            """,
            (username, 1 if enabled else 0),
        )


def get_user_theme_preference(username: str | None) -> UserThemePreference:
    if not username:
        return {"enabled": False, "toml_text": ""}

    with get_connection() as connection:
        row = connection.execute(
            "SELECT custom_theme_enabled, custom_theme_toml FROM user_preferences WHERE username = ?",
            (username,),
        ).fetchone()

    if not row:
        return {"enabled": False, "toml_text": ""}

    return {
        "enabled": bool(int(row["custom_theme_enabled"])),
        "toml_text": str(row["custom_theme_toml"] if row["custom_theme_toml"] else ""),
    }


def set_user_theme_preference(
    username: str,
    *,
    enabled: bool,
    toml_text: str | None,
) -> None:
    existing = get_user_theme_preference(username)
    resolved_toml_text = toml_text if toml_text is not None else existing["toml_text"]

    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO user_preferences (username, view_mature_rated, view_explicit_rated, custom_theme_enabled, custom_theme_toml)
            VALUES (?, 0, 0, ?, ?)
            ON CONFLICT(username) DO UPDATE SET
                custom_theme_enabled = excluded.custom_theme_enabled,
                custom_theme_toml = excluded.custom_theme_toml,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                username,
                1 if enabled else 0,
                resolved_toml_text,
            ),
        )


def create_notification(
    username: str,
    *,
    actor_username: str,
    work_id: str | None,
    kind: str,
    message: str,
    href: str,
) -> int:
    normalized_username = username.strip()
    if not normalized_username:
        raise ValueError("username must not be empty")

    normalized_actor = actor_username.strip()
    if not normalized_actor:
        raise ValueError("actor_username must not be empty")

    normalized_kind = kind.strip()
    stored_kind = normalized_kind if normalized_kind else "generic"

    normalized_message = message.strip()
    if not normalized_message:
        raise ValueError("message must not be empty")

    normalized_href = href.strip()
    stored_work_id = work_id.strip() if isinstance(work_id, str) and work_id.strip() else None

    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO notifications (username, actor_username, work_id, kind, message, href)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                normalized_username,
                normalized_actor,
                stored_work_id,
                stored_kind,
                normalized_message,
                normalized_href,
            ),
        )
    if cursor.lastrowid is None:
        raise RuntimeError("Failed to persist notification")
    return int(cursor.lastrowid)


def list_user_notifications(
    username: str,
    *,
    limit: int = 100,
) -> list[NotificationRow]:
    normalized_username = username.strip()
    if not normalized_username:
        return []

    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                n.id,
                n.username,
                n.actor_username,
                COALESCE(NULLIF(u.display_name, ''), n.actor_username) AS actor_display_name,
                n.work_id,
                n.kind,
                n.message,
                n.href,
                n.is_read,
                n.created_at
            FROM notifications n
            LEFT JOIN users u ON lower(u.username) = lower(n.actor_username)
            WHERE n.username = ?
            ORDER BY n.created_at DESC, n.id DESC
            LIMIT ?
            """,
            (normalized_username, int(limit)),
        ).fetchall()

    notifications: list[NotificationRow] = []
    for row in rows:
        work_id_obj = row["work_id"]
        notifications.append(
            {
                "id": int(row["id"]),
                "username": str(row["username"]),
                "actor_username": str(row["actor_username"]),
                "actor_display_name": str(row["actor_display_name"]),
                "work_id": str(work_id_obj) if work_id_obj is not None else "",
                "kind": str(row["kind"]),
                "message": str(row["message"]),
                "href": str(row["href"]),
                "is_read": bool(int(row["is_read"])),
                "created_at": str(row["created_at"]),
            }
        )
    return notifications


def count_unread_notifications(username: str | None) -> int:
    normalized_username = username.strip() if isinstance(username, str) else ""
    if not normalized_username:
        return 0

    with get_connection() as connection:
        row = connection.execute(
            "SELECT COUNT(*) AS count FROM notifications WHERE username = ? AND is_read = 0",
            (normalized_username,),
        ).fetchone()
    if not row:
        return 0
    return int(row["count"])


def mark_notification_read(username: str, notification_id: int) -> bool:
    normalized_username = username.strip()
    if not normalized_username:
        return False

    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE notifications
            SET is_read = 1
            WHERE id = ? AND username = ?
            """,
            (int(notification_id), normalized_username),
        )
    return cursor.rowcount > 0


def mark_all_notifications_read(username: str) -> int:
    normalized_username = username.strip()
    if not normalized_username:
        return 0

    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE notifications
            SET is_read = 1
            WHERE username = ? AND is_read = 0
            """,
            (normalized_username,),
        )
    return int(cursor.rowcount)


def delete_notification(username: str, notification_id: int) -> bool:
    normalized_username = username.strip()
    if not normalized_username:
        return False

    with get_connection() as connection:
        cursor = connection.execute(
            "DELETE FROM notifications WHERE id = ? AND username = ?",
            (int(notification_id), normalized_username),
        )
    return cursor.rowcount > 0


def list_recent_reading_history(
    user_id: str,
    *,
    limit: int,
) -> list[RecentReadingHistoryRow]:
    normalized_user_id = user_id.strip()
    if not normalized_user_id:
        return []

    normalized_limit = int(limit)
    if normalized_limit < 1:
        return []

    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT rp.work_id, w.title, rp.page_index, rp.updated_at
            FROM reading_progress rp
            JOIN works w ON w.id = rp.work_id
            WHERE rp.user_id = ?
            ORDER BY rp.updated_at DESC
            LIMIT ?
            """,
            (normalized_user_id, normalized_limit),
        ).fetchall()

    history_rows: list[RecentReadingHistoryRow] = []
    for row in rows:
        history_rows.append(
            {
                "work_id": str(row["work_id"]),
                "work_title": str(row["title"]),
                "page_index": as_int(row["page_index"], 1),
                "updated_at": str(row["updated_at"]),
            }
        )
    return history_rows


def upsert_user_bookmark(
    username: str,
    work_id: str,
    *,
    page_index: int,
    message: str,
) -> bool:
    normalized_username = username.strip()
    normalized_work_id = work_id.strip()
    if not normalized_username or not normalized_work_id:
        return False

    stored_page_index = max(1, int(page_index))
    stored_message = message.strip()

    with get_connection() as connection:
        work_row = connection.execute(
            "SELECT 1 FROM works WHERE id = ?",
            (normalized_work_id,),
        ).fetchone()
        if work_row is None:
            return False

        connection.execute(
            """
            INSERT INTO user_bookmarks (username, work_id, page_index, message)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(username, work_id) DO UPDATE SET
                page_index = excluded.page_index,
                message = excluded.message,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                normalized_username,
                normalized_work_id,
                stored_page_index,
                stored_message,
            ),
        )
    return True


def list_user_bookmarks(
    username: str,
    *,
    limit: int = 250,
) -> list[UserBookmarkRow]:
    normalized_username = username.strip()
    if not normalized_username:
        return []

    normalized_limit = int(limit)
    if normalized_limit < 1:
        return []

    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                ub.username,
                ub.work_id,
                w.title,
                COALESCE(w.uploader_username, '') AS author_username,
                COALESCE(NULLIF(au.display_name, ''), COALESCE(w.uploader_username, '')) AS author_display_name,
                ub.page_index,
                ub.message,
                ub.updated_at,
                w.rating,
                w.status
            FROM user_bookmarks ub
            JOIN works w ON w.id = ub.work_id
            LEFT JOIN users au ON lower(au.username) = lower(w.uploader_username)
            WHERE ub.username = ?
            ORDER BY ub.updated_at DESC
            LIMIT ?
            """,
            (normalized_username, normalized_limit),
        ).fetchall()

    bookmark_rows: list[UserBookmarkRow] = []
    for row in rows:
        bookmark_rows.append(
            {
                "username": str(row["username"]),
                "work_id": str(row["work_id"]),
                "work_title": str(row["title"]),
                "author_username": str(row["author_username"]),
                "author_display_name": str(row["author_display_name"]),
                "page_index": as_int(row["page_index"], 1),
                "message": str(row["message"]),
                "updated_at": str(row["updated_at"]),
                "rating": str(row["rating"]),
                "status": str(row["status"]),
            }
        )
    return bookmark_rows
