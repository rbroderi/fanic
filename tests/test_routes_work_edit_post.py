# pyright: reportUnknownLambdaType=false, reportUnknownArgumentType=false

from collections.abc import Callable
from types import ModuleType
from typing import Any
from typing import Protocol


class ResponseLike(Protocol):
    status_code: int
    content_type: str
    headers: dict[str, str]

    def set_data(self, data: str | bytes) -> None: ...


def _always_https(req: Any, res: Any) -> bool:
    _ = (req, res)
    return True


def _always_valid_csrf(req: Any) -> bool:
    _ = req
    return True


def _role_user(_: str | None) -> str:
    return "user"


def _role_admin(_: str | None) -> str:
    return "admin"


def _can_view_work(_username: str | None, _work: dict[str, object]) -> bool:
    return True


def _delete_work_ok(_work_id: str) -> bool:
    return True


def _add_work_kudo(_work_id: str, _username: str) -> bool:
    return True


def _add_work_comment(
    _work_id: str,
    _username: str,
    _body: str,
    chapter_number: int | None = None,
) -> object:
    _ = chapter_number
    return {"id": "comment-1"}


def _create_notification(
    _username: str,
    *,
    actor_username: str,
    work_id: str | None,
    kind: str,
    message: str,
    href: str,
) -> int:
    _ = (actor_username, work_id, kind, message, href)
    return 1


def _update_work_metadata(
    _work_id: str,
    _metadata: dict[str, object],
    *,
    editor_username: str,
    edited_by_admin: bool,
) -> None:
    _ = (editor_username, edited_by_admin)


def _create_work_version_snapshot(
    _work_id: str,
    *,
    action: str,
    actor: str,
    details: dict[str, object],
) -> object:
    _ = (action, actor, details)
    return {}


def _comic_post_deps(
    module: ModuleType,
    *,
    get_work_func: Callable[[str], dict[str, object] | None],
    current_user_func: Callable[[Any], str | None],
    role_for_user_func: Callable[[str | None], str],
    can_view_work_func: Callable[[str | None, dict[str, object]], bool] = _can_view_work,
    delete_work_func: Callable[[str], bool] = _delete_work_ok,
    update_work_metadata_func: Callable[..., object] = _update_work_metadata,
    create_work_version_snapshot_func: Callable[..., object] = _create_work_version_snapshot,
) -> object:
    return module.ComicPostDependencies(
        route_tail=module.route_tail,
        enforce_https_termination=_always_https,
        validate_csrf=_always_valid_csrf,
        get_work=get_work_func,
        current_user=current_user_func,
        role_for_user=role_for_user_func,
        can_view_work=can_view_work_func,
        delete_work=delete_work_func,
        add_work_kudo=_add_work_kudo,
        add_work_comment=_add_work_comment,
        create_notification=_create_notification,
        update_work_metadata=update_work_metadata_func,
        create_work_version_snapshot=create_work_version_snapshot_func,
    )


def test_comic_delete_forbidden_for_non_admin(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/comic.ex.post.py",
        "fanicsite_comic_ex_post_delete_forbidden_test",
    )

    deps = _comic_post_deps(
        module,
        get_work_func=lambda *_: {
            "id": "work-1",
            "uploader_username": "alice",
            "rating": "General Audiences",
        },
        current_user_func=lambda *_: "alice",
        role_for_user_func=_role_user,
    )

    request = dummy_request(path="/comic/work-1/delete", method="POST")
    response = dummy_response()
    result = module.main(request, response, deps=deps)

    assert result.status_code == 403


def test_comic_delete_allows_admin(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/comic.ex.post.py",
        "fanicsite_comic_ex_post_delete_admin_test",
    )

    deps = _comic_post_deps(
        module,
        get_work_func=lambda *_: {
            "id": "work-1",
            "uploader_username": "alice",
            "rating": "General Audiences",
        },
        current_user_func=lambda *_: "admin",
        role_for_user_func=_role_admin,
        delete_work_func=_delete_work_ok,
    )

    request = dummy_request(path="/comic/work-1/delete", method="POST")
    response = dummy_response()
    result = module.main(request, response, deps=deps)

    assert result.status_code == 303
    assert result.headers["Location"] == "/"


def test_non_admin_cannot_lower_explicit_rating(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/comic.ex.post.py",
        "fanicsite_works_edit_post_explicit_lock_test",
    )

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

    deps = _comic_post_deps(
        module,
        get_work_func=fake_get_work,
        current_user_func=fake_current_user,
        role_for_user_func=_role_user,
        can_view_work_func=fake_can_view_work,
        update_work_metadata_func=fake_update_work_metadata,
        create_work_version_snapshot_func=fake_create_work_version_snapshot,
    )

    request = dummy_request(
        path="/comic/work-1/edit",
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
    result = module.main(request, response, deps=deps)

    assert result.status_code == 303
    assert result.headers["Location"] == "/comic/work-1/edit?msg=explicit-rating-locked"
    assert called["updated"] is False
    assert called["snapshotted"] is False


def test_admin_can_lower_explicit_rating(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/comic.ex.post.py",
        "fanicsite_works_edit_post_explicit_admin_test",
    )

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
        return "admin"

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

    deps = _comic_post_deps(
        module,
        get_work_func=fake_get_work,
        current_user_func=fake_current_user,
        role_for_user_func=_role_admin,
        can_view_work_func=fake_can_view_work,
        update_work_metadata_func=fake_update_work_metadata,
        create_work_version_snapshot_func=fake_create_work_version_snapshot,
    )

    request = dummy_request(
        path="/comic/work-1/edit",
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
    result = module.main(request, response, deps=deps)

    assert result.status_code == 303
    assert result.headers["Location"] == "/comic/work-1/edit?msg=saved"
    assert captured["work_id"] == "work-1"
    assert captured["rating"] == "Mature"
    assert captured["edited_by_admin"] is True
    assert captured["snapshot_action"] == "metadata-edit"
