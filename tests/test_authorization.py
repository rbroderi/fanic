from fanic.authorization import AdminPathPolicy
from fanic.authorization import AdminReportsPolicy
from fanic.authorization import AdminUsersPolicy
from fanic.authorization import AuthorizationAction
from fanic.authorization import AuthorizationContext
from fanic.authorization import ComicPolicy
from fanic.authorization import FanartPolicy
from fanic.repository import UserRole


def _is_allowed(
    *,
    action: AuthorizationAction,
    current_username: str,
    current_role: UserRole,
    owner_username: str = "",
    target_username: str = "",
    target_role: str = "",
    requested_role: str = "",
) -> bool:
    ctx = AuthorizationContext.from_inputs(
        current_username=current_username,
        current_role=current_role,
        owner_username=owner_username,
        target_username=target_username,
        target_role=target_role,
        requested_role=requested_role,
    )
    if not ctx.current_username:
        return False

    if action == AuthorizationAction.FANART_DELETE_ITEM:
        return FanartPolicy.can_delete_item(ctx)
    if action == AuthorizationAction.FANART_GALLERY_CREATE:
        return FanartPolicy.can_create_gallery(ctx)
    if action == AuthorizationAction.FANART_GALLERY_UPDATE_ITEMS:
        return FanartPolicy.can_update_gallery_items(ctx)
    if action == AuthorizationAction.FANART_GALLERY_DELETE:
        return FanartPolicy.can_delete_gallery(ctx)
    if action == AuthorizationAction.COMIC_DELETE:
        return ComicPolicy.can_delete(ctx)
    if action == AuthorizationAction.COMIC_EDIT:
        return ComicPolicy.can_edit(ctx)
    if action == AuthorizationAction.ADMIN_REPORTS_MANAGE:
        return AdminReportsPolicy.can_manage(ctx)
    if action == AuthorizationAction.ADMIN_USERS_CREATE:
        return AdminUsersPolicy.can_create(ctx)
    if action == AuthorizationAction.ADMIN_USERS_SET_ROLE:
        return AdminUsersPolicy.can_set_role(ctx)
    if action == AuthorizationAction.ADMIN_USERS_SET_ACTIVE:
        return AdminUsersPolicy.can_set_active(ctx)
    if action == AuthorizationAction.ADMIN_USERS_REMOVE:
        return AdminUsersPolicy.can_remove(ctx)
    if action == AuthorizationAction.ADMIN_PATH_ACCESS:
        return AdminPathPolicy.can_access(ctx)


def test_fanart_delete_item_requires_admin_role() -> None:
    assert (
        _is_allowed(
            action=AuthorizationAction.FANART_DELETE_ITEM,
            current_username="alice",
            current_role="user",
            owner_username="alice",
        )
        is False
    )
    assert (
        _is_allowed(
            action=AuthorizationAction.FANART_DELETE_ITEM,
            current_username="admin-user",
            current_role="admin",
            owner_username="alice",
        )
        is True
    )


def test_fanart_gallery_create_requires_owner() -> None:
    assert (
        _is_allowed(
            action=AuthorizationAction.FANART_GALLERY_CREATE,
            current_username="alice",
            current_role="user",
            owner_username="alice",
        )
        is True
    )
    assert (
        _is_allowed(
            action=AuthorizationAction.FANART_GALLERY_CREATE,
            current_username="admin-user",
            current_role="admin",
            owner_username="alice",
        )
        is False
    )


def test_fanart_gallery_delete_allows_owner_or_admin() -> None:
    assert (
        _is_allowed(
            action=AuthorizationAction.FANART_GALLERY_DELETE,
            current_username="alice",
            current_role="user",
            owner_username="alice",
        )
        is True
    )
    assert (
        _is_allowed(
            action=AuthorizationAction.FANART_GALLERY_DELETE,
            current_username="admin-user",
            current_role="admin",
            owner_username="alice",
        )
        is True
    )
    assert (
        _is_allowed(
            action=AuthorizationAction.FANART_GALLERY_DELETE,
            current_username="bob",
            current_role="user",
            owner_username="alice",
        )
        is False
    )


def test_comic_delete_requires_admin() -> None:
    assert (
        _is_allowed(
            action=AuthorizationAction.COMIC_DELETE,
            current_username="alice",
            current_role="user",
            owner_username="alice",
        )
        is False
    )
    assert (
        _is_allowed(
            action=AuthorizationAction.COMIC_DELETE,
            current_username="admin",
            current_role="admin",
            owner_username="alice",
        )
        is True
    )


