from collections.abc import Callable
from types import ModuleType
from typing import Any
from typing import Protocol


class ResponseLike(Protocol):
    status_code: int
    content_type: str
    data: bytes

    def set_data(self, data: str | bytes) -> None: ...


def test_fanart_upload_get_accepts_trailing_slash(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/fanart/upload.ex.get.py",
        "fanicsite_fanart_upload_ex_get_trailing_slash_test",
    )

    request = dummy_request(path="/fanart/upload/", args={})
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 200
