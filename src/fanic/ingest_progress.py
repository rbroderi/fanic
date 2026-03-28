import time
from threading import Lock
from typing import TypedDict


class IngestProgress(TypedDict):
    stage: str
    message: str
    current: int
    total: int
    done: bool
    ok: bool
    updated_at: float


_PROGRESS: dict[str, IngestProgress] = {}
_LOCK = Lock()
_TTL_SECONDS = 60 * 15


def _prune_stale(now: float) -> None:
    stale_keys = [key for key, value in _PROGRESS.items() if now - value["updated_at"] > _TTL_SECONDS]
    for key in stale_keys:
        if key in _PROGRESS:
            del _PROGRESS[key]


def set_progress(
    token: str,
    *,
    stage: str,
    message: str,
    current: int = 0,
    total: int = 0,
    done: bool = False,
    ok: bool = False,
) -> None:
    if not token:
        return

    now = time.time()
    with _LOCK:
        _prune_stale(now)
        _PROGRESS[token] = {
            "stage": stage,
            "message": message,
            "current": int(current),
            "total": int(total),
            "done": bool(done),
            "ok": bool(ok),
            "updated_at": now,
        }


def get_progress(token: str) -> IngestProgress | None:
    if not token:
        return None

    now = time.time()
    with _LOCK:
        _prune_stale(now)
        value = _PROGRESS.get(token)
        if value is None:
            return None
        return {
            "stage": value["stage"],
            "message": value["message"],
            "current": value["current"],
            "total": value["total"],
            "done": value["done"],
            "ok": value["ok"],
            "updated_at": value["updated_at"],
        }
