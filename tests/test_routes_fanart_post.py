from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

from conftest import DummyResponse as ResponseLike


class _UploadStub:
    def __init__(self, filename: str = "image.png") -> None:
        self.filename = filename

    def save(self, dst: str | Path) -> None:
        Path(dst).write_bytes(b"png")


def test_fanart_delete_requires_admin_role(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: Any,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/fanart.ex.post.py",
        "fanicsite_fanart_ex_post_forbidden_test",
    )

    monkeypatch.setattr(module, "enforce_https_termination", lambda *_: True)
    monkeypatch.setattr(module, "validate_csrf", lambda *_: True)
    monkeypatch.setattr(module, "current_user", lambda *_: "alice")
    monkeypatch.setattr(module, "role_for_user", lambda *_: "user")

    request = dummy_request(path="/fanart/alice/fanart-1/delete", method="POST")
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 403


def test_fanart_delete_admin_redirects_to_gallery(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: Any,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/fanart.ex.post.py",
        "fanicsite_fanart_ex_post_delete_test",
    )

    monkeypatch.setattr(module, "enforce_https_termination", lambda *_: True)
    monkeypatch.setattr(module, "validate_csrf", lambda *_: True)
    monkeypatch.setattr(module, "current_user", lambda *_: "admin-user")
    monkeypatch.setattr(module, "role_for_user", lambda *_: "admin")
    monkeypatch.setattr(
        module,
        "get_fanart_item",
        lambda *_: {"id": "fanart-1", "uploader_username": "alice"},
    )
    monkeypatch.setattr(module, "delete_fanart_item", lambda *_: True)

    request = dummy_request(path="/fanart/alice/fanart-1/delete", method="POST")
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 303
    assert result.headers["Location"] == "/fanart/alice?msg=deleted"


def test_fanart_upload_redirects_with_rating_elevated_message(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: Any,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/fanart.ex.post.py",
        "fanicsite_fanart_ex_post_upload_moderation_test",
    )

    monkeypatch.setattr(module, "enforce_https_termination", lambda *_: True)
    monkeypatch.setattr(module, "validate_csrf", lambda *_: True)
    monkeypatch.setattr(module, "check_post_rate_limit", lambda *_: 0)
    monkeypatch.setattr(module, "current_user", lambda *_: "alice")
    monkeypatch.setattr(module, "validate_page_upload_policy", lambda *_: None)
    monkeypatch.setattr(module, "validate_saved_upload_size", lambda *_: None)
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
