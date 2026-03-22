from __future__ import annotations

import json
import mimetypes
import time
from html import escape
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Callable, Protocol, cast

from authlib.jose import jwt
from authlib.jose.errors import JoseError

from fanic.ingest import ingest_cbz
from fanic.paths import WORKS_DIR
from fanic.settings import get_settings

mimetypes.add_type("image/avif", ".avif")

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
STATIC_ROOT = (PACKAGE_ROOT / "static").resolve()
_SETTINGS = get_settings()

SESSION_COOKIE_NAME = "fanic_session"
SESSION_SECRET = _SETTINGS.fanic_session_secret
SESSION_MAX_AGE = _SETTINGS.fanic_session_max_age
SESSION_COOKIE_SECURE = _SETTINGS.fanic_session_secure
ADMIN_USERNAME = _SETTINGS.fanic_admin_username
ADMIN_PASSWORD = _SETTINGS.fanic_admin_password

RATING_ICON_BY_NAME = {
    "General Audiences": "citrus.svg",
    "Teen And Up Audiences": "orange.svg",
    "Mature": "lime.svg",
    "Explicit": "lemon.svg",
}

SITE_FOOTER_HTML = (
    '<footer class="site-footer" role="contentinfo">'
    '<div class="site-footer-inner">'
    '<a class="site-footer-link" href="/terms">Terms and Conditions</a>'
    '<span class="site-footer-sep" aria-hidden="true"> | </span>'
    '<a class="site-footer-link" href="/faq">FAQ</a>'
    '<span class="site-footer-sep" aria-hidden="true"> | </span>'
    '<a class="site-footer-link" href="/dcma">DMCA Policy</a>'
    "</div>"
    "</footer>"
)

JWTEncode = Callable[[object, object, object], bytes]
JWTDecode = Callable[[str | bytes, object], dict[str, object]]
JWT_ENCODE = cast(JWTEncode, jwt.encode)
JWT_DECODE = cast(JWTDecode, jwt.decode)


class QueryArgsLike(Protocol):
    def get(self, key: str, default: str = "") -> str: ...


class FormLike(Protocol):
    def get(self, key: str, default: str = "") -> str: ...


class CookieMapLike(Protocol):
    def get(self, key: str, default: str = "") -> str: ...


class FileUploadLike(Protocol):
    filename: str | None

    def save(self, dst: str | Path) -> None: ...


class FileMapLike(Protocol):
    def get(self, key: str) -> FileUploadLike | None: ...


class RequestLike(Protocol):
    path: str
    method: str
    args: QueryArgsLike
    form: FormLike
    files: FileMapLike
    cookies: CookieMapLike


class ResponseLike(Protocol):
    status_code: int
    content_type: str
    headers: dict[str, str]

    def set_data(self, data: str | bytes) -> None: ...

    def set_cookie(
        self,
        key: str,
        value: str,
        max_age: int | None = None,
        path: str = "/",
        secure: bool = False,
        httponly: bool = False,
        samesite: str = "Lax",
    ) -> None: ...

    def delete_cookie(self, key: str, path: str = "/") -> None: ...


def path_parts(request: RequestLike) -> list[str]:
    return [segment for segment in request.path.split("/") if segment]


def route_tail(request: RequestLike, prefix_parts: list[str]) -> list[str] | None:
    parts = path_parts(request)
    if len(parts) < len(prefix_parts):
        return None
    if parts[: len(prefix_parts)] != prefix_parts:
        return None
    return parts[len(prefix_parts) :]


def json_response(
    response: ResponseLike, payload: dict[str, object], status_code: int = 200
) -> ResponseLike:
    response.status_code = status_code
    response.content_type = "application/json; charset=utf-8"
    response.set_data(json.dumps(payload, ensure_ascii=True))
    return response


def text_error(
    response: ResponseLike, message: str, status_code: int = 404
) -> ResponseLike:
    response.status_code = status_code
    response.content_type = "text/plain; charset=utf-8"
    response.set_data(message)
    return response


def send_file(
    response: ResponseLike, path: Path, filename: str | None = None
) -> ResponseLike:
    if not path.exists() or not path.is_file():
        return text_error(response, "Not found", 404)

    content_type, _ = mimetypes.guess_type(str(path))
    response.content_type = content_type or "application/octet-stream"
    response.set_data(path.read_bytes())

    if filename:
        response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'

    return response


