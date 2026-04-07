from collections.abc import Callable
from dataclasses import dataclass
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


@dataclass(frozen=True, slots=True)
class UploadSessionStartStub:
    allowed: bool
    limit_code: str
    retry_after: int


@dataclass(frozen=True, slots=True)
class ComicIngestSessionStartStub:
    allowed: bool
    retry_after: int
    queue_position: int


def _always_https(_request: Any, _response: Any) -> bool:
    return True


def _always_valid_csrf(_request: Any) -> bool:
    return True


def _current_user_alice(_request: Any) -> str:
    return "alice"


def _validate_cbz_upload_policy_ok(_upload: object) -> str:
    return ""


def _validate_saved_upload_size_ok(_path: Path, _max_bytes: int, _label: str) -> str:
    return ""


def _validate_page_upload_policy_ok(_upload: object) -> str:
    return ""


def _ingest_editor_page_stub(**_kwargs: object) -> dict[str, object]:
    return {"work_id": "editor-work-1"}


def _editor_replace_page_image_stub(**_kwargs: object) -> dict[str, object]:
    return {"ok": True}


def _editor_delete_page_stub(**_kwargs: object) -> dict[str, object]:
    return {"ok": True}


def _editor_move_page_stub(**_kwargs: object) -> dict[str, object]:
    return {"ok": True}


def _editor_reorder_gallery_stub(**_kwargs: object) -> dict[str, object]:
    return {"ok": True}


def _editor_add_chapter_stub(**_kwargs: object) -> dict[str, object]:
    return {"ok": True}


def _editor_delete_chapter_stub(**_kwargs: object) -> bool:
    return True


def _editor_update_chapter_stub(**_kwargs: object) -> bool:
    return True


def _get_work_stub(_work_id: str) -> dict[str, object] | None:
    return None


def _list_work_page_rows_stub(_work_id: str) -> list[object]:
    return []


def _list_work_chapters_stub(_work_id: str) -> list[object]:
    return []


def _get_explicit_threshold_stub() -> float:
    return 0.5


def _admin_aware_detail(
    _request: Any,
    *,
    public_detail: str,
    exc: BaseException,
) -> str:
    _ = exc
    return public_detail


def _no_op_log_exception(
    _request: Any,
    *,
    code: str,
    exc: BaseException,
    message: str,
) -> None:
    _ = (code, exc, message)


def _comic_upload_post_deps(
    module: ModuleType,
    *,
    begin_upload_session_func: Callable[[str], UploadSessionStartStub],
    begin_comic_ingest_session_func: Callable[..., ComicIngestSessionStartStub],
    end_upload_session_func: Callable[[str], None],
    end_comic_ingest_session_func: Callable[[], None],
    ingest_cbz_func: Callable[..., dict[str, object]],
    set_progress_func: Callable[..., None],
    render_upload_page_func: Callable[..., ResponseLike],
    editor_add_chapter_func: Callable[..., object] = _editor_add_chapter_stub,
) -> object:
    return module.ComicUploadPostDependencies(
        request_id=module.request_id,
        text_error=module.text_error,
        enforce_https_termination=_always_https,
        validate_csrf=_always_valid_csrf,
        current_user=_current_user_alice,
        render_upload_page=render_upload_page_func,
        validate_cbz_upload_policy=_validate_cbz_upload_policy_ok,
        begin_upload_session=begin_upload_session_func,
        end_upload_session=end_upload_session_func,
        validate_saved_upload_size=_validate_saved_upload_size_ok,
        validate_page_upload_policy=_validate_page_upload_policy_ok,
        set_progress=set_progress_func,
        begin_comic_ingest_session=begin_comic_ingest_session_func,
        end_comic_ingest_session=end_comic_ingest_session_func,
        ingest_cbz=ingest_cbz_func,
        ingest_editor_page=_ingest_editor_page_stub,
        editor_replace_page_image=_editor_replace_page_image_stub,
        editor_delete_page=_editor_delete_page_stub,
        editor_move_page=_editor_move_page_stub,
        editor_reorder_gallery=_editor_reorder_gallery_stub,
        editor_add_chapter=editor_add_chapter_func,
        editor_delete_chapter=_editor_delete_chapter_stub,
        editor_update_chapter=_editor_update_chapter_stub,
        get_work=_get_work_stub,
        list_work_page_rows=_list_work_page_rows_stub,
        list_work_chapters=_list_work_chapters_stub,
        get_explicit_threshold=_get_explicit_threshold_stub,
        delete_tree=module.delete_tree,
        thread_factory=ImmediateThread,
        log_exception=_no_op_log_exception,
        admin_aware_detail=_admin_aware_detail,
    )


