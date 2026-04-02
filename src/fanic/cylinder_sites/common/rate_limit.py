"""rate_limit common domain implementation."""

import threading
import time
from collections.abc import Callable
from typing import cast

import structlog

from fanic.cylinder_sites.common.protocols import RequestLike
from fanic.settings import get_settings

_SETTINGS = get_settings()
AUTH_MAX_FAILURES = _SETTINGS.auth_max_failures
AUTH_WINDOW_SECONDS = _SETTINGS.auth_window_seconds
AUTH_LOCKOUT_SECONDS = _SETTINGS.auth_lockout_seconds
UPLOAD_RATE_WINDOW_SECONDS = _SETTINGS.upload_rate_window_seconds
UPLOAD_RATE_MAX_REQUESTS = _SETTINGS.upload_rate_max_requests
UPLOAD_MAX_CONCURRENT_PER_USER = _SETTINGS.upload_max_concurrent_per_user
COMIC_INGEST_MAX_CONCURRENT = _SETTINGS.comic_ingest_max_concurrent
COMIC_INGEST_QUEUE_WAIT_SECONDS = _SETTINGS.comic_ingest_queue_wait_seconds
MAX_SHORT_FIELD_LENGTH = 512
MAX_LONG_FIELD_LENGTH = 4096
MAX_URL_FIELD_LENGTH = 2048
POST_RATE_WINDOW_SECONDS = 60
POST_RATE_MAX_REQUESTS = 30
MAX_TRACKED_RATE_LIMIT_KEYS = int(getattr(_SETTINGS, "max_tracked_rate_limit_keys", 10000))
_AUTH_LOCK = threading.Lock()
_AUTH_FAILURE_TIMESTAMPS: dict[str, list[float]] = {}
_AUTH_LOCKED_UNTIL: dict[str, float] = {}
_POST_RATE_LOCK = threading.Lock()
_POST_RATE_TIMESTAMPS: dict[str, list[float]] = {}
_UPLOAD_LOCK = threading.Lock()
_UPLOAD_ATTEMPT_TIMESTAMPS: dict[str, list[float]] = {}
_UPLOAD_IN_FLIGHT: dict[str, int] = {}


class _ComicIngestQueueState:
    lock: threading.Lock
    condition: threading.Condition
    active: int
    waiting: int

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.condition = threading.Condition(self.lock)
        self.active = 0
        self.waiting = 0


_comic_ingest_state = _ComicIngestQueueState()

LOGGER = structlog.get_logger("fanic.http")


def _header_value(request: RequestLike, header_name: str) -> str:
    headers_obj = getattr(request, "headers", None)
    if headers_obj is None:
        return ""
    if not hasattr(headers_obj, "get"):
        return ""
    getter = cast(Callable[[str, str], object], headers_obj.get)
    value_obj = getter(header_name, "")
    return str(value_obj)


def _request_client_ip(request: RequestLike) -> str:
    forwarded_for = _header_value(request, "X-Forwarded-For")
    if forwarded_for:
        client = forwarded_for.split(",")[0].strip()
        if client:
            return client

    remote_addr_obj = getattr(request, "remote_addr", "")
    remote_addr = str(remote_addr_obj).strip()
    if remote_addr:
        return remote_addr
    return "unknown"


def _auth_key(request: RequestLike, username: str) -> str:
    client = _request_client_ip(request)
    normalized_user = username.strip().lower()
    return f"{client}:{normalized_user}"


def auth_lockout_seconds_remaining(request: RequestLike, username: str) -> int:
    key = _auth_key(request, username)
    now = time.time()
    with _AUTH_LOCK:
        locked_until = _AUTH_LOCKED_UNTIL.get(key, 0.0)
        if locked_until <= now:
            if key in _AUTH_LOCKED_UNTIL:
                _AUTH_LOCKED_UNTIL.pop(key)
            return 0
        return int(locked_until - now)


def record_auth_failure(request: RequestLike, username: str) -> int:
    key = _auth_key(request, username)
    client_ip = _request_client_ip(request)
    now = time.time()
    with _AUTH_LOCK:
        _prune_stale_auth_entries(now)
        attempts = _AUTH_FAILURE_TIMESTAMPS.get(key, [])
        window_floor = now - AUTH_WINDOW_SECONDS
        attempts = [attempt for attempt in attempts if attempt >= window_floor]
        attempts.append(now)
        _AUTH_FAILURE_TIMESTAMPS[key] = attempts

        if len(attempts) >= AUTH_MAX_FAILURES:
            _AUTH_LOCKED_UNTIL[key] = now + AUTH_LOCKOUT_SECONDS
            _AUTH_FAILURE_TIMESTAMPS[key] = []
            LOGGER.warning(
                "auth lockout triggered",
                event_type="security",
                username=username,
                client_ip=client_ip,
                lockout_seconds=AUTH_LOCKOUT_SECONDS,
            )
            return AUTH_LOCKOUT_SECONDS
        LOGGER.info(
            "auth failure recorded",
            event_type="security",
            username=username,
            client_ip=client_ip,
            attempt_count=len(attempts),
        )
        return 0


