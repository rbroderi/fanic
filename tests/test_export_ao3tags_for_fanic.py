import importlib.util
import sys
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "export_ao3tags_for_fanic.py"
    spec = importlib.util.spec_from_file_location("export_ao3tags_for_fanic", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load export_ao3tags_for_fanic.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_build_canonical_tags_applies_min_count_and_slug_dedupe() -> None:
    module = _load_module()

    source = {
        "Hurt/Comfort": 100,
        "hurt comfort": 90,
        "Fluff": 12,
        "Low Count": 1,
    }

    tags = module._build_canonical_tags(source, min_count=10)

    assert [tag.slug for tag in tags] == ["fluff", "hurt-comfort"]
    assert tags[1].name == "Hurt/Comfort"
    assert tags[1].ao3_count == 100


def test_write_sql_escapes_quotes(tmp_path: Path) -> None:
    module = _load_module()

    tags = [
        module.CanonicalTag(
            slug="author-s-choice",
            name="Author's Choice",
            type="freeform",
            ao3_count=10,
        )
    ]

    output = tmp_path / "tags.sql"
    module._write_sql(output, tags)
    content = output.read_text(encoding="utf-8")

    assert "Author''s Choice" in content
    assert "ON CONFLICT(slug) DO UPDATE" in content


def test_patch_fetchtags_page_count_updates_total_line(tmp_path: Path) -> None:
    module = _load_module()

    fetchtags = tmp_path / "fetchtags.js"
    fetchtags.write_text(
        "var base = 'x';\nvar total = 1000;\nfunction x() {}\n",
        encoding="utf-8",
    )

    module._patch_fetchtags_page_count(fetchtags, 123)
    content = fetchtags.read_text(encoding="utf-8")

    assert "var total = 123;" in content


def test_live_fetch_rejects_non_positive_page_count() -> None:
    module = _load_module()

    try:
        module._read_json_via_ao3tags_live_fetch(page_count=0, repo_dir=None)
        raised = False
    except ValueError:
        raised = True

    assert raised


def test_extract_max_page_from_ao3_search_html() -> None:
    module = _load_module()

    html = (
        '<a href="/tags/search?page=1&query%5Btype%5D=Freeform">1</a>'
        '<a href="/tags/search?page=87&query%5Btype%5D=Freeform">87</a>'
        '<a href="/tags/search?page=23&query%5Btype%5D=Freeform">23</a>'
    )

    assert module._extract_max_page_from_ao3_search_html(html) == 87


def test_detect_ao3_freeform_page_count_uses_parsed_html() -> None:
    module = _load_module()

    module._read_text_from_url = lambda _url: (
        '<a href="/tags/search?page=1&query%5Btype%5D=Freeform">1</a>'
        '<a href="/tags/search?page=42&query%5Btype%5D=Freeform">42</a>'
    )

    assert module._detect_ao3_freeform_page_count() == 42


def test_bot_challenge_html_is_detected() -> None:
    module = _load_module()

    html = "<html><title>Shields are up! | Archive of Our Own</title></html>"
    assert module._is_ao3_bot_challenge_html(html)


def test_assert_not_bot_challenge_raises_on_challenge_page() -> None:
    module = _load_module()

    raised = False
    try:
        module._assert_not_ao3_bot_challenge_html("<html>Enable JavaScript and cookies to continue</html>")
    except RuntimeError:
        raised = True

    assert raised


def test_ao3_freeform_search_url_contains_requested_page() -> None:
    module = _load_module()

    url = module._ao3_freeform_search_url(77)

    assert "page=77" in url
    assert "query%5Btype%5D=Freeform" in url


def test_ao3_headers_from_auth_inputs_prefers_cookie_header() -> None:
    module = _load_module()

    headers = module._ao3_headers_from_auth_inputs(
        "a=1; b=2",
        "token123",
        "Agent/1.0",
    )

    assert headers["Cookie"] == "a=1; b=2"
    assert headers["User-Agent"] == "Agent/1.0"


def test_ao3_headers_from_auth_inputs_falls_back_to_cf_clearance() -> None:
    module = _load_module()

    headers = module._ao3_headers_from_auth_inputs("", "token123", "Agent/1.0")

    assert headers["Cookie"] == "cf_clearance=token123"
    assert headers["User-Agent"] == "Agent/1.0"


def test_extract_tag_counts_from_search_html() -> None:
    module = _load_module()

    html = (
        '<li><a class="tag" href="/tags/1">Hurt &amp; Comfort</a> (123)</li>'
        '<li><a class="tag" href="/tags/2">Fluff</a> (45)</li>'
    )

    tags = module._extract_tag_counts_from_search_html(html)

    assert tags["Hurt & Comfort"] == 123
    assert tags["Fluff"] == 45
