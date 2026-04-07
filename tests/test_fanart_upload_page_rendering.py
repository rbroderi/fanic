from collections.abc import Callable
from types import ModuleType
from typing import Any
from typing import Protocol
from typing import runtime_checkable

import pytest

from fanic.settings import static_asset_url


def _current_user_admin(_request: object) -> str:
    return "admin-user"


def _role_admin(_username: object) -> str:
    return "admin"


@runtime_checkable
class ResponseLike(Protocol):
    status_code: int
    content_type: str
    headers: dict[str, str]
    data: bytes

    def set_data(self, data: str | bytes) -> None: ...

    def set_cookie(self, key: str, value: str, **kwargs: Any) -> None: ...

    def delete_cookie(self, key: str, **kwargs: Any) -> None: ...


def test_fanart_upload_get_accepts_trailing_slash(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], Any],
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/fanart/upload.ex.get.py",
        "fanicsite_fanart_upload_ex_get_trailing_slash_test",
    )

    request = dummy_request(path="/fanart/upload/", args={})
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 200


def test_fanart_upload_page_renders_fandom_autocomplete(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], Any],
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/fanart/upload.ex.get.py",
        "fanicsite_fanart_upload_ex_get_autocomplete_test",
    )

    request = dummy_request(path="/fanart/upload", args={})
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 200
    html = response.data.decode("utf-8")
    assert 'data-tag-autocomplete="1"' in html
    assert 'data-tag-type="fandom"' in html
    assert 'data-tag-chips="1"' in html
    assert 'name="fandom"' in html
    assert 'name="tags"' in html
    assert 'data-tag-type="freeform"' in html
    assert 'autocomplete="off"' in html
    assert 'name="upload_token"' in html
    assert 'id="fanartUploadProgressWrap"' in html
    assert 'id="fanartUploadProgressBar"' in html
    assert 'id="fanartUploadProgressText"' in html
    assert '<datalist id="fandomSuggestions">' in html
    assert '<datalist id="freeformSuggestions">' in html
    assert f'<script src="{static_asset_url("tag-autocomplete", "js")}"></script>' in html
    assert f'<script src="{static_asset_url("fanart-upload-progress", "js")}"></script>' in html


def test_fanart_upload_page_renders_admin_moderation_stats_block(
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fanic.cylinder_sites.fanicsite.fanart import upload_page

    monkeypatch.setattr(upload_page, "current_user", _current_user_admin)
    monkeypatch.setattr(upload_page, "role_for_user", _role_admin)

    request = dummy_request(
        path="/fanart/upload",
        args={
            "msg": "blocked",
            "moderation_detail": '{"allow": false, "nsfw_score": 0.83, "style": "photorealistic"}',
        },
    )
    response = dummy_response()
    result = upload_page.render_upload_page(request, response)

    assert result.status_code == 200
    html = response.data.decode("utf-8")
    assert "Moderation stats (admin)" in html
    assert 'class="code-block"' in html
    assert "&quot;allow&quot;: false" in html
    assert "&quot;nsfw_score&quot;: 0.83" in html
    assert "&quot;style&quot;: &quot;photorealistic&quot;" in html
