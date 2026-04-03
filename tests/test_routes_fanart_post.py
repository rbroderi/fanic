# pyright: reportUnknownLambdaType=false, reportUnknownArgumentType=false

from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any
from typing import Protocol
from typing import final

import pytest


class ResponseLike(Protocol):
    status_code: int
    content_type: str
    headers: dict[str, str]

    def set_data(self, data: str | bytes) -> None: ...


@final
class _UploadStub:
    def __init__(self, filename: str = "image.png") -> None:
        self.filename: str = filename

    def save(self, dst: str | Path) -> None:
        Path(dst).write_bytes(b"png")


def _owner_profile_key(username: str) -> str:
    return username


def _always_true(*_args: object, **_kwargs: object) -> bool:
    return True


def _always_none(*_args: object, **_kwargs: object) -> None:
    return None


def _rate_limit_ok(*_args: object, **_kwargs: object) -> int:
    return 0


def _current_user_alice(*_args: object, **_kwargs: object) -> str:
    return "alice"


def _current_user_bob(*_args: object, **_kwargs: object) -> str:
    return "bob"


def _current_user_admin(*_args: object, **_kwargs: object) -> str:
    return "admin-user"


def _current_user_none(*_args: object, **_kwargs: object) -> None:
    return None


def _role_user(*_args: object, **_kwargs: object) -> str:
    return "user"


def _role_admin(*_args: object, **_kwargs: object) -> str:
    return "admin"


def _role_superadmin(*_args: object, **_kwargs: object) -> str:
    return "superadmin"


def _patch_owner_profile_as_username(monkeypatch: pytest.MonkeyPatch, module: ModuleType) -> None:
    monkeypatch.setattr(module, "owner_profile_key", _owner_profile_key)


def test_fanart_delete_requires_admin_role(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/fanart.ex.post.py",
        "fanicsite_fanart_ex_post_forbidden_test",
    )

    monkeypatch.setattr(module, "enforce_https_termination", _always_true)
    monkeypatch.setattr(module, "validate_csrf", _always_true)
    monkeypatch.setattr(module, "current_user", _current_user_alice)
    monkeypatch.setattr(module, "role_for_user", _role_user)

    request = dummy_request(path="/fanart/alice/fanart-1/delete", method="POST")
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 403


def test_fanart_delete_admin_redirects_to_gallery(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/fanart.ex.post.py",
        "fanicsite_fanart_ex_post_delete_test",
    )

    monkeypatch.setattr(module, "enforce_https_termination", _always_true)
    monkeypatch.setattr(module, "validate_csrf", _always_true)
    monkeypatch.setattr(module, "current_user", _current_user_admin)
    monkeypatch.setattr(module, "role_for_user", _role_admin)
    monkeypatch.setattr(
        module,
        "get_fanart_item",
        lambda *_: {"id": "fanart-1", "uploader_username": "alice"},
    )
    monkeypatch.setattr(module, "delete_fanart_item", lambda *_: True)
    _patch_owner_profile_as_username(monkeypatch, module)

    request = dummy_request(path="/fanart/alice/fanart-1/delete", method="POST")
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 303
    assert result.headers["Location"] == "/fanart/alice?msg=deleted"


def test_fanart_delete_admin_redirects_to_safe_next_target(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/fanart.ex.post.py",
        "fanicsite_fanart_ex_post_delete_next_test",
    )

    monkeypatch.setattr(module, "enforce_https_termination", _always_true)
    monkeypatch.setattr(module, "validate_csrf", _always_true)
    monkeypatch.setattr(module, "current_user", _current_user_admin)
    monkeypatch.setattr(module, "role_for_user", _role_superadmin)
    monkeypatch.setattr(
        module,
        "get_fanart_item",
        lambda *_: {"id": "fanart-1", "uploader_username": "alice"},
    )
    monkeypatch.setattr(module, "delete_fanart_item", lambda *_: True)

    request = dummy_request(
        path="/fanart/alice/fanart-1/delete",
        method="POST",
        args={"next": "/?view=fanart"},
    )
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 303
    assert result.headers["Location"] == "/?view=fanart"


