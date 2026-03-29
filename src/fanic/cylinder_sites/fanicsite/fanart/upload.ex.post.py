from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import quote

from fanic.cylinder_sites.common import MAX_PAGE_UPLOAD_BYTES
from fanic.cylinder_sites.common import RequestLike
from fanic.cylinder_sites.common import ResponseLike
from fanic.cylinder_sites.common import check_post_rate_limit
from fanic.cylinder_sites.common import current_user
from fanic.cylinder_sites.common import enforce_https_termination
from fanic.cylinder_sites.common import text_error
from fanic.cylinder_sites.common import validate_csrf
from fanic.cylinder_sites.common import validate_field_lengths
from fanic.cylinder_sites.common import validate_page_upload_policy
from fanic.cylinder_sites.common import validate_saved_upload_size
from fanic.cylinder_sites.editor_metadata import RATING_CHOICES
from fanic.fanart import ingest_fanart_image
from fanic.ingest import ModerationBlockedError


def _redirect(response: ResponseLike, location: str) -> ResponseLike:
    response.status_code = 303
    response.content_type = "text/plain; charset=utf-8"
    response.headers["Location"] = location
    response.set_data(f"See Other: {location}")
    return response


def _has_selected_file(upload: object | None) -> bool:
    if upload is None:
        return False
    filename = getattr(upload, "filename", None)
    return isinstance(filename, str) and bool(filename.strip())


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    if request.path != "/fanart/upload":
        return text_error(response, "Not found", 404)

    if not enforce_https_termination(request, response):
        return response

    if not validate_csrf(request):
        return text_error(response, "Invalid CSRF token", 403)

    retry_after = check_post_rate_limit(request)
    if retry_after:
        response.headers["Retry-After"] = str(retry_after)
        return text_error(response, "Too many requests. Please try again later.", 429)

    username = current_user(request)
    if username is None:
        return _redirect(response, "/fanart/upload?msg=login-required")

    terms_accepted = request.form.get("agree_terms", "").strip().lower() in {
        "on",
        "true",
        "1",
        "yes",
    }
    if not terms_accepted:
        return _redirect(response, "/fanart/upload?msg=terms")

    work_title = request.form.get("title", "").strip()
    work_summary = request.form.get("summary", "").strip()
    work_fandom = request.form.get("fandom", "").strip()
    work_rating = request.form.get("rating", "Not Rated").strip()
    if work_rating not in RATING_CHOICES:
        work_rating = "Not Rated"

    redirect_query = (
        f"title={quote(work_title, safe='')}&"
        f"summary={quote(work_summary, safe='')}&"
        f"fandom={quote(work_fandom, safe='')}&"
        f"rating={quote(work_rating, safe='')}"
    )

    length_error = validate_field_lengths(
        {
            "title": work_title,
            "summary": work_summary,
            "fandom": work_fandom,
        },
        short={"title", "fandom"},
        long={"summary"},
    )
    if length_error or not work_title or not work_summary:
        return _redirect(response, f"/fanart/upload?msg=invalid&{redirect_query}")

    raw_upload = request.files.get("fanart_image")
    upload = raw_upload if _has_selected_file(raw_upload) else None
    if upload is None:
        return _redirect(response, f"/fanart/upload?msg=missing-file&{redirect_query}")

    policy_error = validate_page_upload_policy(upload)
    if policy_error:
        return _redirect(response, f"/fanart/upload?msg=policy&{redirect_query}")

    try:
        with TemporaryDirectory() as temp_dir:
            upload_path = Path(temp_dir) / Path(upload.filename if upload.filename else "upload").name
            upload.save(upload_path)

            size_error = validate_saved_upload_size(
                upload_path,
                MAX_PAGE_UPLOAD_BYTES,
                "Fanart upload",
            )
            if size_error:
                return _redirect(response, f"/fanart/upload?msg=policy&{redirect_query}")

            ingest_work_result = ingest_fanart_image(
                upload_path,
                uploader_username=username,
                title=work_title,
                summary=work_summary,
                fandom=work_fandom,
                rating=work_rating,
            )
    except ModerationBlockedError:
        return _redirect(response, f"/fanart/upload?msg=blocked&{redirect_query}")
    except (OSError, ValueError):
        return _redirect(response, f"/fanart/upload?msg=invalid&{redirect_query}")

    uploaded_msg = "uploaded-rating-elevated"
    if not bool(ingest_work_result.get("rating_auto_elevated", False)):
        uploaded_msg = "uploaded"
    return _redirect(
        response,
        f"/fanart/{quote(username, safe='')}?msg={uploaded_msg}",
    )
