"""responses common domain implementation."""

import json
import mimetypes
import re
import secrets
import time
import tomllib
from collections.abc import Callable
from html import escape
from pathlib import Path
from tempfile import TemporaryDirectory
from textwrap import dedent
from typing import cast

from authlib.jose import jwt
from authlib.jose.errors import JoseError

from fanic.cylinder_sites.common.protocols import FileUploadLike
from fanic.cylinder_sites.common.protocols import RequestLike
from fanic.cylinder_sites.common.protocols import ResponseLike
from fanic.cylinder_sites.common.security import MAX_CBZ_UPLOAD_BYTES
from fanic.cylinder_sites.common.security import validate_cbz_upload_policy
from fanic.cylinder_sites.common.security import validate_saved_upload_size
from fanic.cylinder_sites.site_layout import site_header_parts_for_template
from fanic.cylinder_sites.user_roles import is_privileged_role
from fanic.ingest import ingest_cbz
from fanic.repository.users import UserRole
from fanic.repository.users import get_local_user
from fanic.repository.users import get_user_role
from fanic.repository.users import get_user_theme_preference
from fanic.settings import DYNAMIC_TEMPLATE_DIR
from fanic.settings import WORKS_DIR
from fanic.settings import get_settings

STATIC_ROOT = DYNAMIC_TEMPLATE_DIR
_SETTINGS = get_settings()
SESSION_COOKIE_NAME = "fanic_session"
CSRF_COOKIE_NAME = "fanic_csrf"
SESSION_SECRET = _SETTINGS.session_secret
SESSION_MAX_AGE = _SETTINGS.session_max_age
SESSION_COOKIE_SECURE = _SETTINGS.session_secure_effective
SESSION_COOKIE_SAMESITE = _SETTINGS.session_cookie_samesite
CSRF_PROTECT = _SETTINGS.csrf_protect_effective
_POST_FORM_OPEN_TAG_RE = re.compile(
    r"<form\b[^>]*\bmethod\s*=\s*(['\"]?)post\1[^>]*>",
    flags=re.IGNORECASE,
)
_REQUEST_ID_ATTR = "_fanic_request_id"
RATING_ICON_BY_NAME = {
    "General Audiences": "citrus.svg",
    "Teen And Up Audiences": "orange.svg",
    "Mature": "lime.svg",
    "Explicit": "lemon.svg",
}
SITE_FOOTER_HTML = dedent(
    """
    <footer class="site-footer" role="contentinfo">
    <div class="site-footer-inner">
    <a class="site-footer-link" href="/terms">Terms and Conditions</a>
    <span class="site-footer-sep" aria-hidden="true"> | </span>
    <a class="site-footer-link" href="/faq">FAQ</a>
    <span class="site-footer-sep" aria-hidden="true"> | </span>
    <a class="site-footer-link" href="/dmca">Report Copyright/Content</a>
    <span class="site-footer-sep" aria-hidden="true"> | </span>
    <a class="site-footer-link" href="/cbz-format">CBZ SPEC INFO</a>
    </div>
    </footer>
    """
).strip()
SITE_HEAD_ASSETS_HTML = dedent(
    """
    <link rel="icon" href="/static/logo.png" type="image/png" />
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Source+Serif+4:wght@400;700&display=swap" rel="stylesheet" />
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.2/css/all.min.css" />
    <link rel="stylesheet" href="/static/styles.css" />
    """
).strip()
SITE_COMMON_SCRIPTS_HTML = dedent(
    """
    <script src="/static/user-menu.js?v=20260329-logged-out-page"></script>
    <script src="/static/confirm-actions.js?v=20260401-csp"></script>
    <script src="/static/queued-images.js?v=20260401-queue"></script>
    """
).strip()


def site_logo_html(*, home_href: str = "/", include_title_wrapper: bool = True) -> str:
    safe_home_href = escape(home_href)
    logo_anchor = dedent(
        f"""
        <a href="{safe_home_href}" aria-label="FANIC home">
        <img class="site-logo" src="/static/logo.png" alt="FANIC Logo" />
        </a>
        """
    ).strip()
    if include_title_wrapper:
        return dedent(
            f"""
            <h1 class="site-title">
            {logo_anchor}
            </h1>
            """
        ).strip()
    return logo_anchor


THEME_VAR_ALLOWLIST = {
    "bg",
    "paper",
    "ink",
    "accent",
    "accent-soft",
    "line",
    "muted",
    "tag-bg",
    "panel-bg",
    "header-bg",
    "surface-strong",
    "danger-bg",
    "danger-line",
    "danger-ink",
    "reader-overlay-border",
    "reader-overlay-bg",
    "reader-overlay-ink",
    "reader-page-bg",
    "bg-glow-1",
    "bg-glow-2",
}
SAFE_THEME_VALUE_PATTERN = re.compile(r"^[#(),.%/\-\sA-Za-z0-9]+$")
JWTDecode = Callable[[str | bytes, object], dict[str, object]]
JWT_DECODE = cast(JWTDecode, jwt.decode)


