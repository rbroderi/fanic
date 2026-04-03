from dataclasses import dataclass
from typing import cast
from urllib.parse import quote

from fanic.authorization import FanartPolicy
from fanic.cylinder_sites.common.protocols import RequestLike
from fanic.cylinder_sites.common.protocols import ResponseLike
from fanic.cylinder_sites.common.responses import redirect_see_other as _redirect
from fanic.cylinder_sites.common.responses import text_error
from fanic.cylinder_sites.common.security import enforce_https_termination
from fanic.cylinder_sites.common.security import route_tail
from fanic.cylinder_sites.common.security import validate_csrf
from fanic.cylinder_sites.common.session import current_user
from fanic.cylinder_sites.common.session import role_for_user
from fanic.cylinder_sites.fanicsite.fanart_post_service import CreateGalleryOutcome
from fanic.cylinder_sites.fanicsite.fanart_post_service import DeleteGalleryOutcome
from fanic.cylinder_sites.fanicsite.fanart_post_service import DeleteItemOutcome
from fanic.cylinder_sites.fanicsite.fanart_post_service import ReaderCommentOutcome
from fanic.cylinder_sites.fanicsite.fanart_post_service import UpdateGalleryOutcome
from fanic.cylinder_sites.fanicsite.fanart_post_service import (
    authorization_context_for_owner,
)
from fanic.cylinder_sites.fanicsite.fanart_post_service import owner_profile_key
from fanic.cylinder_sites.fanicsite.fanart_post_service import resolve_owner_username
from fanic.cylinder_sites.fanicsite.fanart_post_service import (
    run_create_gallery_use_case,
)
from fanic.cylinder_sites.fanicsite.fanart_post_service import (
    run_delete_gallery_use_case,
)
from fanic.cylinder_sites.fanicsite.fanart_post_service import run_delete_item_use_case
from fanic.cylinder_sites.fanicsite.fanart_post_service import (
    run_reader_comment_use_case,
)
from fanic.cylinder_sites.fanicsite.fanart_post_service import (
    run_update_gallery_items_use_case,
)
from fanic.repository.fanart import add_fanart_comment
from fanic.repository.fanart import create_fanart_gallery
from fanic.repository.fanart import delete_fanart_gallery
from fanic.repository.fanart import delete_fanart_item
from fanic.repository.fanart import get_fanart_gallery_by_slug
from fanic.repository.fanart import get_fanart_item
from fanic.repository.fanart import replace_fanart_gallery_items
from fanic.repository.users import UserRole


@dataclass(frozen=True, slots=True)
class CurrentIdentity:
    username: str | None
    user_role: UserRole
    current_username: str


def _get_fanart_item_as_dict(item_id: str) -> dict[str, object] | None:
    item = get_fanart_item(item_id)
    if item is None:
        return None
    return cast(dict[str, object], cast(object, item))


def _get_fanart_gallery_by_slug_as_dict(
    uploader_username: str,
    gallery_slug: str,
) -> dict[str, object] | None:
    gallery = get_fanart_gallery_by_slug(uploader_username, gallery_slug)
    if gallery is None:
        return None
    return cast(dict[str, object], cast(object, gallery))


def _create_fanart_gallery_as_dict(
    *,
    uploader_username: str,
    name: str,
    description: str = "",
) -> dict[str, object]:
    gallery = create_fanart_gallery(
        uploader_username=uploader_username,
        name=name,
        description=description,
    )
    return cast(dict[str, object], cast(object, gallery))


def _form_values(request: RequestLike, key: str) -> list[str]:
    form_obj = request.form
    getlist = getattr(form_obj, "getlist", None)
    if callable(getlist):
        values_obj = getlist(key)
        if not isinstance(values_obj, list):
            return []
        values = cast(list[object], values_obj)
        return [str(value).strip() for value in values if str(value).strip()]

    raw = request.form.get(key, "").strip()
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def _safe_redirect_target(raw_target: str) -> str | None:
    target = raw_target.strip()
    if not target:
        return None
    if not target.startswith("/"):
        return None
    if target.startswith("//"):
        return None
    if "://" in target:
        return None
    return target


def _current_identity(request: RequestLike) -> CurrentIdentity:
    username = current_user(request)
    user_role = role_for_user(username)
    current_username = username if username else ""
    return CurrentIdentity(
        username=username,
        user_role=user_role,
        current_username=current_username,
    )


