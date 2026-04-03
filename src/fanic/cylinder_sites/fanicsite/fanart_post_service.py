from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from fanic.authorization import AuthorizationContext
from fanic.repository.users import UserRole
from fanic.repository.users import get_local_user
from fanic.repository.users import get_local_user_by_display_name


class ReaderCommentOutcome(StrEnum):
    LOGIN_REQUIRED = "login-required"
    NOT_FOUND = "not-found"
    COMMENT_EMPTY = "comment-empty"
    COMMENT_SAVED = "comment-saved"


@dataclass(frozen=True)
class ReaderCommentResult:
    outcome: ReaderCommentOutcome


class DeleteItemOutcome(StrEnum):
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not-found"
    DELETED = "deleted"


@dataclass(frozen=True)
class DeleteItemResult:
    outcome: DeleteItemOutcome


class CreateGalleryOutcome(StrEnum):
    FORBIDDEN = "forbidden"
    NAME_REQUIRED = "gallery-name-required"
    INVALID = "gallery-invalid"
    CREATED = "gallery-created"


@dataclass(frozen=True)
class CreateGalleryResult:
    outcome: CreateGalleryOutcome
    gallery_slug: str = ""


class UpdateGalleryOutcome(StrEnum):
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not-found"
    UPDATED = "gallery-updated"


@dataclass(frozen=True)
class UpdateGalleryResult:
    outcome: UpdateGalleryOutcome


class DeleteGalleryOutcome(StrEnum):
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not-found"
    DELETED = "gallery-deleted"


@dataclass(frozen=True)
class DeleteGalleryResult:
    outcome: DeleteGalleryOutcome


def resolve_owner_username(owner_key: str) -> str | None:
    normalized_owner_key = owner_key.strip()
    if not normalized_owner_key:
        return None

    local_user = get_local_user(normalized_owner_key)
    if local_user is not None:
        username = str(local_user.get("username", "")).strip()
        if username:
            return username

    local_user = get_local_user_by_display_name(normalized_owner_key)
    if local_user is not None:
        username = str(local_user.get("username", "")).strip()
        if username:
            return username

    return normalized_owner_key


def owner_profile_key(work_owner_username: str) -> str:
    local_user = get_local_user(work_owner_username)
    if local_user is None:
        return work_owner_username

    display_name = str(local_user.get("display_name", "")).strip()
    if display_name:
        return display_name
    return work_owner_username


def authorization_context_for_owner(
    current_username: str,
    current_role: UserRole,
    owner_username: str,
) -> AuthorizationContext:
    return AuthorizationContext.from_inputs(
        current_username=current_username,
        current_role=current_role,
        owner_username=owner_username,
    )


def run_reader_comment_use_case(
    *,
    owner_username: str,
    actor_username: str | None,
    fanart_item_id: str,
    comment_body: str,
    get_fanart_item: Callable[[str], dict[str, object] | None],
    add_fanart_comment: Callable[[str, str, str], object],
) -> ReaderCommentResult:
    if actor_username is None:
        return ReaderCommentResult(ReaderCommentOutcome.LOGIN_REQUIRED)

    normalized_item_id = fanart_item_id.strip()
    if not normalized_item_id:
        return ReaderCommentResult(ReaderCommentOutcome.NOT_FOUND)

    fanart_item = get_fanart_item(normalized_item_id)
    if fanart_item is None:
        return ReaderCommentResult(ReaderCommentOutcome.NOT_FOUND)
    uploader_username = str(fanart_item.get("uploader_username", "")).strip()
    if uploader_username != owner_username:
        return ReaderCommentResult(ReaderCommentOutcome.NOT_FOUND)

    normalized_body = comment_body.strip()
    if not normalized_body:
        return ReaderCommentResult(ReaderCommentOutcome.COMMENT_EMPTY)

    _ = add_fanart_comment(normalized_item_id, actor_username, normalized_body)
    return ReaderCommentResult(ReaderCommentOutcome.COMMENT_SAVED)


