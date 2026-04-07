import os
import statistics
import time
from pathlib import Path
from zipfile import ZipFile

import pytest

from fanic.moderation import moderate_image_bytes

MEDIA_DIR = Path(__file__).resolve().parent / "media"
_IMAGE_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".avif",
    ".gif",
    ".bmp",
    ".tif",
    ".tiff",
}


def _resolve_cbz_path() -> Path | None:
    env_path = os.getenv("FANIC_MODERATION_TIMING_CBZ", "").strip()
    if env_path:
        candidate = Path(env_path)
        return candidate if candidate.exists() else None

    default_cbz = MEDIA_DIR / "mod_test.cbz"
    if default_cbz.exists():
        return default_cbz

    candidates = sorted(path for path in MEDIA_DIR.glob("*.cbz") if path.is_file())
    return candidates[0] if candidates else None


def _p95_ms(values_ms: list[float]) -> float:
    if not values_ms:
        return 0.0
    ordered = sorted(values_ms)
    index = int((len(ordered) - 1) * 0.95)
    return ordered[index]


def test_moderation_timing_for_cbz_pages() -> None:
    enabled = os.getenv("FANIC_RUN_MODERATION_TIMING", "").strip()
    if enabled != "1":
        pytest.skip("Set FANIC_RUN_MODERATION_TIMING=1 to run moderation timing test")

    cbz_path = _resolve_cbz_path()
    if cbz_path is None:
        pytest.skip("No CBZ found for moderation timing test")

    with ZipFile(cbz_path, "r") as cbz_file:
        image_members = sorted(
            member
            for member in cbz_file.namelist()
            if not member.endswith("/") and Path(member).suffix.lower() in _IMAGE_SUFFIXES
        )

        if not image_members:
            pytest.skip(f"No image pages found in {cbz_path.name}")

        elapsed_ms_values: list[float] = []
        allowed_count = 0

        print(f"\nTiming moderation for {cbz_path} ({len(image_members)} pages)")
        for index, member in enumerate(image_members, start=1):
            payload = cbz_file.read(member)
            suffix = Path(member).suffix

            started_at = time.perf_counter()
            try:
                result = moderate_image_bytes(payload, suffix=suffix)
            except Exception as exc:
                elapsed_ms = (time.perf_counter() - started_at) * 1000.0
                print(f"page {index:03d}/{len(image_members)} {member} -> FAILED after {elapsed_ms:.1f}ms error={exc}")
                raise

            elapsed_ms = (time.perf_counter() - started_at) * 1000.0
            elapsed_ms_values.append(elapsed_ms)

            if bool(result.get("allow", False)):
                allowed_count += 1

            print(
                f"page {index:03d}/{len(image_members)} {member} -> "
                f"{elapsed_ms:.1f}ms allow={bool(result.get('allow', False))} "
                f"style={result.get('style', 'unknown')} nsfw={float(result.get('nsfw_score', 0.0)):.4f}"
            )

    total_ms = sum(elapsed_ms_values)
    avg_ms = statistics.mean(elapsed_ms_values)
    med_ms = statistics.median(elapsed_ms_values)
    max_ms = max(elapsed_ms_values)
    min_ms = min(elapsed_ms_values)
    p95_ms = _p95_ms(elapsed_ms_values)

    print("\nModeration timing summary")
    print(f"cbz={cbz_path}")
    print(f"pages={len(elapsed_ms_values)} allowed={allowed_count}")
    print(f"total_ms={total_ms:.1f}")
    print(f"avg_ms={avg_ms:.1f} median_ms={med_ms:.1f} p95_ms={p95_ms:.1f}")
    print(f"min_ms={min_ms:.1f} max_ms={max_ms:.1f}")

    assert len(elapsed_ms_values) > 0