def _header_value(request: RequestLike, header_name: str) -> str:
    headers_obj = getattr(request, "headers", None)
    if headers_obj is None:
        return ""
    if not hasattr(headers_obj, "get"):
        return ""
    getter = cast(Callable[[str, str], object], headers_obj.get)
    value_obj = getter(header_name, "")
    return str(value_obj)


def request_id(request: RequestLike, response: ResponseLike | None = None) -> str:
    existing = getattr(request, _REQUEST_ID_ATTR, "")
    existing_id = str(existing).strip()
    if existing_id:
        if response is not None:
            response.headers["X-Request-ID"] = existing_id
        return existing_id

    incoming = _header_value(request, "X-Request-ID").strip()
    resolved = incoming if incoming else secrets.token_hex(16)
    setattr(request, _REQUEST_ID_ATTR, resolved)
    if response is not None:
        response.headers["X-Request-ID"] = resolved
    return resolved


def role_for_user(username: str | None) -> UserRole:
    return get_user_role(username)


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


def current_user_role(request: RequestLike) -> UserRole:
    username = current_user(request)
    return role_for_user(username)


def is_admin_request(request: RequestLike) -> bool:
    role = current_user_role(request)
    return is_privileged_role(role)


def admin_aware_detail(
    request: RequestLike,
    *,
    public_detail: str,
    exc: Exception | None = None,
) -> str:
    if not is_admin_request(request):
        return public_detail
    if exc is None:
        return public_detail
    return str(exc) if str(exc) else public_detail


def json_response(response: ResponseLike, payload: dict[str, object], status_code: int = 200) -> ResponseLike:
    response.status_code = status_code
    response.content_type = "application/json; charset=utf-8"
    response.set_data(json.dumps(payload, ensure_ascii=True))
    return response


def stable_api_error(
    request: RequestLike,
    response: ResponseLike,
    *,
    error: str,
    public_detail: str,
    status_code: int,
    exc: Exception | None = None,
) -> ResponseLike:
    rid = request_id(request, response)
    detail = admin_aware_detail(request, public_detail=public_detail, exc=exc)
    return json_response(
        response,
        {
            "ok": False,
            "error": error,
            "detail": detail,
            "request_id": rid,
        },
        status_code,
    )


def text_error(response: ResponseLike, message: str, status_code: int = 404) -> ResponseLike:
    response.status_code = status_code
    response.content_type = "text/plain; charset=utf-8"
    response.set_data(message)
    return response


def redirect_see_other(response: ResponseLike, location: str) -> ResponseLike:
    response.status_code = 303
    response.content_type = "text/plain; charset=utf-8"
    response.headers["Location"] = location
    response.set_data(f"See Other: {location}")
    return response


def send_file(response: ResponseLike, path: Path, filename: str | None = None) -> ResponseLike:
    if not path.exists() or not path.is_file():
        return text_error(response, "Not found", 404)

    content_type, _ = mimetypes.guess_type(str(path))
    response.content_type = content_type if content_type else "application/octet-stream"
    response.set_data(path.read_bytes())

    if filename:
        response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'

    return response


def _ensure_csrf_token(request: RequestLike, response: ResponseLike) -> str:
    existing_token = request.cookies.get(CSRF_COOKIE_NAME, "")
    token = existing_token.strip()
    if token:
        return token

    token = secrets.token_urlsafe(32)
    response.set_cookie(
        CSRF_COOKIE_NAME,
        token,
        max_age=SESSION_MAX_AGE,
        path="/",
        secure=SESSION_COOKIE_SECURE,
        httponly=False,
        samesite=SESSION_COOKIE_SAMESITE,
    )
    return token


def _inject_csrf_inputs(html: str, csrf_token: str) -> str:
    def replacer(match: re.Match[str]) -> str:
        open_tag = match.group(0)
        return f'{open_tag}<input type="hidden" name="csrf_token" value="{escape(csrf_token)}" />'

    return _POST_FORM_OPEN_TAG_RE.sub(replacer, html)


def apply_security_markup(
    request: RequestLike,
    response: ResponseLike,
    html: str,
) -> str:
    if not CSRF_PROTECT:
        return html
    csrf_token = _ensure_csrf_token(request, response)
    return _inject_csrf_inputs(html, csrf_token)


