import json
from collections.abc import Callable
from contextlib import contextmanager
from types import ModuleType
from typing import Any
from typing import Protocol
from typing import cast

from fanic.storage_health import FanartStorageHealth


class ResponseLike(Protocol):
    status_code: int
    data: bytes

    def set_data(self, data: str | bytes) -> None: ...


class HealthRouteModule(Protocol):
    def main(self, request: Any, response: ResponseLike) -> ResponseLike: ...


def _health_degraded(*, max_rows_to_check: int = 50) -> FanartStorageHealth:
    _ = max_rows_to_check
    return FanartStorageHealth(
        status="degraded",
        db_items=2,
        checked_items=2,
        missing_image_files=2,
        missing_thumb_files=2,
        image_dir_exists=True,
        thumb_dir_exists=True,
    )


def test_api_health_not_found(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/api/health.ex.get.py",
        "fanicsite_api_health_ex_get_not_found_test",
    )
    route_module = cast(HealthRouteModule, cast(object, module))

    request = dummy_request(path="/api/not-health")
    response = dummy_response()

    result = route_module.main(request, response)

    assert result.status_code == 404


def test_api_health_reports_fanart_storage(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: Any,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/api/health.ex.get.py",
        "fanicsite_api_health_ex_get_fanart_storage_test",
    )
    route_module = cast(HealthRouteModule, cast(object, module))

    class _Cursor:
        def fetchone(self):
            return (1,)

    class _Connection:
        def execute(self, _query: str):
            return _Cursor()

    @contextmanager
    def _fake_get_connection():
        yield _Connection()

    monkeypatch.setattr(module, "get_connection", _fake_get_connection)
    monkeypatch.setattr(module, "get_fanart_storage_health", _health_degraded)

    request = dummy_request(path="/api/health")
    response = dummy_response()

    result = route_module.main(request, response)
    payload = json.loads(result.data.decode("utf-8"))

    assert result.status_code == 200
    assert payload["ok"] is True
    assert payload["db"] == "up"
    assert payload["fanart_storage"] == "degraded"
    assert payload["fanart_missing_images"] == 2
    assert payload["fanart_missing_thumbs"] == 2