def _prune_stale_auth_entries(now: float) -> None:
    """Remove expired lockout entries to prevent unbounded memory growth.

    Must be called while holding ``_AUTH_LOCK``.
    """
    cutoff = now - AUTH_LOCKOUT_SECONDS * 2
    stale_keys = [key for key, locked_until in _AUTH_LOCKED_UNTIL.items() if locked_until < cutoff]
    for key in stale_keys:
        _AUTH_LOCKED_UNTIL.pop(key, None)
        _AUTH_FAILURE_TIMESTAMPS.pop(key, None)

    if len(_AUTH_LOCKED_UNTIL) <= MAX_TRACKED_RATE_LIMIT_KEYS:
        return

    overflow = len(_AUTH_LOCKED_UNTIL) - MAX_TRACKED_RATE_LIMIT_KEYS
    sorted_keys = sorted(_AUTH_LOCKED_UNTIL, key=lambda key: _AUTH_LOCKED_UNTIL.get(key, 0.0))
    for key in sorted_keys[:overflow]:
        _AUTH_LOCKED_UNTIL.pop(key, None)
        _AUTH_FAILURE_TIMESTAMPS.pop(key, None)


def _prune_stale_post_rate_entries(now: float) -> None:
    cutoff = now - POST_RATE_WINDOW_SECONDS * 2
    stale_keys = [key for key, attempts in _POST_RATE_TIMESTAMPS.items() if not attempts or max(attempts) < cutoff]
    for key in stale_keys:
        _POST_RATE_TIMESTAMPS.pop(key, None)

    if len(_POST_RATE_TIMESTAMPS) <= MAX_TRACKED_RATE_LIMIT_KEYS:
        return

    overflow = len(_POST_RATE_TIMESTAMPS) - MAX_TRACKED_RATE_LIMIT_KEYS
    sorted_keys = sorted(
        _POST_RATE_TIMESTAMPS,
        key=lambda key: max(_POST_RATE_TIMESTAMPS.get(key, [0.0])),
    )
    for key in sorted_keys[:overflow]:
        _POST_RATE_TIMESTAMPS.pop(key, None)


def _prune_stale_upload_rate_entries(now: float) -> None:
    cutoff = now - UPLOAD_RATE_WINDOW_SECONDS * 2
    stale_keys = [
        key
        for key, attempts in _UPLOAD_ATTEMPT_TIMESTAMPS.items()
        if (not attempts or max(attempts) < cutoff) and _UPLOAD_IN_FLIGHT.get(key, 0) <= 0
    ]
    for key in stale_keys:
        _UPLOAD_ATTEMPT_TIMESTAMPS.pop(key, None)
        _UPLOAD_IN_FLIGHT.pop(key, None)

    if len(_UPLOAD_ATTEMPT_TIMESTAMPS) <= MAX_TRACKED_RATE_LIMIT_KEYS:
        return

    overflow = len(_UPLOAD_ATTEMPT_TIMESTAMPS) - MAX_TRACKED_RATE_LIMIT_KEYS
    sorted_keys = sorted(
        _UPLOAD_ATTEMPT_TIMESTAMPS,
        key=lambda key: max(_UPLOAD_ATTEMPT_TIMESTAMPS.get(key, [0.0])),
    )
    for key in sorted_keys[:overflow]:
        if _UPLOAD_IN_FLIGHT.get(key, 0) <= 0:
            _UPLOAD_ATTEMPT_TIMESTAMPS.pop(key, None)
            _UPLOAD_IN_FLIGHT.pop(key, None)


def clear_auth_failures(request: RequestLike, username: str) -> None:
    key = _auth_key(request, username)
    with _AUTH_LOCK:
        if key in _AUTH_FAILURE_TIMESTAMPS:
            _AUTH_FAILURE_TIMESTAMPS.pop(key)
        if key in _AUTH_LOCKED_UNTIL:
            _AUTH_LOCKED_UNTIL.pop(key)


def begin_upload_session(username: str) -> tuple[bool, str, int]:
    normalized_username = username.strip().lower()
    if not normalized_username:
        return True, "", 0

    now = time.time()
    with _UPLOAD_LOCK:
        _prune_stale_upload_rate_entries(now)
        attempts = _UPLOAD_ATTEMPT_TIMESTAMPS.get(normalized_username, [])
        window_floor = now - UPLOAD_RATE_WINDOW_SECONDS
        attempts = [attempt for attempt in attempts if attempt >= window_floor]

        current_in_flight = _UPLOAD_IN_FLIGHT.get(normalized_username, 0)
        if current_in_flight >= UPLOAD_MAX_CONCURRENT_PER_USER:
            _UPLOAD_ATTEMPT_TIMESTAMPS[normalized_username] = attempts
            return False, "upload_concurrency_limited", 0

        if len(attempts) >= UPLOAD_RATE_MAX_REQUESTS:
            oldest_attempt = attempts[0]
            retry_after = int(max(1, oldest_attempt + UPLOAD_RATE_WINDOW_SECONDS - now))
            _UPLOAD_ATTEMPT_TIMESTAMPS[normalized_username] = attempts
            return False, "upload_rate_limited", retry_after

        attempts.append(now)
        _UPLOAD_ATTEMPT_TIMESTAMPS[normalized_username] = attempts
        _UPLOAD_IN_FLIGHT[normalized_username] = current_in_flight + 1
    return True, "", 0


