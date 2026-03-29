from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any
from typing import Protocol


class ResponseLike(Protocol):
    status_code: int
    content_type: str
    data: bytes
    headers: dict[str, str]

    def set_data(self, data: str | bytes) -> None: ...


class DummyUpload:
    filename: str
    _payload: bytes

    def __init__(self, filename: str, payload: bytes) -> None:
        self.filename = filename
        self._payload = payload

    def save(self, dst: str | Path) -> None:
        Path(dst).write_bytes(self._payload)


class ImmediateThread:
    _target: Callable[..., None]
    _kwargs: dict[str, Any]

    def __init__(self, *, target: Callable[..., None], kwargs: dict[str, Any], **_: object) -> None:
        self._target = target
        self._kwargs = kwargs

    def start(self) -> None:
        self._target(**self._kwargs)


def test_comic_upload_post_runs_async_worker_and_sets_done_progress(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: Any,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/comic/upload.ex.post.py",
        "fanicsite_comic_upload_ex_post_async_success_test",
    )

    progress_events: list[dict[str, object]] = []
    render_calls: list[dict[str, object]] = []
    ended_upload_users: list[str] = []
    ended_comic_sessions: list[bool] = []

    def enforce_https_termination_stub(_request: Any, _response: Any) -> bool:
        return True

    def validate_csrf_stub(_request: Any) -> bool:
        return True

    def current_user_stub(_request: Any) -> str:
        return "alice"

    def validate_cbz_upload_policy_stub(_upload: Any) -> str:
        return ""

    def validate_saved_upload_size_stub(_path: Any, _max_bytes: Any, _label: Any) -> str:
        return ""

    def begin_upload_session_stub(_username: str) -> tuple[bool, str, int]:
        return (True, "", 0)

    def begin_comic_ingest_session_stub(on_queued: Any) -> tuple[bool, int, int]:
        _ = on_queued
        return (True, 0, 0)

    def end_upload_session_stub(username: str) -> None:
        ended_upload_users.append(username)

    def end_comic_ingest_session_stub() -> None:
        ended_comic_sessions.append(True)

    def ingest_cbz_stub(*_args: object, **_kwargs: object) -> dict[str, object]:
        return {"work_id": "w-123"}

    def fake_render_upload_page(
        request: object,
        response: ResponseLike,
        **kwargs: object,
    ) -> ResponseLike:
        _ = request
        render_calls.append(dict(kwargs))
        response.status_code = 200
        response.content_type = "text/html; charset=utf-8"
        response.set_data("ok")
        return response

    def fake_set_progress(token: str, **kwargs: object) -> None:
        progress_events.append({"token": token, **kwargs})

    monkeypatch.setattr(module, "enforce_https_termination", enforce_https_termination_stub)
    monkeypatch.setattr(module, "validate_csrf", validate_csrf_stub)
    monkeypatch.setattr(module, "current_user", current_user_stub)
    monkeypatch.setattr(module, "validate_cbz_upload_policy", validate_cbz_upload_policy_stub)
    monkeypatch.setattr(module, "validate_saved_upload_size", validate_saved_upload_size_stub)
    monkeypatch.setattr(module, "begin_upload_session", begin_upload_session_stub)
    monkeypatch.setattr(module, "begin_comic_ingest_session", begin_comic_ingest_session_stub)
    monkeypatch.setattr(module, "end_upload_session", end_upload_session_stub)
    monkeypatch.setattr(module, "end_comic_ingest_session", end_comic_ingest_session_stub)
    monkeypatch.setattr(module, "ingest_cbz", ingest_cbz_stub)
    monkeypatch.setattr(module, "render_upload_page", fake_render_upload_page)
    monkeypatch.setattr(module, "set_progress", fake_set_progress)
    monkeypatch.setattr(module.threading, "Thread", ImmediateThread)

    request = dummy_request(
        path="/comic/upload",
        method="POST",
        form={
            "action": "load-metadata",
            "agree_terms": "on",
            "upload_token": "tok-123",
            "title": "My Comic",
        },
        files={
            "cbz": DummyUpload("sample.cbz", b"PK\x03\x04dummy"),
        },
    )
    response = dummy_response()

    result = module.main(request, response)

    assert result.status_code == 200
    assert render_calls
    assert render_calls[-1]["upload_token"] == "tok-123"
    assert render_calls[-1]["upload_status_kind"] == "success"
    assert ended_upload_users == ["alice"]
    assert ended_comic_sessions == [True]

    stages = [str(event.get("stage", "")) for event in progress_events]
    assert "queued" in stages
    assert "done" in stages

    done_events = [event for event in progress_events if str(event.get("stage", "")) == "done"]
    assert done_events
    assert done_events[-1].get("ok") is True
    assert done_events[-1].get("work_id") == "w-123"
    assert done_events[-1].get("redirect_to") == "/comic/w-123"


