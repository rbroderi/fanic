"""session common domain implementation."""

import secrets
import time
from collections.abc import Callable
from typing import cast

from authlib.jose import jwt
from authlib.jose.errors import JoseError

from fanic.cylinder_sites.common.protocols import RequestLike
from fanic.cylinder_sites.common.protocols import ResponseLike
from fanic.repository.users import UserRole
from fanic.repository.users import get_user_role
from fanic.settings import get_settings

_SETTINGS = get_settings()
SESSION_COOKIE_NAME = "fanic_session"
CSRF_COOKIE_NAME = "fanic_csrf"
SESSION_SECRET = _SETTINGS.session_secret
SESSION_MAX_AGE = _SETTINGS.session_max_age
SESSION_COOKIE_SECURE = _SETTINGS.session_secure_effective
SESSION_COOKIE_SAMESITE = _SETTINGS.session_cookie_samesite
JWTEncode = Callable[[object, object, object], bytes]
JWTDecode = Callable[[str | bytes, object], dict[str, object]]
JWT_ENCODE = cast(JWTEncode, jwt.encode)
JWT_DECODE = cast(JWTDecode, jwt.decode)


def role_for_user(username: str | None) -> UserRole:
    return get_user_role(username)


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
        samesite=SESSION_COOKIE_SAMESITE,
    )
    # Rotate CSRF token on login to prevent token-fixation attacks.
    new_csrf = secrets.token_urlsafe(32)
    response.set_cookie(
        CSRF_COOKIE_NAME,
        new_csrf,
        max_age=SESSION_MAX_AGE,
        path="/",
        secure=SESSION_COOKIE_SECURE,
        httponly=False,
        samesite=SESSION_COOKIE_SAMESITE,
    )


def clear_login_cookie(response: ResponseLike) -> None:
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    response.delete_cookie(CSRF_COOKIE_NAME, path="/")
