import importlib.util
import sys
from pathlib import Path
from typing import Any
from typing import Protocol

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class FileLike(Protocol):
    filename: str | None

    def save(self, dst: str | Path) -> None: ...


class DummyRequest:
    def __init__(
        self,
        *,
        path: str,
        method: str = "GET",
        args: dict[str, str] | None = None,
        form: dict[str, str] | None = None,
        files: dict[str, FileLike] | None = None,
        cookies: dict[str, str] | None = None,
    ) -> None:
        self.path: str = path
        self.method: str = method
        self.args: dict[str, str] = args if args is not None else {}
        self.form: dict[str, str] = form if form is not None else {}
        self.files: dict[str, FileLike] = files if files is not None else {}
        self.cookies: dict[str, str] = cookies if cookies is not None else {}


class DummyResponse:
    def __init__(self) -> None:
        self.status_code: int = 200
        self.content_type: str = "text/plain; charset=utf-8"
        self.headers: dict[str, str] = {}
        self.data: bytes = b""

    def set_data(self, data: str | bytes) -> None:
        if isinstance(data, str):
            self.data = data.encode("utf-8")
        else:
            self.data = data

    def set_cookie(
        self,
        key: str,
        value: str,
        max_age: int | None = None,
        path: str = "/",
        secure: bool = False,
        httponly: bool = False,
        samesite: str = "Lax",
    ) -> None:
        _ = (key, value, max_age, path, secure, httponly, samesite)

    def delete_cookie(self, key: str, path: str = "/") -> None:
        _ = (key, path)


@pytest.fixture
def load_route_module() -> Any:
    def _load(relative_path: str, module_name: str) -> Any:
        module_path = ROOT / relative_path
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Unable to load module from {module_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    return _load


@pytest.fixture
def dummy_request() -> type[DummyRequest]:
    return DummyRequest


@pytest.fixture
def dummy_response() -> type[DummyResponse]:
    return DummyResponse