def test_fanart_upload_redirects_with_rating_elevated_message(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/fanart/upload.ex.post.py",
        "fanicsite_fanart_upload_ex_post_upload_moderation_test",
    )

    monkeypatch.setattr(module, "enforce_https_termination", _always_true)
    monkeypatch.setattr(module, "validate_csrf", _always_true)
    monkeypatch.setattr(module, "check_post_rate_limit", _rate_limit_ok)
    monkeypatch.setattr(module, "current_user", _current_user_alice)
    monkeypatch.setattr(module, "validate_page_upload_policy", _always_none)
    monkeypatch.setattr(module, "validate_saved_upload_size", _always_none)
    monkeypatch.setattr(module, "validate_field_lengths", lambda *_args, **_kwargs: "")
    monkeypatch.setattr(
        module,
        "ingest_fanart_image",
        lambda *_args, **_kwargs: {
            "item_id": "fanart-1",
            "rating_before": "Teen And Up Audiences",
            "rating_after": "Explicit",
            "rating_auto_elevated": True,
        },
    )
    monkeypatch.setattr(module, "get_local_user", _always_none)

    request = dummy_request(
        path="/fanart/upload",
        method="POST",
        form={
            "agree_terms": "on",
            "title": "Skyline",
            "summary": "Study",
            "fandom": "Skyverse",
            "rating": "Teen And Up Audiences",
        },
        files={"fanart_image": _UploadStub()},
    )
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 303
    assert result.headers["Location"] == "/fanart/alice?msg=uploaded-rating-elevated"


def test_fanart_gallery_create_requires_owner(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/fanart.ex.post.py",
        "fanicsite_fanart_ex_post_gallery_create_forbidden_test",
    )

    monkeypatch.setattr(module, "enforce_https_termination", _always_true)
    monkeypatch.setattr(module, "validate_csrf", _always_true)
    monkeypatch.setattr(module, "current_user", _current_user_bob)
    monkeypatch.setattr(module, "role_for_user", _role_user)

    request = dummy_request(
        path="/fanart/alice/galleries/create",
        method="POST",
        form={"gallery_name": "Sketches"},
    )
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 403


def test_fanart_gallery_create_redirects_to_new_gallery(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/fanart.ex.post.py",
        "fanicsite_fanart_ex_post_gallery_create_test",
    )

    monkeypatch.setattr(module, "enforce_https_termination", _always_true)
    monkeypatch.setattr(module, "validate_csrf", _always_true)
    monkeypatch.setattr(module, "current_user", _current_user_alice)
    monkeypatch.setattr(module, "role_for_user", _role_user)
    monkeypatch.setattr(
        module,
        "create_fanart_gallery",
        lambda **_kwargs: {
            "id": "gallery-1",
            "uploader_username": "alice",
            "name": "Sketches",
            "slug": "sketches",
            "description": "",
            "item_count": 0,
            "created_at": "",
            "updated_at": "",
        },
    )
    _patch_owner_profile_as_username(monkeypatch, module)

    request = dummy_request(
        path="/fanart/alice/galleries/create",
        method="POST",
        form={"gallery_name": "Sketches", "gallery_description": "Warmups"},
    )
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 303
    assert result.headers["Location"] == "/fanart/alice?gallery=sketches&msg=gallery-created"