def test_comic_upload_post_runs_async_worker_and_sets_done_progress(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/comic/upload.ex.post.py",
        "fanicsite_comic_upload_ex_post_async_success_test",
    )

    progress_events: list[dict[str, object]] = []
    render_calls: list[dict[str, object]] = []
    ended_upload_users: list[str] = []
    ended_comic_sessions: list[bool] = []

    def begin_upload_session_stub(_username: str) -> UploadSessionStartStub:
        return UploadSessionStartStub(True, "", 0)

    def begin_comic_ingest_session_stub(on_queued: Any) -> ComicIngestSessionStartStub:
        _ = on_queued
        return ComicIngestSessionStartStub(True, 0, 0)

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

    deps = _comic_upload_post_deps(
        module,
        begin_upload_session_func=begin_upload_session_stub,
        begin_comic_ingest_session_func=begin_comic_ingest_session_stub,
        end_upload_session_func=end_upload_session_stub,
        end_comic_ingest_session_func=end_comic_ingest_session_stub,
        ingest_cbz_func=ingest_cbz_stub,
        set_progress_func=fake_set_progress,
        render_upload_page_func=fake_render_upload_page,
    )

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

    result = module.main(request, response, deps=deps)

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
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/comic/upload.ex.post.py",
        "fanicsite_comic_upload_ex_post_async_queue_timeout_test",
    )

    progress_events: list[dict[str, object]] = []
    ended_upload_users: list[str] = []
    ended_comic_sessions: list[bool] = []

    def begin_upload_session_stub(_username: str) -> UploadSessionStartStub:
        return UploadSessionStartStub(True, "", 0)

    def begin_comic_ingest_session_stub(on_queued: Any) -> ComicIngestSessionStartStub:
        _ = on_queued
        return ComicIngestSessionStartStub(False, 0, 2)

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

    deps = _comic_upload_post_deps(
        module,
        begin_upload_session_func=begin_upload_session_stub,
        begin_comic_ingest_session_func=begin_comic_ingest_session_stub,
        end_upload_session_func=end_upload_session_stub,
        end_comic_ingest_session_func=end_comic_ingest_session_stub,
        ingest_cbz_func=ingest_cbz_stub,
        set_progress_func=set_progress_stub,
        render_upload_page_func=render_upload_page_stub,
    )

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

    result = module.main(request, response, deps=deps)

    assert result.status_code == 200
    assert ended_upload_users == ["alice"]
    assert ended_comic_sessions == []

    throttled_events = [event for event in progress_events if str(event.get("stage", "")) == "throttled"]
    assert throttled_events
    assert throttled_events[-1].get("done") is True
    assert throttled_events[-1].get("ok") is False