def _handle_reader_comments(
    request: RequestLike,
    response: ResponseLike,
    work_owner_key: str,
) -> ResponseLike:
    work_owner_username = resolve_owner_username(work_owner_key)
    if not work_owner_username:
        return text_error(response, "Not found", 404)

    identity = _current_identity(request)
    username = identity.username
    fanart_item_id = request.form.get("fanart_item_id", "").strip()
    comment_body = request.form.get("comment_body", "").strip()

    result = run_reader_comment_use_case(
        owner_username=work_owner_username,
        actor_username=username,
        fanart_item_id=fanart_item_id,
        comment_body=comment_body,
        get_fanart_item=_get_fanart_item_as_dict,
        add_fanart_comment=add_fanart_comment,
    )

    next_target = _safe_redirect_target(request.form.get("next", ""))
    if result.outcome == ReaderCommentOutcome.NOT_FOUND:
        return text_error(response, "Not found", 404)
    if result.outcome == ReaderCommentOutcome.LOGIN_REQUIRED:
        if next_target:
            separator = "&" if "?" in next_target else "?"
            return _redirect(response, f"{next_target}{separator}msg=login-required")
        profile_key = owner_profile_key(work_owner_username)
        return _redirect(
            response,
            f"/fanart/{quote(profile_key, safe='')}/reader?msg=login-required",
        )
    if result.outcome == ReaderCommentOutcome.COMMENT_EMPTY:
        if next_target:
            separator = "&" if "?" in next_target else "?"
            return _redirect(response, f"{next_target}{separator}msg=comment-empty")
        profile_key = owner_profile_key(work_owner_username)
        return _redirect(
            response,
            f"/fanart/{quote(profile_key, safe='')}/reader?item_id={quote(fanart_item_id, safe='')}&msg=comment-empty",
        )

    if next_target:
        separator = "&" if "?" in next_target else "?"
        return _redirect(response, f"{next_target}{separator}msg=comment-saved")
    profile_key = owner_profile_key(work_owner_username)
    return _redirect(
        response,
        f"/fanart/{quote(profile_key, safe='')}/reader?item_id={quote(fanart_item_id, safe='')}&msg=comment-saved",
    )


def _handle_item_delete(
    request: RequestLike,
    response: ResponseLike,
    work_owner_key: str,
    work_id: str,
) -> ResponseLike:
    identity = _current_identity(request)
    work_owner_username = resolve_owner_username(work_owner_key)
    if not work_owner_username:
        return text_error(response, "Not found", 404)

    result = run_delete_item_use_case(
        owner_username=work_owner_username,
        current_username=identity.current_username,
        current_role=identity.user_role,
        item_id=work_id,
        authorization_context_for_owner=authorization_context_for_owner,
        can_delete_item=FanartPolicy.can_delete_item,
        get_fanart_item=_get_fanart_item_as_dict,
        delete_fanart_item=delete_fanart_item,
    )

    if result.outcome == DeleteItemOutcome.FORBIDDEN:
        return text_error(response, "Forbidden", 403)
    if result.outcome == DeleteItemOutcome.NOT_FOUND:
        return text_error(response, "Not found", 404)

    next_target = _safe_redirect_target(request.args.get("next", ""))
    if next_target:
        return _redirect(response, next_target)
    profile_key = owner_profile_key(work_owner_username)
    return _redirect(
        response,
        f"/fanart/{quote(profile_key, safe='')}?msg=deleted",
    )


def _handle_gallery_create(
    request: RequestLike,
    response: ResponseLike,
    work_owner_key: str,
) -> ResponseLike:
    work_owner_username = resolve_owner_username(work_owner_key)
    if not work_owner_username:
        return text_error(response, "Not found", 404)

    identity = _current_identity(request)
    gallery_name = request.form.get("gallery_name", "").strip()
    gallery_description = request.form.get("gallery_description", "").strip()

    result = run_create_gallery_use_case(
        owner_username=work_owner_username,
        current_username=identity.current_username,
        current_role=identity.user_role,
        gallery_name=gallery_name,
        gallery_description=gallery_description,
        authorization_context_for_owner=authorization_context_for_owner,
        can_create_gallery=FanartPolicy.can_create_gallery,
        create_fanart_gallery=_create_fanart_gallery_as_dict,
    )

    if result.outcome == CreateGalleryOutcome.FORBIDDEN:
        return text_error(response, "Forbidden", 403)

    profile_key = owner_profile_key(work_owner_username)
    if result.outcome == CreateGalleryOutcome.NAME_REQUIRED:
        return _redirect(
            response,
            f"/fanart/{quote(profile_key, safe='')}?msg=gallery-name-required",
        )
    if result.outcome == CreateGalleryOutcome.INVALID:
        return _redirect(
            response,
            f"/fanart/{quote(profile_key, safe='')}?msg=gallery-invalid",
        )

    gallery_slug = result.gallery_slug
    return _redirect(
        response,
        (f"/fanart/{quote(profile_key, safe='')}?gallery={quote(gallery_slug, safe='')}&msg=gallery-created"),
    )


