import json
import secrets
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import quote

from fanic.cylinder_sites.common.protocols import RequestLike
from fanic.cylinder_sites.common.protocols import ResponseLike
from fanic.cylinder_sites.common.rate_limit import check_post_rate_limit
from fanic.cylinder_sites.common.rate_limit import validate_field_lengths
from fanic.cylinder_sites.common.responses import redirect_see_other as _redirect
from fanic.cylinder_sites.common.responses import text_error
from fanic.cylinder_sites.common.security import MAX_PAGE_UPLOAD_BYTES
from fanic.cylinder_sites.common.security import enforce_https_termination
from fanic.cylinder_sites.common.security import validate_csrf
from fanic.cylinder_sites.common.security import validate_page_upload_policy
from fanic.cylinder_sites.common.security import validate_saved_upload_size
from fanic.cylinder_sites.common.session import current_user
from fanic.cylinder_sites.common.session import role_for_user
from fanic.cylinder_sites.editor_metadata import RATING_CHOICES
from fanic.cylinder_sites.user_roles import is_privileged_role
from fanic.fanart import ingest_fanart_image
from fanic.ingest import ModerationBlockedError
from fanic.ingest_progress import set_progress
from fanic.repository.users import get_local_user


def _has_selected_file(upload: object | None) -> bool:
    if upload is None:
        return False
    filename = getattr(upload, "filename", None)
    return isinstance(filename, str) and bool(filename.strip())


