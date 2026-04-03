import os
import shutil
from pathlib import Path

from fanic.settings import get_settings

_SETTINGS = get_settings()
_MANAGED_RUNTIME_ROOT = _SETTINGS.data_root.resolve()


def _running_under_pytest() -> bool:
    return True if os.environ.get("PYTEST_VERSION") else False


def _allow_pytest_mutations() -> bool:
    return True if os.environ.get("FANIC_ALLOW_PYTEST_FILESYSTEM_MUTATIONS") else False


def _is_managed_runtime_path(path: Path) -> bool:
    try:
        _ = path.resolve().relative_to(_MANAGED_RUNTIME_ROOT)
    except ValueError:
        return False
    return True


def _should_skip_mutation_for_tests(path: Path) -> bool:
    if not _running_under_pytest():
        return False
    if _allow_pytest_mutations():
        return False
    return True if _is_managed_runtime_path(path) else False


def delete_file(path: Path, *, missing_ok: bool = False) -> None:
    if _should_skip_mutation_for_tests(path):
        return
    path.unlink(missing_ok=missing_ok)


def delete_tree(path: Path, *, ignore_errors: bool = False) -> None:
    if _should_skip_mutation_for_tests(path):
        return
    shutil.rmtree(path, ignore_errors=ignore_errors)


def copy_file(src: Path, dst: Path) -> Path:
    if _should_skip_mutation_for_tests(dst):
        return dst
    return Path(shutil.copy2(src, dst))


def copy_tree(src: Path, dst: Path) -> Path:
    if _should_skip_mutation_for_tests(dst):
        return dst
    return Path(shutil.copytree(src, dst))