def run_delete_item_use_case(
    *,
    owner_username: str,
    current_username: str,
    current_role: UserRole,
    item_id: str,
    authorization_context_for_owner: Callable[[str, UserRole, str], AuthorizationContext],
    can_delete_item: Callable[[AuthorizationContext], bool],
    get_fanart_item: Callable[[str], dict[str, object] | None],
    delete_fanart_item: Callable[[str], bool],
) -> DeleteItemResult:
    delete_ctx = authorization_context_for_owner(
        current_username,
        current_role,
        owner_username,
    )
    if not can_delete_item(delete_ctx):
        return DeleteItemResult(DeleteItemOutcome.FORBIDDEN)

    normalized_item_id = item_id.strip()
    if not owner_username or not normalized_item_id:
        return DeleteItemResult(DeleteItemOutcome.NOT_FOUND)

    work = get_fanart_item(normalized_item_id)
    if work is None:
        return DeleteItemResult(DeleteItemOutcome.NOT_FOUND)
    work_owner = str(work.get("uploader_username", "")).strip()
    if work_owner != owner_username:
        return DeleteItemResult(DeleteItemOutcome.NOT_FOUND)

    _ = delete_fanart_item(normalized_item_id)
    return DeleteItemResult(DeleteItemOutcome.DELETED)


def run_create_gallery_use_case(
    *,
    owner_username: str,
    current_username: str,
    current_role: UserRole,
    gallery_name: str,
    gallery_description: str,
    authorization_context_for_owner: Callable[[str, UserRole, str], AuthorizationContext],
    can_create_gallery: Callable[[AuthorizationContext], bool],
    create_fanart_gallery: Callable[..., dict[str, object]],
) -> CreateGalleryResult:
    create_ctx = authorization_context_for_owner(
        current_username,
        current_role,
        owner_username,
    )
    if not can_create_gallery(create_ctx):
        return CreateGalleryResult(CreateGalleryOutcome.FORBIDDEN)

    normalized_name = gallery_name.strip()
    normalized_description = gallery_description.strip()
    if not normalized_name:
        return CreateGalleryResult(CreateGalleryOutcome.NAME_REQUIRED)

    try:
        gallery = create_fanart_gallery(
            uploader_username=owner_username,
            name=normalized_name,
            description=normalized_description,
        )
    except ValueError:
        return CreateGalleryResult(CreateGalleryOutcome.INVALID)

    gallery_slug = str(gallery.get("slug", "")).strip()
    return CreateGalleryResult(
        outcome=CreateGalleryOutcome.CREATED,
        gallery_slug=gallery_slug,
    )


def run_update_gallery_items_use_case(
    *,
    owner_username: str,
    current_username: str,
    current_role: UserRole,
    gallery_slug: str,
    selected_item_ids: list[str],
    authorization_context_for_owner: Callable[[str, UserRole, str], AuthorizationContext],
    can_update_gallery_items: Callable[[AuthorizationContext], bool],
    get_fanart_gallery_by_slug: Callable[[str, str], dict[str, object] | None],
    replace_fanart_gallery_items: Callable[..., object],
) -> UpdateGalleryResult:
    update_ctx = authorization_context_for_owner(
        current_username,
        current_role,
        owner_username,
    )
    if not can_update_gallery_items(update_ctx):
        return UpdateGalleryResult(UpdateGalleryOutcome.FORBIDDEN)

    normalized_slug = gallery_slug.strip()
    gallery = get_fanart_gallery_by_slug(owner_username, normalized_slug)
    if gallery is None:
        return UpdateGalleryResult(UpdateGalleryOutcome.NOT_FOUND)

    _ = replace_fanart_gallery_items(
        uploader_username=owner_username,
        gallery_id=str(gallery.get("id", "")),
        fanart_item_ids=selected_item_ids,
    )
    return UpdateGalleryResult(UpdateGalleryOutcome.UPDATED)


def run_delete_gallery_use_case(
    *,
    owner_username: str,
    current_username: str,
    current_role: UserRole,
    gallery_slug: str,
    authorization_context_for_owner: Callable[[str, UserRole, str], AuthorizationContext],
    can_delete_gallery: Callable[[AuthorizationContext], bool],
    get_fanart_gallery_by_slug: Callable[[str, str], dict[str, object] | None],
    delete_fanart_gallery: Callable[..., bool],
) -> DeleteGalleryResult:
    delete_ctx = authorization_context_for_owner(
        current_username,
        current_role,
        owner_username,
    )
    if not can_delete_gallery(delete_ctx):
        return DeleteGalleryResult(DeleteGalleryOutcome.FORBIDDEN)

    normalized_slug = gallery_slug.strip()
    gallery = get_fanart_gallery_by_slug(owner_username, normalized_slug)
    if gallery is None:
        return DeleteGalleryResult(DeleteGalleryOutcome.NOT_FOUND)

    deleted = delete_fanart_gallery(
        uploader_username=owner_username,
        gallery_id=str(gallery.get("id", "")),
    )
    if not deleted:
        return DeleteGalleryResult(DeleteGalleryOutcome.NOT_FOUND)

    return DeleteGalleryResult(DeleteGalleryOutcome.DELETED)
