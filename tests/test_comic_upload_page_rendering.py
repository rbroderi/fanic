from collections.abc import Callable
from types import ModuleType
from typing import Any
from typing import Protocol


class ResponseLike(Protocol):
    status_code: int
    content_type: str
    data: bytes

    def set_data(self, data: str | bytes) -> None: ...


def test_comic_upload_page_renders_site_placeholders(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/comic/upload.ex.get.py",
        "fanicsite_comic_upload_ex_get_render_placeholders_test",
    )

    request = dummy_request(path="/comic/upload", args={})
    response = dummy_response()
    result = module.main(request, response)

    html = result.data.decode("utf-8", errors="replace")
    assert result.status_code == 200
    assert "__SITE_HEAD_ASSETS__" not in html
    assert "__SITE_HEADER_HTML__" not in html
    assert "__SITE_COMMON_SCRIPTS__" not in html
    assert "/static/styles.css" in html


def test_comic_upload_get_accepts_trailing_slash(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/comic/upload.ex.get.py",
        "fanicsite_comic_upload_ex_get_trailing_slash_test",
    )

    request = dummy_request(path="/comic/upload/", args={})
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 200