def user_menu_replacements(request: RequestLike) -> dict[str, str]:
    username = current_user(request)
    logged_in = username is not None
    display_name = ""
    if logged_in and username:
        try:
            local_user = get_local_user(username)
            display_name = local_user["display_name"] if local_user is not None else username
        except Exception:
            display_name = username
    role = current_user_role(request)
    is_admin = is_privileged_role(role)
    reports_current_attr = ' aria-current="page"' if request.path == "/admin/reports" else ""
    users_current_attr = ' aria-current="page"' if request.path == "/admin/users" else ""
    tags_current_attr = ' aria-current="page"' if request.path == "/admin/tag-popularity" else ""
    admin_reports_link = (
        dedent(
            f"""
            <a href="/admin/reports"{reports_current_attr}>Reports</a>
            <a href="/admin/users"{users_current_attr}>Users</a>
            <a href="/admin/tag-popularity"{tags_current_attr}>Tag Popularity</a>
            """
        ).strip()
        if is_admin
        else ""
    )
    login_hidden_attr = "hidden" if logged_in else ""
    profile_hidden_attr = "" if logged_in else "hidden"
    logout_hidden_attr = "" if logged_in else "hidden"
    status_text = "Logged in as " + escape(display_name) + "." if logged_in and username else "Not logged in."
    user_menu_panel_content = dedent(
        f"""
        <p id="userMenuStatus" class="user-menu-status">{status_text}</p>
        <a id="userMenuLogin" class="user-menu-link" href="/account/login" {login_hidden_attr}>Login</a>
        <a id="userMenuSignup" class="user-menu-link" href="https://fanic.media/account/auth0/signup" {login_hidden_attr}>Create an account</a>
        <a id="userMenuProfile" class="user-menu-link" href="/user/profile" {profile_hidden_attr}>Profile</a>
        __USER_MENU_UPLOAD_LINK__
        <a id="userMenuLogout" class="user-menu-link user-menu-logout" href="/account/logout" {logout_hidden_attr}>Logout</a>
        """
    ).strip()
    user_menu_html = dedent(
        f"""
        <div class="user-menu">
        <button id="userMenuButton" class="user-menu-button" type="button"
        aria-haspopup="true" aria-expanded="false" aria-controls="userMenuPanel"
        title="User menu">
        <i class="fa-solid fa-user" aria-hidden="true"></i>
        <span class="sr-only">User menu</span>
        </button>
        <div id="userMenuPanel" class="user-menu-panel" hidden>
        {user_menu_panel_content}
        </div>
        </div>
        """
    ).strip()
    return {
        "__USER_MENU_STATUS__": f"Logged in as {escape(display_name)}." if logged_in and username else "Not logged in.",
        "__USER_MENU_LOGIN_HIDDEN_ATTR__": login_hidden_attr,
        "__USER_MENU_PROFILE_HIDDEN_ATTR__": profile_hidden_attr,
        "__USER_MENU_LOGOUT_HIDDEN_ATTR__": logout_hidden_attr,
        "__USER_MENU_PANEL_CONTENT__": user_menu_panel_content,
        "__USER_MENU_HTML__": user_menu_html,
        "__SITE_TAGLINE__": "Fan Archive Nexus for Illustrated Comics",
        "__SITE_LOGO_HTML__": site_logo_html(),
        "__USER_MENU_UPLOAD_LINK__": "",
        "__ADMIN_REPORTS_LINK__": admin_reports_link,
    }


def _replace_markers(text: str, replacements: dict[str, str]) -> str:
    resolved = text
    for marker, value in replacements.items():
        resolved = resolved.replace(marker, value)
    return resolved


def _site_header_html(template_name: str, replacements: dict[str, str]) -> str:
    header_parts = site_header_parts_for_template(template_name)
    resolved_nav_links = _replace_markers(header_parts.nav_links, replacements)
    resolved_meta_html = _replace_markers(header_parts.meta_html, replacements)
    resolved_extra_html = _replace_markers(header_parts.extra_html, replacements)
    resolved_logo = _replace_markers(replacements.get("__SITE_LOGO_HTML__", ""), replacements)
    resolved_user_menu = _replace_markers(replacements.get("__USER_MENU_HTML__", ""), replacements)

    return dedent(
        f"""
        <header class="site-header">
        <div class="site-header-row">
        {resolved_logo}
        {resolved_meta_html}
        <div class="header-actions">
        <nav class="site-nav" aria-label="Primary">
        {resolved_nav_links}
        </nav>
        {resolved_user_menu}
        </div>
        {resolved_extra_html}
        </div>
        </header>
        """
    ).strip()


def _theme_value_is_safe(value: str) -> bool:
    if not value or len(value) > 120:
        return False
    if "{" in value or "}" in value or ";" in value or "<" in value or ">" in value:
        return False
    return bool(SAFE_THEME_VALUE_PATTERN.match(value))


def _normalize_theme_var_name(name: object) -> str:
    text = str(name).strip()
    while text.startswith("--"):
        text = text[2:]
    return text.replace("_", "-")


