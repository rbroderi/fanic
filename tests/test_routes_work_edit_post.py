from __future__ import annotations

from collections.abc import Callable
from types import ModuleType
from typing import Any
from typing import Protocol

import pytest


class ResponseLike(Protocol):
    status_code: int
    content_type: str
    headers: dict[str, str]

    def set_data(self, data: str | bytes) -> None: ...


def test_non_admin_cannot_lower_explicit_rating(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/works.ex.post.py",
        "fanicsite_works_edit_post_explicit_lock_test",
    )

    def fake_enforce_https_termination(request: Any) -> bool:
        _ = request
        return True

    def fake_validate_csrf(request: Any) -> bool:
        _ = request
        return True

    def fake_get_work(work_id: str) -> dict[str, Any] | None:
        _ = work_id
        return {
            "id": "work-1",
            "title": "Locked Rating",
            "summary": "",
            "rating": "Explicit",
            "warnings": "",
            "status": "in_progress",
            "language": "en",
            "uploader_username": "alice",
        }

    def fake_current_user(request: Any) -> str:
        _ = request
        return "alice"

    def fake_can_view_work(username: str | None, work: dict[str, Any]) -> bool:
        _ = (username, work)
        return True

    called: dict[str, bool] = {"updated": False, "snapshotted": False}

    def fake_update_work_metadata(
        work_id: str,
        metadata: dict[str, object],
        *,
        editor_username: str,
        edited_by_admin: bool,
    ) -> None:
        _ = (work_id, metadata, editor_username, edited_by_admin)
        called["updated"] = True

    def fake_create_work_version_snapshot(
        work_id: str,
        *,
        action: str,
        actor: str,
        details: dict[str, object],
    ) -> object:
        _ = (work_id, action, actor, details)
        called["snapshotted"] = True
        return {}

    monkeypatch.setattr(
        module, "enforce_https_termination", fake_enforce_https_termination
    )
    monkeypatch.setattr(module, "validate_csrf", fake_validate_csrf)
    monkeypatch.setattr(module, "get_work", fake_get_work)
    monkeypatch.setattr(module, "current_user", fake_current_user)
    monkeypatch.setattr(module, "can_view_work", fake_can_view_work)
    monkeypatch.setattr(module, "update_work_metadata", fake_update_work_metadata)
    monkeypatch.setattr(
        module,
        "create_work_version_snapshot",
        fake_create_work_version_snapshot,
    )

    request = dummy_request(
        path="/works/work-1/edit",
        method="POST",
        form={
            "title": "Locked Rating",
            "rating": "Mature",
            "status": "in_progress",
            "summary": "",
            "warnings": "",
            "language": "en",
            "series": "",
            "series_index": "",
            "published_at": "",
            "fandoms": "",
            "relationships": "",
            "characters": "",
            "freeform_tags": "",
        },
    )
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 303
    assert result.headers["Location"] == "/works/work-1/edit?msg=explicit-rating-locked"
    assert called["updated"] is False
    assert called["snapshotted"] is False


def test_admin_can_lower_explicit_rating(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/works.ex.post.py",
        "fanicsite_works_edit_post_explicit_admin_test",
    )

    def fake_enforce_https_termination(request: Any) -> bool:
        _ = request
        return True

    def fake_validate_csrf(request: Any) -> bool:
        _ = request
        return True

    def fake_get_work(work_id: str) -> dict[str, Any] | None:
        _ = work_id
        return {
            "id": "work-1",
            "title": "Editable",
            "summary": "",
            "rating": "Explicit",
            "warnings": "",
            "status": "in_progress",
            "language": "en",
            "uploader_username": "alice",
        }

    def fake_current_user(request: Any) -> str:
        _ = request
        return str(module.ADMIN_USERNAME)

    def fake_can_view_work(username: str | None, work: dict[str, Any]) -> bool:
        _ = (username, work)
        return True

    captured: dict[str, object] = {}

    def fake_update_work_metadata(
        work_id: str,
        metadata: dict[str, object],
        *,
        editor_username: str,
        edited_by_admin: bool,
    ) -> None:
        captured["work_id"] = work_id
        captured["rating"] = metadata.get("rating")
        captured["editor_username"] = editor_username
        captured["edited_by_admin"] = edited_by_admin

    def fake_create_work_version_snapshot(
        work_id: str,
        *,
        action: str,
        actor: str,
        details: dict[str, object],
    ) -> object:
        captured["snapshot_work_id"] = work_id
        captured["snapshot_action"] = action
        captured["snapshot_actor"] = actor
        captured["snapshot_details"] = details
        return {}

    monkeypatch.setattr(
        module, "enforce_https_termination", fake_enforce_https_termination
    )
    monkeypatch.setattr(module, "validate_csrf", fake_validate_csrf)
    monkeypatch.setattr(module, "get_work", fake_get_work)
    monkeypatch.setattr(module, "current_user", fake_current_user)
    monkeypatch.setattr(module, "can_view_work", fake_can_view_work)
    monkeypatch.setattr(module, "update_work_metadata", fake_update_work_metadata)
    monkeypatch.setattr(
        module,
        "create_work_version_snapshot",
        fake_create_work_version_snapshot,
    )

    request = dummy_request(
        path="/works/work-1/edit",
        method="POST",
        form={
            "title": "Editable",
            "rating": "Mature",
            "status": "in_progress",
            "summary": "",
            "warnings": "",
            "language": "en",
            "series": "",
            "series_index": "",
            "published_at": "",
            "fandoms": "",
            "relationships": "",
            "characters": "",
            "freeform_tags": "",
        },
    )
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 303
    assert result.headers["Location"] == "/works/work-1/edit?msg=saved"
    assert captured["work_id"] == "work-1"
    assert captured["rating"] == "Mature"
    assert captured["edited_by_admin"] is True
    assert captured["snapshot_action"] == "metadata-edit"
