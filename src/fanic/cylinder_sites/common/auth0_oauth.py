"""auth0_oauth common domain implementation."""

import time
from collections.abc import Callable
from typing import cast

from authlib.jose import jwt
from authlib.jose.errors import JoseError

from fanic.cylinder_sites.common.protocols import RequestLike
from fanic.cylinder_sites.common.protocols import ResponseLike
from fanic.settings import get_settings

_SETTINGS = get_settings()
AUTH0_OAUTH_COOKIE_NAME = "fanic_auth0_oauth"
SESSION_SECRET = _SETTINGS.session_secret
SESSION_COOKIE_SECURE = _SETTINGS.session_secure_effective
SESSION_COOKIE_SAMESITE = _SETTINGS.session_cookie_samesite
AUTH0_OAUTH_MAX_AGE = 600
JWTEncode = Callable[[object, object, object], bytes]
JWTDecode = Callable[[str | bytes, object], dict[str, object]]
JWT_ENCODE = cast(JWTEncode, jwt.encode)
JWT_DECODE = cast(JWTDecode, jwt.decode)


def _safe_next_url(value: str) -> str:
    candidate = value.strip()
    if not candidate.startswith("/"):
        return "/"
    if candidate.startswith("//"):
        return "/"
    return candidate


def encode_auth0_oauth_state(*, state: str, code_verifier: str, next_url: str) -> str:
    now = int(time.time())
    token = JWT_ENCODE(
        {"alg": "HS256", "typ": "JWT"},
        {
            "state": state,
            "code_verifier": code_verifier,
            "next_url": _safe_next_url(next_url),
            "iat": now,
            "exp": now + AUTH0_OAUTH_MAX_AGE,
        },
        SESSION_SECRET,
    )
    return token.decode("utf-8")


def decode_auth0_oauth_state(token: str) -> dict[str, str] | None:
    try:
        claims = JWT_DECODE(token, SESSION_SECRET)
        exp = claims.get("exp")
        if not isinstance(exp, int) or exp < int(time.time()):
            return None
        state = claims.get("state")
        code_verifier = claims.get("code_verifier")
        next_url = claims.get("next_url")
        if not isinstance(state, str) or not isinstance(code_verifier, str):
            return None
        resolved_next = next_url if isinstance(next_url, str) else "/"
        return {
            "state": state,
            "code_verifier": code_verifier,
            "next_url": _safe_next_url(resolved_next),
        }
    except (JoseError, ValueError):
        return None


def read_auth0_oauth_state(request: RequestLike) -> dict[str, str] | None:
    token = request.cookies.get(AUTH0_OAUTH_COOKIE_NAME, "").strip()
    if not token:
        return None
    return decode_auth0_oauth_state(token)


def set_auth0_oauth_cookie(
    response: ResponseLike,
    *,
    state: str,
    code_verifier: str,
    next_url: str,
) -> None:
    token = encode_auth0_oauth_state(state=state, code_verifier=code_verifier, next_url=next_url)
    response.set_cookie(
        AUTH0_OAUTH_COOKIE_NAME,
        token,
        max_age=AUTH0_OAUTH_MAX_AGE,
        path="/",
        secure=SESSION_COOKIE_SECURE,
        httponly=True,
        samesite=SESSION_COOKIE_SAMESITE,
    )


def clear_auth0_oauth_cookie(response: ResponseLike) -> None:
    response.delete_cookie(AUTH0_OAUTH_COOKIE_NAME, path="/")
