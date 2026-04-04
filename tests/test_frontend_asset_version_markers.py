import re
from pathlib import Path

from fanic.settings import ASSET_VERSIONS

_VERSION_RE = re.compile(r"FANIC_ASSET_VERSION:\s*([A-Za-z0-9._-]+)")


def _has_version_marker(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    header = "\n".join(text.splitlines()[:30])
    return _VERSION_RE.search(header) is not None


def test_frontend_typescript_sources_define_asset_versions() -> None:
    frontend_dir = Path("frontend")
    missing: list[str] = []

    for source_path in sorted(frontend_dir.glob("*.ts")):
        if not _has_version_marker(source_path):
            missing.append(str(source_path))

    assert not missing, f"Missing FANIC_ASSET_VERSION marker in: {', '.join(missing)}"


def test_stylesheet_source_defines_asset_version() -> None:
    styles_path = Path("frontend/styles.css")
    assert _has_version_marker(styles_path), "Missing FANIC_ASSET_VERSION marker in frontend/styles.css"


def test_versioned_stylesheet_build_output_exists() -> None:
    styles_version = ASSET_VERSIONS.get("styles", "0")
    built_styles_path = Path(f"/mnt/storage/static/styles.v{styles_version}.css")
    assert built_styles_path.exists(), (
        f"Expected built stylesheet missing: {built_styles_path}. "
        "Run `npm run frontend:build` to generate versioned frontend assets."
    )