def _moderation_stats_text(moderation: dict[str, object]) -> str:
    payload = dict(moderation)
    return json.dumps(payload, ensure_ascii=True, sort_keys=True)


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    if request.path not in {"/fanart/upload", "/fanart/upload/"}:
        return text_error(response, "Not found", 404)

    if not enforce_https_termination(request, response):
        return response

    if not validate_csrf(request):
        return text_error(response, "Invalid CSRF token", 403)

    retry_after = check_post_rate_limit(request)
    if retry_after:
        response.headers["Retry-After"] = str(retry_after)
        return text_error(response, "Too many requests. Please try again later.", 429)

    upload_token = request.form.get("upload_token", "").strip()
    if not upload_token:
        upload_token = f"fanart-ingest-{secrets.token_hex(8)}"

    set_progress(
        upload_token,
        stage="queued",
        message="Upload received. Validating request...",
        current=0,
        total=4,
        done=False,
        ok=False,
    )

    username = current_user(request)
    if username is None:
        set_progress(
            upload_token,
            stage="failed",
            message="Login required before uploading fanart.",
            current=4,
            total=4,
            done=True,
            ok=False,
        )
        return _redirect(response, "/fanart/upload?msg=login-required")

    is_admin_user = is_privileged_role(role_for_user(username))

    terms_accepted = request.form.get("agree_terms", "").strip().lower() in {
        "on",
        "true",
        "1",
        "yes",
    }
    if not terms_accepted:
        set_progress(
            upload_token,
            stage="failed",
            message="You must agree to the terms before uploading.",
            current=4,
            total=4,
            done=True,
            ok=False,
        )
        return _redirect(response, "/fanart/upload?msg=terms")

    work_title = request.form.get("title", "").strip()
    work_summary = request.form.get("summary", "").strip()
    work_fandom = request.form.get("fandom", "").strip()
    work_tags = request.form.get("tags", "").strip()
    work_rating = request.form.get("rating", "Not Rated").strip()
    if work_rating not in RATING_CHOICES:
        work_rating = "Not Rated"

    redirect_query = (
        f"title={quote(work_title, safe='')}&"
        f"summary={quote(work_summary, safe='')}&"
        f"fandom={quote(work_fandom, safe='')}&"
        f"tags={quote(work_tags, safe='')}&"
        f"rating={quote(work_rating, safe='')}"
    )

    length_error = validate_field_lengths(
        {
            "title": work_title,
            "summary": work_summary,
            "fandom": work_fandom,
            "tags": work_tags,
        },
        short={"title"},
        long={"summary", "fandom", "tags"},
    )
    if length_error or not work_title or not work_summary:
        set_progress(
            upload_token,
            stage="failed",
            message="Please complete all required fields.",
            current=4,
            total=4,
            done=True,
            ok=False,
        )
        return _redirect(response, f"/fanart/upload?msg=invalid&{redirect_query}")

    raw_upload = request.files.get("fanart_image")
    upload = raw_upload if _has_selected_file(raw_upload) else None
    if upload is None:
        set_progress(
            upload_token,
            stage="failed",
            message="Choose an image file to upload.",
            current=4,
            total=4,
            done=True,
            ok=False,
        )
        return _redirect(response, f"/fanart/upload?msg=missing-file&{redirect_query}")

    policy_error = validate_page_upload_policy(upload)
    if policy_error:
        set_progress(
            upload_token,
            stage="failed",
            message="Upload rejected by file policy.",
            current=4,
            total=4,
            done=True,
            ok=False,
        )
        return _redirect(response, f"/fanart/upload?msg=policy&{redirect_query}")

    try:
        set_progress(
            upload_token,
            stage="upload_saved",
            message="Upload complete. Preparing image...",
            current=1,
            total=4,
            done=False,
            ok=False,
        )

        with TemporaryDirectory() as temp_dir:
            upload_path = Path(temp_dir) / Path(upload.filename if upload.filename else "upload").name
            upload.save(upload_path)

            size_error = validate_saved_upload_size(
                upload_path,
                MAX_PAGE_UPLOAD_BYTES,
                "Fanart upload",
            )
            if size_error:
                set_progress(
                    upload_token,
                    stage="failed",
                    message="Upload rejected by file size policy.",
                    current=4,
                    total=4,
                    done=True,
                    ok=False,
                )
                return _redirect(response, f"/fanart/upload?msg=policy&{redirect_query}")

            set_progress(
                upload_token,
                stage="moderation",
                message="Running moderation checks...",
                current=2,
                total=4,
                done=False,
                ok=False,
            )

            ingest_work_result = ingest_fanart_image(
                upload_path,
                uploader_username=username,
                title=work_title,
                summary=work_summary,
                fandom=work_fandom,
                tags=work_tags,
                rating=work_rating,
            )
    except ModerationBlockedError as exc:
        moderation_details = _moderation_stats_text(exc.moderation)
        blocked_message = (
            f"Upload blocked by moderation policy. stats={moderation_details}"
            if is_admin_user
            else "Upload blocked by moderation policy."
        )
        set_progress(
            upload_token,
            stage="failed",
            message=blocked_message,
            current=4,
            total=4,
            done=True,
            ok=False,
        )
        if is_admin_user:
            blocked_query = f"{redirect_query}&moderation_detail={quote(moderation_details, safe='')}"
            return _redirect(response, f"/fanart/upload?msg=blocked&{blocked_query}")
        return _redirect(response, f"/fanart/upload?msg=blocked&{redirect_query}")
    except (OSError, ValueError):
        set_progress(
            upload_token,
            stage="failed",
            message="Upload failed. Please try again.",
            current=4,
            total=4,
            done=True,
            ok=False,
        )
        return _redirect(response, f"/fanart/upload?msg=invalid&{redirect_query}")

    uploaded_msg = "uploaded-rating-elevated"
    if not bool(ingest_work_result.get("rating_auto_elevated", False)):
        uploaded_msg = "uploaded"
    progress_done_message = "Fanart uploaded successfully."
    rating_after = str(ingest_work_result.get("rating_after", "")).strip()
    if bool(ingest_work_result.get("rating_auto_elevated", False)) and rating_after == "Explicit":
        progress_done_message = (
            "Fanart uploaded successfully. Rating was auto-promoted to Explicit based on moderation."
        )
        if bool(ingest_work_result.get("manual_review_queued", False)):
            progress_done_message = (
                f"{progress_done_message} This upload was also added to the admin moderation review queue."
            )
    local_user = get_local_user(username)
    profile_key = username
    if local_user is not None:
        display_name = str(local_user.get("display_name", "")).strip()
        if display_name:
            profile_key = display_name

    redirect_target = f"/fanart/{quote(profile_key, safe='')}?msg={uploaded_msg}"
    set_progress(
        upload_token,
        stage="done",
        message=progress_done_message,
        current=4,
        total=4,
        done=True,
        ok=True,
        redirect_to=redirect_target,
    )

    return _redirect(
        response,
        redirect_target,
    )