def _extract_theme_overrides(toml_text: str) -> dict[str, dict[str, str]]:
    parsed: dict[str, object] = tomllib.loads(toml_text)

    result: dict[str, dict[str, str]] = {"light": {}, "dark": {}}
    for theme_name in ("light", "dark"):
        section = parsed.get(theme_name, {})
        if not isinstance(section, dict):
            continue
        section_map = cast(dict[object, object], section)
        for raw_name, raw_value in section_map.items():
            var_name = _normalize_theme_var_name(raw_name)
            if var_name not in THEME_VAR_ALLOWLIST:
                continue
            if not isinstance(raw_value, str):
                continue
            value = raw_value.strip()
            if not _theme_value_is_safe(value):
                continue
            result[theme_name][var_name] = value
    return result


def custom_theme_css_text(request: RequestLike) -> str:
    username = current_user(request)
    if not username:
        return ""

    preference = get_user_theme_preference(username)
    if not preference["enabled"]:
        return ""
    toml_text = preference["toml_text"].strip()
    if not toml_text:
        return ""

    try:
        overrides = _extract_theme_overrides(toml_text)
    except tomllib.TOMLDecodeError:
        return ""

    light_pairs = overrides["light"]
    dark_pairs = overrides["dark"]
    if not light_pairs and not dark_pairs:
        return ""

    css_chunks: list[str] = []
    if light_pairs:
        css_chunks.append(":root {\n")
        for name, value in light_pairs.items():
            css_chunks.append(f"  --{name}: {value};\n")
        css_chunks.append("}\n")
    if dark_pairs:
        css_chunks.append(':root[data-theme="dark"] {\n')
        for name, value in dark_pairs.items():
            css_chunks.append(f"  --{name}: {value};\n")
        css_chunks.append("}\n")
    return "".join(css_chunks)


def rating_badge_html(rating: object) -> str:
    rating_text = str(rating if rating else "Not Rated").strip()
    safe_rating = rating_text if rating_text else "Not Rated"
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
    merged["__SITE_HEAD_ASSETS__"] = SITE_HEAD_ASSETS_HTML
    merged["__SITE_HEADER_HTML__"] = _site_header_html(template_name, merged)
    merged["__SITE_COMMON_SCRIPTS__"] = SITE_COMMON_SCRIPTS_HTML

    for marker, value in merged.items():
        html = html.replace(marker, value)

    custom_theme_css = custom_theme_css_text(request)
    if custom_theme_css and "</head>" in html:
        custom_theme_link = '<link rel="stylesheet" href="/theme/custom.css" />'
        html = html.replace("</head>", f"{custom_theme_link}\n  </head>", 1)

    # Add the global footer to styled site pages without editing each template.
    if "/static/styles.css" in html and "</body>" in html:
        html = html.replace("</body>", f"{SITE_FOOTER_HTML}\n  </body>", 1)

    html = apply_security_markup(request, response, html)

    response.status_code = 200
    response.content_type = "text/html; charset=utf-8"
    response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    response.set_data(html)
    return response


def save_uploaded_ingest(
    cbz_upload: FileUploadLike,
    metadata_upload: FileUploadLike | None,
) -> dict[str, object]:
    cbz_policy_error = validate_cbz_upload_policy(cbz_upload)
    if cbz_policy_error:
        raise ValueError(cbz_policy_error)

    cbz_filename = cbz_upload.filename if cbz_upload.filename else "upload.cbz"
    cbz_name = Path(cbz_filename).name
    metadata_name = (
        Path(metadata_upload.filename if metadata_upload.filename else "metadata.json").name
        if metadata_upload is not None
        else "metadata.json"
    )

    with TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        cbz_path = temp_root / cbz_name
        cbz_upload.save(cbz_path)

        cbz_size_error = validate_saved_upload_size(
            cbz_path,
            MAX_CBZ_UPLOAD_BYTES,
            "CBZ upload",
        )
        if cbz_size_error:
            raise ValueError(cbz_size_error)

        metadata_path: Path | None = None
        if metadata_upload is not None and metadata_upload.filename:
            metadata_path = temp_root / metadata_name
            metadata_upload.save(metadata_path)

        return ingest_cbz(cbz_path, metadata_path)


def page_file_for(work_id: str, image_name: str) -> Path:
    return WORKS_DIR / work_id / "pages" / image_name


def thumb_file_for(work_id: str, thumb_name: str) -> Path:
    return WORKS_DIR / work_id / "thumbs" / thumb_name


def media_url(path: str) -> str:
    trimmed = path.strip()
    if not trimmed:
        return ""
    if trimmed.startswith("http://") or trimmed.startswith("https://"):
        return trimmed
    if not trimmed.startswith("/"):
        trimmed = f"/{trimmed}"
    media_base = _SETTINGS.media_base_url.strip()
    if not media_base:
        return trimmed
    return f"{media_base.rstrip('/')}{trimmed}"
