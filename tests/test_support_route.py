from collections.abc import Callable
from types import ModuleType
from typing import Any
from typing import Protocol
from typing import cast


class ResponseLike(Protocol):
    status_code: int
    headers: dict[str, str]


class RouteModule(Protocol):
    def main(self, request: Any, response: ResponseLike) -> ResponseLike: ...


def test_support_route_redirects_to_buymeacoffee(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/support.ex.get.py",
        "fanicsite_support_ex_get_redirect_test",
    )
    route_module = cast(RouteModule, cast(object, module))

    request = dummy_request(path="/support")
    response = dummy_response()

    result = route_module.main(request, response)

    assert result.status_code == 303
    assert result.headers.get("Location") == "https://buymeacoffee.com/fanic.media"