def test_fanart_gallery_update_items_redirects_with_success(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/fanart.ex.post.py",
        "fanicsite_fanart_ex_post_gallery_update_items_test",
    )

    monkeypatch.setattr(module, "enforce_https_termination", lambda *_: True)
    monkeypatch.setattr(module, "validate_csrf", lambda *_: True)
    monkeypatch.setattr(module, "current_user", lambda *_: "alice")
    monkeypatch.setattr(module, "role_for_user", lambda *_: "user")
    monkeypatch.setattr(module, "resolve_owner_username", lambda *_: "alice")
    monkeypatch.setattr(
        module,
        "get_fanart_gallery_by_slug",
        lambda *_: {
            "id": "gallery-1",
            "uploader_username": "alice",
            "name": "Sketches",
            "slug": "sketches",
            "description": "",
            "item_count": 0,
            "created_at": "",
            "updated_at": "",
        },
    )

    captured: dict[str, object] = {}

    def fake_replace_fanart_gallery_items(**kwargs: object) -> int:
        captured.update(kwargs)
        return 1

    monkeypatch.setattr(module, "replace_fanart_gallery_items", fake_replace_fanart_gallery_items)
    _patch_owner_profile_as_username(monkeypatch, module)

    request = dummy_request(
        path="/fanart/alice/galleries/update-items",
        method="POST",
        form={"gallery_slug": "sketches", "gallery_item_id": "art-1,art-2"},
    )
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 303
    assert result.headers["Location"] == "/fanart/alice?gallery=sketches&msg=gallery-updated"
    assert captured["uploader_username"] == "alice"
    assert captured["gallery_id"] == "gallery-1"
    assert captured["fanart_item_ids"] == ["art-1", "art-2"]


def test_fanart_gallery_delete_requires_owner(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: Any,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/fanart.ex.post.py",
        "fanicsite_fanart_ex_post_gallery_delete_forbidden_test",
    )

    monkeypatch.setattr(module, "enforce_https_termination", _always_true)
    monkeypatch.setattr(module, "validate_csrf", _always_true)
    monkeypatch.setattr(module, "current_user", _current_user_bob)
    monkeypatch.setattr(module, "role_for_user", _role_user)

    request = dummy_request(
        path="/fanart/alice/galleries/delete",
        method="POST",
        form={"gallery_slug": "sketches"},
    )
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 403


def test_fanart_gallery_delete_redirects_to_gallery_root(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/fanart.ex.post.py",
        "fanicsite_fanart_ex_post_gallery_delete_test",
    )

    monkeypatch.setattr(module, "enforce_https_termination", _always_true)
    monkeypatch.setattr(module, "validate_csrf", _always_true)
    monkeypatch.setattr(module, "current_user", _current_user_alice)
    monkeypatch.setattr(module, "role_for_user", _role_user)
    monkeypatch.setattr(module, "resolve_owner_username", lambda *_: "alice")
    monkeypatch.setattr(
        module,
        "get_fanart_gallery_by_slug",
        lambda *_: {
            "id": "gallery-1",
            "uploader_username": "alice",
            "name": "Sketches",
            "slug": "sketches",
            "description": "",
            "item_count": 2,
            "created_at": "",
            "updated_at": "",
        },
    )

    captured: dict[str, object] = {}

    def fake_delete_fanart_gallery(**kwargs: object) -> bool:
        captured.update(kwargs)
        return True

    monkeypatch.setattr(module, "delete_fanart_gallery", fake_delete_fanart_gallery)
    _patch_owner_profile_as_username(monkeypatch, module)

    request = dummy_request(
        path="/fanart/alice/galleries/delete",
        method="POST",
        form={"gallery_slug": "sketches"},
    )
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 303
    assert result.headers["Location"] == "/fanart/alice?msg=gallery-deleted"
    assert captured["uploader_username"] == "alice"
    assert captured["gallery_id"] == "gallery-1"


def test_fanart_gallery_delete_admin_can_delete_for_owner(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/fanart.ex.post.py",
        "fanicsite_fanart_ex_post_gallery_delete_admin_test",
    )

    monkeypatch.setattr(module, "enforce_https_termination", _always_true)
    monkeypatch.setattr(module, "validate_csrf", _always_true)
    monkeypatch.setattr(module, "current_user", _current_user_admin)
    monkeypatch.setattr(module, "role_for_user", _role_admin)
    monkeypatch.setattr(module, "resolve_owner_username", lambda *_: "alice")
    monkeypatch.setattr(
        module,
        "get_fanart_gallery_by_slug",
        lambda *_: {
            "id": "gallery-1",
            "uploader_username": "alice",
            "name": "Sketches",
            "slug": "sketches",
            "description": "",
            "item_count": 2,
            "created_at": "",
            "updated_at": "",
        },
    )

    captured: dict[str, object] = {}

    def fake_delete_fanart_gallery(**kwargs: object) -> bool:
        captured.update(kwargs)
        return True

    monkeypatch.setattr(module, "delete_fanart_gallery", fake_delete_fanart_gallery)
    _patch_owner_profile_as_username(monkeypatch, module)

    request = dummy_request(
        path="/fanart/alice/galleries/delete",
        method="POST",
        form={"gallery_slug": "sketches"},
    )
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 303
    assert result.headers["Location"] == "/fanart/alice?msg=gallery-deleted"
    assert captured["uploader_username"] == "alice"
    assert captured["gallery_id"] == "gallery-1"