def test_comic_upload_post_async_worker_reports_blocked_stats_for_admin(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/comic/upload.ex.post.py",
        "fanicsite_comic_upload_ex_post_async_blocked_admin_stats_test",
    )

    progress_events: list[dict[str, object]] = []

    def begin_upload_session_stub(_username: str) -> UploadSessionStartStub:
        return UploadSessionStartStub(True, "", 0)

    def begin_comic_ingest_session_stub(on_queued: Any) -> ComicIngestSessionStartStub:
        _ = on_queued
        return ComicIngestSessionStartStub(True, 0, 0)

    def end_upload_session_stub(_username: str) -> None:
        return None

    def end_comic_ingest_session_stub() -> None:
        return None

    def ingest_cbz_blocked(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise module.ModerationBlockedError(
            {
                "allow": False,
                "source_member": "001.png",
                "style": "photorealistic",
                "nsfw_score": 0.93,
                "reasons": ["style:photorealistic", "explicit:0.93"],
            }
        )

    def set_progress_stub(token: str, **kwargs: object) -> None:
        progress_events.append({"token": token, **kwargs})

    def render_upload_page_stub(_request: Any, response: ResponseLike, **_kwargs: object) -> ResponseLike:
        response.status_code = 200
        response.content_type = "text/html; charset=utf-8"
        response.set_data("ok")
        return response

    def admin_aware_detail_stub(
        _request: Any,
        *,
        public_detail: str,
        exc: BaseException,
    ) -> str:
        _ = public_detail
        return str(exc)

    deps = module.ComicUploadPostDependencies(
        request_id=module.request_id,
        text_error=module.text_error,
        enforce_https_termination=_always_https,
        validate_csrf=_always_valid_csrf,
        current_user=_current_user_alice,
        render_upload_page=render_upload_page_stub,
        validate_cbz_upload_policy=_validate_cbz_upload_policy_ok,
        begin_upload_session=begin_upload_session_stub,
        end_upload_session=end_upload_session_stub,
        validate_saved_upload_size=_validate_saved_upload_size_ok,
        validate_page_upload_policy=_validate_page_upload_policy_ok,
        set_progress=set_progress_stub,
        begin_comic_ingest_session=begin_comic_ingest_session_stub,
        end_comic_ingest_session=end_comic_ingest_session_stub,
        ingest_cbz=ingest_cbz_blocked,
        ingest_editor_page=_ingest_editor_page_stub,
        editor_replace_page_image=_editor_replace_page_image_stub,
        editor_delete_page=_editor_delete_page_stub,
        editor_move_page=_editor_move_page_stub,
        editor_reorder_gallery=_editor_reorder_gallery_stub,
        editor_add_chapter=_editor_add_chapter_stub,
        editor_delete_chapter=_editor_delete_chapter_stub,
        editor_update_chapter=_editor_update_chapter_stub,
        get_work=_get_work_stub,
        list_work_page_rows=_list_work_page_rows_stub,
        list_work_chapters=_list_work_chapters_stub,
        get_explicit_threshold=_get_explicit_threshold_stub,
        delete_tree=module.delete_tree,
        thread_factory=ImmediateThread,
        log_exception=_no_op_log_exception,
        admin_aware_detail=admin_aware_detail_stub,
    )

    request = dummy_request(
        path="/comic/upload",
        method="POST",
        form={
            "action": "ingest",
            "agree_terms": "on",
            "upload_token": "tok-blocked-admin",
        },
        files={
            "cbz": DummyUpload("sample.cbz", b"PK\\x03\\x04dummy"),
        },
    )
    response = dummy_response()

    result = module.main(request, response, deps=deps)

    assert result.status_code == 200
    blocked_events = [event for event in progress_events if str(event.get("stage", "")) == "blocked"]
    assert blocked_events
    blocked_message = str(blocked_events[-1].get("message", ""))
    assert "CBZ import blocked by moderation policy (001.png)." in blocked_message
    assert "stats={" in blocked_message
    assert '"nsfw_score": 0.93' in blocked_message


def test_comic_upload_post_editor_add_chapter_uses_injected_dependency(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/comic/upload.ex.post.py",
        "fanicsite_comic_upload_ex_post_editor_add_chapter_deps_test",
    )

    captured: dict[str, object] = {}
    render_calls: list[dict[str, object]] = []

    def begin_upload_session_stub(_username: str) -> UploadSessionStartStub:
        return UploadSessionStartStub(True, "", 0)

    def begin_comic_ingest_session_stub(on_queued: Any) -> ComicIngestSessionStartStub:
        _ = on_queued
        return ComicIngestSessionStartStub(True, 0, 0)

    def end_upload_session_stub(_username: str) -> None:
        return None

    def end_comic_ingest_session_stub() -> None:
        return None

    def ingest_cbz_stub(*_args: object, **_kwargs: object) -> dict[str, object]:
        return {"work_id": "unused"}

    def set_progress_stub(_token: str, **_kwargs: object) -> None:
        return None

    def editor_add_chapter_stub(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {"id": "chapter-9", "ok": True}

    def render_upload_page_stub(
        _request: Any,
        response: ResponseLike,
        **kwargs: object,
    ) -> ResponseLike:
        render_calls.append(dict(kwargs))
        response.status_code = 200
        response.content_type = "text/html; charset=utf-8"
        response.set_data("ok")
        return response

    deps = _comic_upload_post_deps(
        module,
        begin_upload_session_func=begin_upload_session_stub,
        begin_comic_ingest_session_func=begin_comic_ingest_session_stub,
        end_upload_session_func=end_upload_session_stub,
        end_comic_ingest_session_func=end_comic_ingest_session_stub,
        ingest_cbz_func=ingest_cbz_stub,
        set_progress_func=set_progress_stub,
        render_upload_page_func=render_upload_page_stub,
        editor_add_chapter_func=editor_add_chapter_stub,
    )

    request = dummy_request(
        path="/comic/upload",
        method="POST",
        form={
            "action": "editor-add-chapter",
            "agree_terms": "on",
            "editor_work_id": "work-42",
            "editor_title": "Draft",
            "editor_summary": "Summary",
            "chapter_title": "Act One",
            "chapter_start_page": "1",
            "chapter_end_page": "3",
        },
    )
    response = dummy_response()

    result = module.main(request, response, deps=deps)

    assert result.status_code == 200
    assert captured["work_id"] == "work-42"
    assert captured["title"] == "Act One"
    assert captured["start_page"] == 1
    assert captured["end_page"] == 3
    assert captured["uploader_username"] == "alice"
    assert render_calls
    assert render_calls[-1]["upload_status_kind"] == "success"
    assert render_calls[-1]["upload_status_text"] == "Chapter added."
