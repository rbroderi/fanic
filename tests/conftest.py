import importlib.util
import os
import shutil
import sys
import tomllib
from pathlib import Path
from typing import Any
from typing import Protocol

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

# Force tests onto isolated runtime storage and DB path.
TEST_RUNTIME_ROOT = (ROOT / ".pytest-runtime").resolve()
os.environ.setdefault("FANIC_DATA_DIR", str(TEST_RUNTIME_ROOT))
os.environ.setdefault("FANIC_DB_PATH", str(TEST_RUNTIME_ROOT / "fanic.test.db"))


def _settings_toml_db_path() -> Path:
    settings_toml_path = ROOT / "settings.toml"
    if not settings_toml_path.is_file():
        return ROOT / "runtime" / "fanic.db"

    with settings_toml_path.open("rb") as handle:
        parsed = tomllib.load(handle)
    db_path_raw = parsed.get("db_path")
    if isinstance(db_path_raw, str) and db_path_raw.strip():
        return Path(db_path_raw).expanduser()
    return ROOT / "runtime" / "fanic.db"


def _test_db_source_path() -> Path:
    source_from_env = os.environ.get("FANIC_TEST_DB_SOURCE_PATH")
    if isinstance(source_from_env, str) and source_from_env.strip():
        return Path(source_from_env).expanduser()

    source_from_legacy_env = os.environ.get("FANIC_PROD_DB_PATH")
    if isinstance(source_from_legacy_env, str) and source_from_legacy_env.strip():
        return Path(source_from_legacy_env).expanduser()

    return _settings_toml_db_path()


if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@pytest.fixture(autouse=True, scope="session")
def _guard_test_runtime_paths() -> None:  # pyright: ignore[reportUnusedFunction]
    test_data_dir_raw = os.environ.get("FANIC_DATA_DIR", "")
    test_db_path_raw = os.environ.get("FANIC_DB_PATH", "")
    if not test_data_dir_raw or not test_db_path_raw:
        pytest.fail("FANIC_DATA_DIR and FANIC_DB_PATH must be set for tests.")

    test_data_dir = Path(test_data_dir_raw).expanduser().resolve()
    test_db_path = Path(test_db_path_raw).expanduser().resolve()
    disallowed_roots = (Path("/mnt/storage"), ROOT / "runtime")

    for disallowed_root in disallowed_roots:
        resolved_root = disallowed_root.resolve()
        if test_data_dir.is_relative_to(resolved_root):
            pytest.fail(f"Unsafe FANIC_DATA_DIR for tests: {test_data_dir}")
        if test_db_path.is_relative_to(resolved_root):
            pytest.fail(f"Unsafe FANIC_DB_PATH for tests: {test_db_path}")


@pytest.fixture(autouse=True, scope="session")
def _seed_test_database_copy() -> None:  # pyright: ignore[reportUnusedFunction]
    target_db_path = Path(os.environ["FANIC_DB_PATH"]).expanduser().resolve()
    source_db_path = _test_db_source_path().resolve()

    target_db_path.parent.mkdir(parents=True, exist_ok=True)
    if target_db_path.exists():
        target_db_path.unlink()

    if source_db_path.exists():
        shutil.copy2(source_db_path, target_db_path)


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