def test_fanart_reader_comment_requires_login(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/fanart.ex.post.py",
        "fanicsite_fanart_ex_post_reader_comment_login_test",
    )

    monkeypatch.setattr(module, "enforce_https_termination", _always_true)
    monkeypatch.setattr(module, "validate_csrf", _always_true)
    monkeypatch.setattr(module, "resolve_owner_username", lambda *_: "alice")
    monkeypatch.setattr(module, "current_user", _current_user_none)

    request = dummy_request(
        path="/fanart/alice/reader/comments",
        method="POST",
        form={
            "fanart_item_id": "art-1",
            "comment_body": "Nice",
            "next": "/fanart/alice/reader?item_id=art-1",
        },
    )
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 303
    assert result.headers["Location"] == "/fanart/alice/reader?item_id=art-1&msg=login-required"


def test_fanart_reader_comment_rejects_empty_body(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/fanart.ex.post.py",
        "fanicsite_fanart_ex_post_reader_comment_empty_test",
    )

    monkeypatch.setattr(module, "enforce_https_termination", _always_true)
    monkeypatch.setattr(module, "validate_csrf", _always_true)
    monkeypatch.setattr(module, "resolve_owner_username", lambda *_: "alice")
    monkeypatch.setattr(module, "current_user", _current_user_bob)
    monkeypatch.setattr(
        module,
        "get_fanart_item",
        lambda *_: {
            "id": "art-1",
            "uploader_username": "alice",
        },
    )

    request = dummy_request(
        path="/fanart/alice/reader/comments",
        method="POST",
        form={
            "fanart_item_id": "art-1",
            "comment_body": "   ",
            "next": "/fanart/alice/reader?item_id=art-1",
        },
    )
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 303
    assert result.headers["Location"] == "/fanart/alice/reader?item_id=art-1&msg=comment-empty"


def test_fanart_reader_comment_redirects_with_success(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/fanart.ex.post.py",
        "fanicsite_fanart_ex_post_reader_comment_success_test",
    )

    monkeypatch.setattr(module, "enforce_https_termination", _always_true)
    monkeypatch.setattr(module, "validate_csrf", _always_true)
    monkeypatch.setattr(module, "resolve_owner_username", lambda *_: "alice")
    monkeypatch.setattr(module, "current_user", _current_user_bob)
    monkeypatch.setattr(
        module,
        "get_fanart_item",
        lambda *_: {
            "id": "art-1",
            "uploader_username": "alice",
        },
    )

    captured: dict[str, str] = {}

    def fake_add_fanart_comment(item_id: str, username: str, body: str) -> dict[str, str]:
        captured["item_id"] = item_id
        captured["username"] = username
        captured["body"] = body
        return {"id": "comment-1"}

    monkeypatch.setattr(module, "add_fanart_comment", fake_add_fanart_comment)

    request = dummy_request(
        path="/fanart/alice/reader/comments",
        method="POST",
        form={
            "fanart_item_id": "art-1",
            "comment_body": "Great shot",
            "next": "/fanart/alice/reader?item_id=art-1",
        },
    )
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 303
    assert result.headers["Location"] == "/fanart/alice/reader?item_id=art-1&msg=comment-saved"
    assert captured == {
        "item_id": "art-1",
        "username": "bob",
        "body": "Great shot",
    }