def test_comic_upload_post_async_worker_reports_queue_timeout(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: Any,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/comic/upload.ex.post.py",
        "fanicsite_comic_upload_ex_post_async_queue_timeout_test",
    )

    progress_events: list[dict[str, object]] = []
    ended_upload_users: list[str] = []
    ended_comic_sessions: list[bool] = []

    def enforce_https_termination_stub(_request: Any, _response: Any) -> bool:
        return True

    def validate_csrf_stub(_request: Any) -> bool:
        return True

    def current_user_stub(_request: Any) -> str:
        return "alice"

    def validate_cbz_upload_policy_stub(_upload: Any) -> str:
        return ""

    def validate_saved_upload_size_stub(_path: Any, _max_bytes: Any, _label: Any) -> str:
        return ""

    def begin_upload_session_stub(_username: str) -> tuple[bool, str, int]:
        return (True, "", 0)

    def begin_comic_ingest_session_stub(on_queued: Any) -> tuple[bool, int, int]:
        _ = on_queued
        return (False, 0, 2)

    def end_upload_session_stub(username: str) -> None:
        ended_upload_users.append(username)

    def end_comic_ingest_session_stub() -> None:
        ended_comic_sessions.append(True)

    def ingest_cbz_stub(*_args: object, **_kwargs: object) -> dict[str, object]:
        return {"work_id": "should-not-run"}

    def set_progress_stub(token: str, **kwargs: object) -> None:
        progress_events.append({"token": token, **kwargs})

    def render_upload_page_stub(_request: Any, response: ResponseLike, **_kwargs: object) -> ResponseLike:
        return response

    monkeypatch.setattr(module, "enforce_https_termination", enforce_https_termination_stub)
    monkeypatch.setattr(module, "validate_csrf", validate_csrf_stub)
    monkeypatch.setattr(module, "current_user", current_user_stub)
    monkeypatch.setattr(module, "validate_cbz_upload_policy", validate_cbz_upload_policy_stub)
    monkeypatch.setattr(module, "validate_saved_upload_size", validate_saved_upload_size_stub)
    monkeypatch.setattr(module, "begin_upload_session", begin_upload_session_stub)
    monkeypatch.setattr(module, "begin_comic_ingest_session", begin_comic_ingest_session_stub)
    monkeypatch.setattr(module, "end_upload_session", end_upload_session_stub)
    monkeypatch.setattr(module, "end_comic_ingest_session", end_comic_ingest_session_stub)
    monkeypatch.setattr(module, "ingest_cbz", ingest_cbz_stub)
    monkeypatch.setattr(module, "set_progress", set_progress_stub)
    monkeypatch.setattr(module, "render_upload_page", render_upload_page_stub)
    monkeypatch.setattr(module.threading, "Thread", ImmediateThread)

    request = dummy_request(
        path="/comic/upload",
        method="POST",
        form={
            "action": "ingest",
            "agree_terms": "on",
            "upload_token": "tok-timeout",
        },
        files={
            "cbz": DummyUpload("sample.cbz", b"PK\x03\x04dummy"),
        },
    )
    response = dummy_response()

    result = module.main(request, response)

    assert result.status_code == 200
    assert ended_upload_users == ["alice"]
    assert ended_comic_sessions == []

    throttled_events = [event for event in progress_events if str(event.get("stage", "")) == "throttled"]
    assert throttled_events
    assert throttled_events[-1].get("done") is True
    assert throttled_events[-1].get("ok") is False