def test_comic_edit_allows_owner_or_admin() -> None:
    assert (
        _is_allowed(
            action=AuthorizationAction.COMIC_EDIT,
            current_username="alice",
            current_role="user",
            owner_username="alice",
        )
        is True
    )
    assert (
        _is_allowed(
            action=AuthorizationAction.COMIC_EDIT,
            current_username="admin",
            current_role="admin",
            owner_username="alice",
        )
        is True
    )
    assert (
        _is_allowed(
            action=AuthorizationAction.COMIC_EDIT,
            current_username="bob",
            current_role="user",
            owner_username="alice",
        )
        is False
    )


def test_admin_reports_manage_requires_admin() -> None:
    assert (
        _is_allowed(
            action=AuthorizationAction.ADMIN_REPORTS_MANAGE,
            current_username="alice",
            current_role="user",
        )
        is False
    )
    assert (
        _is_allowed(
            action=AuthorizationAction.ADMIN_REPORTS_MANAGE,
            current_username="admin",
            current_role="admin",
        )
        is True
    )


def test_admin_users_create_blocks_non_superadmin_superadmin_creation() -> None:
    assert (
        _is_allowed(
            action=AuthorizationAction.ADMIN_USERS_CREATE,
            current_username="admin",
            current_role="admin",
            requested_role="superadmin",
        )
        is False
    )
    assert (
        _is_allowed(
            action=AuthorizationAction.ADMIN_USERS_CREATE,
            current_username="superadmin",
            current_role="superadmin",
            requested_role="superadmin",
        )
        is True
    )


def test_admin_users_set_role_checks_target_and_requested_superadmin() -> None:
    assert (
        _is_allowed(
            action=AuthorizationAction.ADMIN_USERS_SET_ROLE,
            current_username="admin",
            current_role="admin",
            target_username="alice",
            target_role="superadmin",
            requested_role="user",
        )
        is False
    )
    assert (
        _is_allowed(
            action=AuthorizationAction.ADMIN_USERS_SET_ROLE,
            current_username="admin",
            current_role="admin",
            target_username="alice",
            target_role="user",
            requested_role="superadmin",
        )
        is False
    )
    assert (
        _is_allowed(
            action=AuthorizationAction.ADMIN_USERS_SET_ROLE,
            current_username="superadmin",
            current_role="superadmin",
            target_username="alice",
            target_role="user",
            requested_role="admin",
        )
        is True
    )


def test_admin_users_set_active_blocks_self_and_superadmin_target() -> None:
    assert (
        _is_allowed(
            action=AuthorizationAction.ADMIN_USERS_SET_ACTIVE,
            current_username="alice",
            current_role="admin",
            target_username="alice",
            target_role="admin",
        )
        is False
    )
    assert (
        _is_allowed(
            action=AuthorizationAction.ADMIN_USERS_SET_ACTIVE,
            current_username="admin",
            current_role="admin",
            target_username="owner",
            target_role="superadmin",
        )
        is False
    )
    assert (
        _is_allowed(
            action=AuthorizationAction.ADMIN_USERS_SET_ACTIVE,
            current_username="superadmin",
            current_role="superadmin",
            target_username="owner",
            target_role="superadmin",
        )
        is True
    )


def test_admin_users_remove_blocks_self_and_superadmin_target() -> None:
    assert (
        _is_allowed(
            action=AuthorizationAction.ADMIN_USERS_REMOVE,
            current_username="alice",
            current_role="admin",
            target_username="alice",
            target_role="admin",
        )
        is False
    )
    assert (
        _is_allowed(
            action=AuthorizationAction.ADMIN_USERS_REMOVE,
            current_username="admin",
            current_role="admin",
            target_username="owner",
            target_role="superadmin",
        )
        is False
    )
    assert (
        _is_allowed(
            action=AuthorizationAction.ADMIN_USERS_REMOVE,
            current_username="superadmin",
            current_role="superadmin",
            target_username="owner",
            target_role="superadmin",
        )
        is True
    )


def test_admin_path_access_requires_admin_role() -> None:
    assert (
        _is_allowed(
            action=AuthorizationAction.ADMIN_PATH_ACCESS,
            current_username="alice",
            current_role="user",
        )
        is False
    )
    assert (
        _is_allowed(
            action=AuthorizationAction.ADMIN_PATH_ACCESS,
            current_username="admin",
            current_role="admin",
        )
        is True
    )
