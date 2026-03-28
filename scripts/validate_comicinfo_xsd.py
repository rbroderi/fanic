from __future__ import annotations

import sys
from pathlib import Path


def _load_schema_module() -> object:
    try:
        import xmlschema  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "Missing dependency 'xmlschema'. Run via uvx with --with xmlschema or install xmlschema."
        ) from exc
    return xmlschema


def main(argv: list[str]) -> int:
    repo_root = Path(__file__).resolve().parents[1]
    schema_path = repo_root / "schema" / "comicinfo" / "v2.0" / "ComicInfo.xsd"
    if not schema_path.exists():
        print(f"Schema file not found: {schema_path}")
        return 2

    xml_files = [Path(item) for item in argv[1:] if item.strip()]
    if not xml_files:
        return 0

    try:
        xmlschema = _load_schema_module()
        schema = xmlschema.XMLSchema(str(schema_path))
    except Exception as exc:  # pragma: no cover - tool/runtime failures
        print(f"Failed to initialize schema validator: {exc}")
        return 2

    failed = 0
    for xml_path in xml_files:
        if not xml_path.exists():
            continue
        try:
            schema.validate(str(xml_path))
        except Exception as exc:
            failed += 1
            print(f"[ComicInfo XSD] Validation failed: {xml_path}")
            print(f"  {exc}")

    if failed:
        print(f"[ComicInfo XSD] {failed} file(s) failed validation.")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
