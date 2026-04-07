# pyright: reportUnknownLambdaType=false, reportUnknownArgumentType=false
from collections.abc import Callable
from types import ModuleType
from typing import Any
from typing import Protocol
from typing import runtime_checkable

from fanic.settings import static_asset_url


@runtime_checkable
class ResponseLike(Protocol):
    status_code: int
    data: bytes

    def set_data(self, data: str | bytes) -> None: ...


def test_fanart_gallery_renders_tag_chip_filter(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: Any,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/fanart.ex.get.py",
        "fanicsite_fanart_ex_get_filter_tag_test",
    )

    monkeypatch.setattr(
        module,
        "_resolve_owner_username",
        lambda owner_key: "alice" if owner_key else "",
    )
    monkeypatch.setattr(module, "current_user", lambda _request: None)
    monkeypatch.setattr(module, "role_for_user", lambda _username: "user")
    monkeypatch.setattr(module, "list_fanart_items_by_uploader", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(module, "list_fanart_items", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(module, "list_fanart_galleries_by_uploader", lambda *_args, **_kwargs: [])

    request = dummy_request(path="/fanart/alice", args={"tag": "sunset"})
    response = dummy_response()

    result = module.main(request, response)

    assert result.status_code == 200
    html = result.data.decode("utf-8")
    assert 'name="tag"' in html
    assert 'data-tag-type="freeform"' in html
    assert 'data-tag-chips="1"' in html
    assert 'autocomplete="off"' in html
    assert '<datalist id="freeformSuggestions">' in html
    assert f'<script src="{static_asset_url("tag-autocomplete", "js")}"></script>' in html