def end_upload_session(username: str) -> None:
    normalized_username = username.strip().lower()
    if not normalized_username:
        return

    with _UPLOAD_LOCK:
        current_in_flight = _UPLOAD_IN_FLIGHT.get(normalized_username, 0)
        if current_in_flight <= 1:
            if normalized_username in _UPLOAD_IN_FLIGHT:
                _UPLOAD_IN_FLIGHT.pop(normalized_username)
            return
        _UPLOAD_IN_FLIGHT[normalized_username] = current_in_flight - 1


def begin_comic_ingest_session(
    *,
    wait_timeout_seconds: int | None = None,
    on_queued: Callable[[int], None] | None = None,
) -> tuple[bool, int, int]:
    if COMIC_INGEST_MAX_CONCURRENT <= 0:
        return True, 0, 0

    timeout_seconds = wait_timeout_seconds if wait_timeout_seconds is not None else COMIC_INGEST_QUEUE_WAIT_SECONDS
    timeout_seconds = max(timeout_seconds, 0)
    deadline = time.time() + timeout_seconds

    queue_state = _comic_ingest_state
    with queue_state.condition:
        queued = False
        queue_position = 0
        while queue_state.active >= COMIC_INGEST_MAX_CONCURRENT:
            if not queued:
                queue_state.waiting += 1
                queued = True
                queue_position = queue_state.waiting
            else:
                queue_position = queue_state.waiting

            if on_queued is not None and queue_position > 0:
                try:
                    on_queued(queue_position)
                except Exception:
                    pass

            remaining = deadline - time.time()
            if remaining <= 0:
                if queued:
                    queue_state.waiting -= 1
                timeout_retry_after = 1
                return (
                    False,
                    timeout_retry_after,
                    queue_position if queue_position else 1,
                )

            queue_state.condition.wait(timeout=remaining)

        if queued:
            queue_state.waiting -= 1
        queue_state.active += 1
    return True, 0, queue_position


def end_comic_ingest_session() -> None:
    queue_state = _comic_ingest_state
    with queue_state.condition:
        if queue_state.active > 0:
            queue_state.active -= 1
        queue_state.condition.notify()


def check_post_rate_limit(request: RequestLike) -> int:
    """Return retry-after seconds if the client IP exceeds the POST rate limit, else 0."""
    client_ip = _request_client_ip(request)
    now = time.time()
    with _POST_RATE_LOCK:
        _prune_stale_post_rate_entries(now)
        attempts = _POST_RATE_TIMESTAMPS.get(client_ip, [])
        window_floor = now - POST_RATE_WINDOW_SECONDS
        attempts = [ts for ts in attempts if ts >= window_floor]

        if len(attempts) >= POST_RATE_MAX_REQUESTS:
            oldest = attempts[0]
            retry_after = int(max(1, oldest + POST_RATE_WINDOW_SECONDS - now))
            _POST_RATE_TIMESTAMPS[client_ip] = attempts
            LOGGER.warning(
                "POST rate limit exceeded",
                event_type="security",
                client_ip=client_ip,
                retry_after=retry_after,
            )
            return retry_after

        attempts.append(now)
        _POST_RATE_TIMESTAMPS[client_ip] = attempts
    return 0


def validate_field_lengths(
    fields: dict[str, str],
    *,
    short: set[str] | None = None,
    long: set[str] | None = None,
    url: set[str] | None = None,
) -> str | None:
    """Return an error message if any field exceeds its length limit, else None."""
    for name, value in fields.items():
        if short and name in short:
            if len(value) > MAX_SHORT_FIELD_LENGTH:
                return f"{name} exceeds maximum length ({MAX_SHORT_FIELD_LENGTH} chars)"
        elif url and name in url:
            if len(value) > MAX_URL_FIELD_LENGTH:
                return f"{name} exceeds maximum length ({MAX_URL_FIELD_LENGTH} chars)"
        elif long and name in long:
            if len(value) > MAX_LONG_FIELD_LENGTH:
                return f"{name} exceeds maximum length ({MAX_LONG_FIELD_LENGTH} chars)"
    return None


__all__ = [
    "AUTH_LOCKOUT_SECONDS",
    "AUTH_MAX_FAILURES",
    "AUTH_WINDOW_SECONDS",
    "COMIC_INGEST_MAX_CONCURRENT",
    "COMIC_INGEST_QUEUE_WAIT_SECONDS",
    "POST_RATE_MAX_REQUESTS",
    "POST_RATE_WINDOW_SECONDS",
    "RequestLike",
    "auth_lockout_seconds_remaining",
    "begin_comic_ingest_session",
    "begin_upload_session",
    "check_post_rate_limit",
    "clear_auth_failures",
    "end_comic_ingest_session",
    "end_upload_session",
    "record_auth_failure",
    "validate_field_lengths",
]