def _handle_gallery_update_items(
    request: RequestLike,
    response: ResponseLike,
    work_owner_key: str,
) -> ResponseLike:
    work_owner_username = resolve_owner_username(work_owner_key)
    if not work_owner_username:
        return text_error(response, "Not found", 404)

    identity = _current_identity(request)
    gallery_slug = request.form.get("gallery_slug", "").strip()
    selected_item_ids = _form_values(request, "gallery_item_id")

    result = run_update_gallery_items_use_case(
        owner_username=work_owner_username,
        current_username=identity.current_username,
        current_role=identity.user_role,
        gallery_slug=gallery_slug,
        selected_item_ids=selected_item_ids,
        authorization_context_for_owner=authorization_context_for_owner,
        can_update_gallery_items=FanartPolicy.can_update_gallery_items,
        get_fanart_gallery_by_slug=_get_fanart_gallery_by_slug_as_dict,
        replace_fanart_gallery_items=replace_fanart_gallery_items,
    )

    if result.outcome == UpdateGalleryOutcome.FORBIDDEN:
        return text_error(response, "Forbidden", 403)
    if result.outcome == UpdateGalleryOutcome.NOT_FOUND:
        return text_error(response, "Not found", 404)

    profile_key = owner_profile_key(work_owner_username)
    return _redirect(
        response,
        (f"/fanart/{quote(profile_key, safe='')}?gallery={quote(gallery_slug, safe='')}&msg=gallery-updated"),
    )


def _handle_gallery_delete(
    request: RequestLike,
    response: ResponseLike,
    work_owner_key: str,
) -> ResponseLike:
    work_owner_username = resolve_owner_username(work_owner_key)
    if not work_owner_username:
        return text_error(response, "Not found", 404)

    identity = _current_identity(request)
    gallery_slug = request.form.get("gallery_slug", "").strip()

    result = run_delete_gallery_use_case(
        owner_username=work_owner_username,
        current_username=identity.current_username,
        current_role=identity.user_role,
        gallery_slug=gallery_slug,
        authorization_context_for_owner=authorization_context_for_owner,
        can_delete_gallery=FanartPolicy.can_delete_gallery,
        get_fanart_gallery_by_slug=_get_fanart_gallery_by_slug_as_dict,
        delete_fanart_gallery=delete_fanart_gallery,
    )

    if result.outcome == DeleteGalleryOutcome.FORBIDDEN:
        return text_error(response, "Forbidden", 403)
    if result.outcome == DeleteGalleryOutcome.NOT_FOUND:
        return text_error(response, "Not found", 404)

    profile_key = owner_profile_key(work_owner_username)
    return _redirect(
        response,
        f"/fanart/{quote(profile_key, safe='')}?msg=gallery-deleted",
    )


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    tail = route_tail(request, ["fanart"])
    if tail is None:
        return text_error(response, "Not found", 404)

    if not enforce_https_termination(request, response):
        return response

    if not validate_csrf(request):
        return text_error(response, "Invalid CSRF token", 403)

    path_key = tail[1] if len(tail) > 1 else ""
    action = tail[2] if len(tail) > 2 else ""
    owner_key = tail[0].strip() if tail else ""

    match (len(tail), path_key, action):
        case (3, "reader", "comments"):
            return _handle_reader_comments(request, response, owner_key)
        case (3, _, "delete") if path_key != "galleries":
            work_id = path_key.strip()
            return _handle_item_delete(request, response, owner_key, work_id)
        case (3, "galleries", "create"):
            return _handle_gallery_create(request, response, owner_key)
        case (3, "galleries", "update-items"):
            return _handle_gallery_update_items(request, response, owner_key)
        case (3, "galleries", "delete"):
            return _handle_gallery_delete(request, response, owner_key)
        case _:
            return text_error(response, "Not found", 404)
