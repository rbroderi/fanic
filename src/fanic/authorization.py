from dataclasses import dataclass
from enum import StrEnum
from typing import Self

from fanic.cylinder_sites.user_roles import is_privileged_role
from fanic.repository.users import UserRole


class AuthorizationAction(StrEnum):
    FANART_DELETE_ITEM = "fanart_delete_item"
    FANART_GALLERY_CREATE = "fanart_gallery_create"
    FANART_GALLERY_UPDATE_ITEMS = "fanart_gallery_update_items"
    FANART_GALLERY_DELETE = "fanart_gallery_delete"
    COMIC_DELETE = "comic_delete"
    COMIC_EDIT = "comic_edit"
    ADMIN_REPORTS_MANAGE = "admin_reports_manage"
    ADMIN_USERS_CREATE = "admin_users_create"
    ADMIN_USERS_SET_ROLE = "admin_users_set_role"
    ADMIN_USERS_SET_ACTIVE = "admin_users_set_active"
    ADMIN_USERS_REMOVE = "admin_users_remove"
    ADMIN_PATH_ACCESS = "admin_path_access"


def _is_admin(role: UserRole) -> bool:
    return is_privileged_role(role)


def _is_owner(current_username: str, owner_username: str) -> bool:
    return current_username == owner_username


@dataclass(frozen=True, slots=True)
class AuthorizationContext:
    current_username: str
    current_role: UserRole
    owner_username: str
    target_username: str
    target_role: str
    requested_role: str

    @classmethod
    def from_inputs(
        cls,
        *,
        current_username: str,
        current_role: UserRole,
        owner_username: str = "",
        target_username: str = "",
        target_role: str = "",
        requested_role: str = "",
    ) -> Self:
        return cls(
            current_username=current_username.strip(),
            current_role=current_role,
            owner_username=owner_username.strip(),
            target_username=target_username.strip(),
            target_role=target_role.strip(),
            requested_role=requested_role.strip(),
        )


class FanartPolicy:
    @staticmethod
    def can_delete_item(ctx: AuthorizationContext) -> bool:
        return _is_admin(ctx.current_role)

    @staticmethod
    def can_create_gallery(ctx: AuthorizationContext) -> bool:
        if not ctx.owner_username:
            return False
        return _is_owner(ctx.current_username, ctx.owner_username)

    @staticmethod
    def can_update_gallery_items(ctx: AuthorizationContext) -> bool:
        if not ctx.owner_username:
            return False
        return _is_owner(ctx.current_username, ctx.owner_username)

    @staticmethod
    def can_delete_gallery(ctx: AuthorizationContext) -> bool:
        if not ctx.owner_username:
            return False
        return _is_owner(ctx.current_username, ctx.owner_username) or _is_admin(ctx.current_role)


class ComicPolicy:
    @staticmethod
    def can_delete(ctx: AuthorizationContext) -> bool:
        return _is_admin(ctx.current_role)

    @staticmethod
    def can_edit(ctx: AuthorizationContext) -> bool:
        if not ctx.owner_username:
            return False
        return _is_owner(ctx.current_username, ctx.owner_username) or _is_admin(ctx.current_role)


class AdminReportsPolicy:
    @staticmethod
    def can_manage(ctx: AuthorizationContext) -> bool:
        return _is_admin(ctx.current_role)


class AdminUsersPolicy:
    @staticmethod
    def can_create(ctx: AuthorizationContext) -> bool:
        if not _is_admin(ctx.current_role):
            return False
        if ctx.requested_role == "superadmin" and ctx.current_role != "superadmin":
            return False
        return True

    @staticmethod
    def can_set_role(ctx: AuthorizationContext) -> bool:
        if not _is_admin(ctx.current_role):
            return False
        if ctx.requested_role == "superadmin" and ctx.current_role != "superadmin":
            return False
        if ctx.target_role == "superadmin" and ctx.current_role != "superadmin":
            return False
        return True

    @staticmethod
    def can_set_active(ctx: AuthorizationContext) -> bool:
        if not _is_admin(ctx.current_role):
            return False
        if ctx.target_username and ctx.target_username == ctx.current_username:
            return False
        if ctx.target_role == "superadmin" and ctx.current_role != "superadmin":
            return False
        return True

    @staticmethod
    def can_remove(ctx: AuthorizationContext) -> bool:
        if not _is_admin(ctx.current_role):
            return False
        if ctx.target_username and ctx.target_username == ctx.current_username:
            return False
        if ctx.target_role == "superadmin" and ctx.current_role != "superadmin":
            return False
        return True


class AdminPathPolicy:
    @staticmethod
    def can_access(ctx: AuthorizationContext) -> bool:
        return _is_admin(ctx.current_role)
