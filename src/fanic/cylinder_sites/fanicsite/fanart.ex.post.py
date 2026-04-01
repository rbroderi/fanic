from urllib.parse import quote

from fanic.authorization import AuthorizationContext
from fanic.authorization import FanartPolicy
from fanic.cylinder_sites.common import RequestLike
from fanic.cylinder_sites.common import ResponseLike
from fanic.cylinder_sites.common import current_user
from fanic.cylinder_sites.common import enforce_https_termination
from fanic.cylinder_sites.common import role_for_user
from fanic.cylinder_sites.common import route_tail
from fanic.cylinder_sites.common import text_error
from fanic.cylinder_sites.common import validate_csrf
from fanic.repository import create_fanart_gallery
from fanic.repository import delete_fanart_gallery
from fanic.repository import delete_fanart_item
from fanic.repository import get_fanart_gallery_by_slug
from fanic.repository import get_fanart_item
from fanic.repository import get_local_user
from fanic.repository import get_local_user_by_display_name
from fanic.repository import replace_fanart_gallery_items


def _redirect(response: ResponseLike, location: str) -> ResponseLike:
    response.status_code = 303
    response.content_type = "text/plain; charset=utf-8"
    response.headers["Location"] = location
    response.set_data(f"See Other: {location}")
    return response


def _form_values(request: RequestLike, key: str) -> list[str]:
    form_obj = request.form
    getlist = getattr(form_obj, "getlist", None)
    if callable(getlist):
        values = getlist(key)
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


def _resolve_owner_username(owner_key: str) -> str | None:
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


def _owner_profile_key(work_owner_username: str) -> str:
    local_user = get_local_user(work_owner_username)
    if local_user is None:
        return work_owner_username

    display_name = str(local_user.get("display_name", "")).strip()
    if display_name:
        return display_name
    return work_owner_username


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    tail = route_tail(request, ["fanart"])
    if tail is None:
        return text_error(response, "Not found", 404)

    if not enforce_https_termination(request, response):
        return response

    if not validate_csrf(request):
        return text_error(response, "Invalid CSRF token", 403)

    if len(tail) == 3 and tail[1] != "galleries" and tail[2] == "delete":
        username = current_user(request)
        user_role = role_for_user(username)
        work_owner_key = tail[0].strip()
        work_owner_username = _resolve_owner_username(work_owner_key)
        if not work_owner_username:
            return text_error(response, "Not found", 404)

        delete_ctx = AuthorizationContext.from_inputs(
            current_username=username,
            current_role=user_role,
            owner_username=work_owner_username,
        )
        if not FanartPolicy.can_delete_item(delete_ctx):
            return text_error(response, "Forbidden", 403)
        work_id = tail[1].strip()
        if not work_owner_username or not work_id:
            return text_error(response, "Not found", 404)

        work = get_fanart_item(work_id)
        if work is None:
            return text_error(response, "Not found", 404)
        work_owner = str(work.get("uploader_username", "")).strip()
        if work_owner != work_owner_username:
            return text_error(response, "Not found", 404)

        _ = delete_fanart_item(work_id)
        next_target = _safe_redirect_target(request.args.get("next", ""))
        if next_target:
            return _redirect(response, next_target)
        profile_key = _owner_profile_key(work_owner_username)
        return _redirect(
            response,
            f"/fanart/{quote(profile_key, safe='')}?msg=deleted",
        )

    if len(tail) == 3 and tail[1] == "galleries" and tail[2] == "create":
        work_owner_key = tail[0].strip()
        work_owner_username = _resolve_owner_username(work_owner_key)
        if not work_owner_username:
            return text_error(response, "Not found", 404)

        username = current_user(request)
        user_role = role_for_user(username)
        create_ctx = AuthorizationContext.from_inputs(
            current_username=username,
            current_role=user_role,
            owner_username=work_owner_username,
        )
        if not FanartPolicy.can_create_gallery(create_ctx):
            return text_error(response, "Forbidden", 403)

        gallery_name = request.form.get("gallery_name", "").strip()
        gallery_description = request.form.get("gallery_description", "").strip()
        profile_key = _owner_profile_key(work_owner_username)
        if not gallery_name:
            return _redirect(
                response,
                f"/fanart/{quote(profile_key, safe='')}?msg=gallery-name-required",
            )

        try:
            gallery = create_fanart_gallery(
                uploader_username=work_owner_username,
                name=gallery_name,
                description=gallery_description,
            )
        except ValueError:
            return _redirect(
                response,
                f"/fanart/{quote(profile_key, safe='')}?msg=gallery-invalid",
            )

        gallery_slug = str(gallery.get("slug", "")).strip()
        return _redirect(
            response,
            (f"/fanart/{quote(profile_key, safe='')}?gallery={quote(gallery_slug, safe='')}&msg=gallery-created"),
        )

    if len(tail) == 3 and tail[1] == "galleries" and tail[2] == "update-items":
        work_owner_key = tail[0].strip()
        work_owner_username = _resolve_owner_username(work_owner_key)
        if not work_owner_username:
            return text_error(response, "Not found", 404)

        username = current_user(request)
        user_role = role_for_user(username)
        update_ctx = AuthorizationContext.from_inputs(
            current_username=username,
            current_role=user_role,
            owner_username=work_owner_username,
        )
        if not FanartPolicy.can_update_gallery_items(update_ctx):
            return text_error(response, "Forbidden", 403)

        gallery_slug = request.form.get("gallery_slug", "").strip()
        gallery = get_fanart_gallery_by_slug(work_owner_username, gallery_slug)
        if gallery is None:
            return text_error(response, "Not found", 404)

        selected_item_ids = _form_values(request, "gallery_item_id")
        _ = replace_fanart_gallery_items(
            uploader_username=work_owner_username,
            gallery_id=str(gallery.get("id", "")),
            fanart_item_ids=selected_item_ids,
        )
        profile_key = _owner_profile_key(work_owner_username)
        return _redirect(
            response,
            (f"/fanart/{quote(profile_key, safe='')}?gallery={quote(gallery_slug, safe='')}&msg=gallery-updated"),
        )

    if len(tail) == 3 and tail[1] == "galleries" and tail[2] == "delete":
        work_owner_key = tail[0].strip()
        work_owner_username = _resolve_owner_username(work_owner_key)
        if not work_owner_username:
            return text_error(response, "Not found", 404)

        username = current_user(request)
        user_role = role_for_user(username)
        delete_gallery_ctx = AuthorizationContext.from_inputs(
            current_username=username,
            current_role=user_role,
            owner_username=work_owner_username,
        )
        if not FanartPolicy.can_delete_gallery(delete_gallery_ctx):
            return text_error(response, "Forbidden", 403)

        gallery_slug = request.form.get("gallery_slug", "").strip()
        gallery = get_fanart_gallery_by_slug(work_owner_username, gallery_slug)
        if gallery is None:
            return text_error(response, "Not found", 404)

        deleted = delete_fanart_gallery(
            uploader_username=work_owner_username,
            gallery_id=str(gallery.get("id", "")),
        )
        if not deleted:
            return text_error(response, "Not found", 404)

        profile_key = _owner_profile_key(work_owner_username)
        return _redirect(
            response,
            f"/fanart/{quote(profile_key, safe='')}?msg=gallery-deleted",
        )

    return text_error(response, "Not found", 404)
