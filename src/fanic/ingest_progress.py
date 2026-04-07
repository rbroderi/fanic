import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from threading import Lock
from typing import NotRequired
from typing import TypedDict
from typing import cast


class IngestProgress(TypedDict):
    stage: str
    message: str
    current: int
    total: int
    done: bool
    ok: bool
    updated_at: float
    work_id: NotRequired[str]
    redirect_to: NotRequired[str]


_PROGRESS: dict[str, IngestProgress] = {}
_LOCK = Lock()
_TTL_SECONDS = 60 * 15


def _progress_dir() -> Path:
    configured = os.getenv("FANIC_INGEST_PROGRESS_DIR", "").strip()
    if configured:
        path = Path(configured)
    else:
        path = Path(tempfile.gettempdir()) / "fanic-ingest-progress"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _progress_file_path(token: str) -> Path:
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return _progress_dir() / f"{token_hash}.json"


def _write_progress_file(token: str, value: IngestProgress) -> None:
    path = _progress_file_path(token)
    temp_path = path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(value, ensure_ascii=True), encoding="utf-8")
    temp_path.replace(path)


def _read_progress_file(token: str) -> IngestProgress | None:
    path = _progress_file_path(token)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None

    if not isinstance(payload, dict):
        return None
    payload_map = cast(dict[str, object], payload)

    stage = payload_map.get("stage")
    message = payload_map.get("message")
    current = payload_map.get("current")
    total = payload_map.get("total")
    done = payload_map.get("done")
    ok = payload_map.get("ok")
    updated_at = payload_map.get("updated_at")

    if not isinstance(stage, str) or not isinstance(message, str):
        return None
    if not isinstance(current, int) or not isinstance(total, int):
        return None
    if not isinstance(done, bool) or not isinstance(ok, bool):
        return None
    if not isinstance(updated_at, (int, float)):
        return None

    value: IngestProgress = {
        "stage": stage,
        "message": message,
        "current": int(current),
        "total": int(total),
        "done": done,
        "ok": ok,
        "updated_at": float(updated_at),
    }

    work_id = payload_map.get("work_id")
    redirect_to = payload_map.get("redirect_to")
    if isinstance(work_id, str) and work_id:
        value["work_id"] = work_id
    if isinstance(redirect_to, str) and redirect_to:
        value["redirect_to"] = redirect_to
    return value


def _prune_stale_files(now: float) -> None:
    threshold = now - _TTL_SECONDS
    for path in _progress_dir().glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            try:
                path.unlink()
            except OSError:
                pass
            continue

        payload_map = cast(dict[str, object], payload) if isinstance(payload, dict) else {}
        updated_at = payload_map.get("updated_at")
        is_stale = True
        if isinstance(updated_at, (int, float)):
            is_stale = float(updated_at) < threshold
        if is_stale:
            try:
                path.unlink()
            except OSError:
                pass


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
    work_id: str = "",
    redirect_to: str = "",
) -> None:
    if not token:
        return

    now = time.time()
    with _LOCK:
        _prune_stale(now)
        _prune_stale_files(now)
        value: IngestProgress = {
            "stage": stage,
            "message": message,
            "current": int(current),
            "total": int(total),
            "done": bool(done),
            "ok": bool(ok),
            "updated_at": now,
        }
        if work_id:
            value["work_id"] = work_id
        if redirect_to:
            value["redirect_to"] = redirect_to
        _PROGRESS[token] = value
        _write_progress_file(token, value)


def get_progress(token: str) -> IngestProgress | None:
    if not token:
        return None

    now = time.time()
    with _LOCK:
        _prune_stale(now)
        _prune_stale_files(now)
        value = _PROGRESS.get(token)
        if value is None:
            value = _read_progress_file(token)
            if value is None:
                return None
            if now - value["updated_at"] > _TTL_SECONDS:
                return None
            _PROGRESS[token] = value
        copied: IngestProgress = {
            "stage": value["stage"],
            "message": value["message"],
            "current": value["current"],
            "total": value["total"],
            "done": value["done"],
            "ok": value["ok"],
            "updated_at": value["updated_at"],
        }
        if "work_id" in value and value["work_id"]:
            copied["work_id"] = value["work_id"]
        if "redirect_to" in value and value["redirect_to"]:
            copied["redirect_to"] = value["redirect_to"]
        return copied