def safe_static_path(rel_path: str) -> Path | None:
    candidate = (STATIC_ROOT / rel_path).resolve()
    try:
        _ = candidate.relative_to(STATIC_ROOT)
    except ValueError:
        return None
    return candidate


def encode_session(username: str) -> str:
    now = int(time.time())
    token = JWT_ENCODE(
        {"alg": "HS256", "typ": "JWT"},
        {
            "sub": username,
            "iat": now,
            "exp": now + SESSION_MAX_AGE,
        },
        SESSION_SECRET,
    )
    return token.decode("utf-8")


def decode_session(token: str) -> str | None:
    try:
        claims = JWT_DECODE(token, SESSION_SECRET)

        exp = claims.get("exp")
        if not isinstance(exp, int):
            return None
        if exp < int(time.time()):
            return None

        username = claims.get("sub")
        if isinstance(username, str):
            return username
        return None
    except (JoseError, ValueError):
        return None


def current_user(request: RequestLike) -> str | None:
    token = request.cookies.get(SESSION_COOKIE_NAME, "")
    if not token:
        return None
    return decode_session(token)


def set_login_cookie(response: ResponseLike, username: str) -> None:
    token = encode_session(username)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        max_age=SESSION_MAX_AGE,
        path="/",
        secure=SESSION_COOKIE_SECURE,
        httponly=True,
        samesite="Lax",
    )


def clear_login_cookie(response: ResponseLike) -> None:
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")


def user_menu_replacements(request: RequestLike) -> dict[str, str]:
    username = current_user(request)
    logged_in = username is not None
    return {
        "__USER_MENU_STATUS__": f"Logged in as {escape(username)}."
        if logged_in and username
        else "Not logged in.",
        "__USER_MENU_LOGIN_HIDDEN_ATTR__": "hidden" if logged_in else "",
        "__USER_MENU_PROFILE_HIDDEN_ATTR__": "" if logged_in else "hidden",
        "__USER_MENU_LOGOUT_HIDDEN_ATTR__": "" if logged_in else "hidden",
    }


def rating_badge_html(rating: object) -> str:
    safe_rating = str(rating or "Not Rated").strip() or "Not Rated"
    icon_name = RATING_ICON_BY_NAME.get(safe_rating)
    safe_label = escape(safe_rating)
    if not icon_name:
        return f'<span class="rating-badge"><span>{safe_label}</span></span>'

    safe_icon = escape(icon_name)
    return (
        '<span class="rating-badge">'
        f'<img class="rating-logo" src="/static/{safe_icon}" alt="" aria-hidden="true" />'
        f"<span>{safe_label}</span>"
        "</span>"
    )


def render_html_template(
    request: RequestLike,
    response: ResponseLike,
    template_name: str,
    replacements: dict[str, str] | None = None,
) -> ResponseLike:
    html = (STATIC_ROOT / template_name).read_text(encoding="utf-8")
    merged = user_menu_replacements(request)
    if replacements:
        merged.update(replacements)

    for marker, value in merged.items():
        html = html.replace(marker, value)

    # Add the global footer to styled site pages without editing each template.
    if "/static/styles.css" in html and "</body>" in html:
        html = html.replace("</body>", f"{SITE_FOOTER_HTML}\n  </body>", 1)

    response.status_code = 200
    response.content_type = "text/html; charset=utf-8"
    response.set_data(html)
    return response


def save_uploaded_ingest(
    cbz_upload: FileUploadLike,
    metadata_upload: FileUploadLike | None,
) -> dict[str, object]:
    cbz_name = Path(cbz_upload.filename or "upload.cbz").name
    metadata_name = (
        Path(metadata_upload.filename or "metadata.json").name
        if metadata_upload is not None
        else "metadata.json"
    )

    with TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        cbz_path = temp_root / cbz_name
        cbz_upload.save(cbz_path)

        metadata_path: Path | None = None
        if metadata_upload is not None and metadata_upload.filename:
            metadata_path = temp_root / metadata_name
            metadata_upload.save(metadata_path)

        return ingest_cbz(cbz_path, metadata_path)


def page_file_for(work_id: str, image_name: str) -> Path:
    return WORKS_DIR / work_id / "pages" / image_name


def thumb_file_for(work_id: str, thumb_name: str) -> Path:
    return WORKS_DIR / work_id / "thumbs" / thumb_name
