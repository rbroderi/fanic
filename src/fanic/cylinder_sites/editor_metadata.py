from __future__ import annotations

from html import escape

from fanic.repository import list_tag_names

RATING_CHOICES = [
    "Not Rated",
    "General Audiences",
    "Teen And Up Audiences",
    "Mature",
    "Explicit",
]


def selected_attr(actual: str, expected: str) -> str:
    return "selected" if actual == expected else ""


def render_options_html(names: list[str], selected: str) -> str:
    selected_norm = selected.strip().casefold()
    parts: list[str] = []
    for name in names:
        selected_attr_value = (
            " selected" if name.strip().casefold() == selected_norm else ""
        )
        parts.append(
            f'<option value="{escape(name)}"{selected_attr_value}>{escape(name)}</option>'
        )
    return "".join(parts)


def render_tag_datalist_options_html(tag_type: str) -> str:
    return "".join(
        f'<option value="{escape(name)}"></option>' for name in list_tag_names(tag_type)
    )


def render_common_tag_datalist_replacements() -> dict[str, str]:
    return {
        "__WARNINGS_OPTIONS_HTML__": render_tag_datalist_options_html(
            "archive_warning"
        ),
        "__FANDOM_OPTIONS_HTML__": render_tag_datalist_options_html("fandom"),
        "__RELATIONSHIP_OPTIONS_HTML__": render_tag_datalist_options_html(
            "relationship"
        ),
        "__CHARACTER_OPTIONS_HTML__": render_tag_datalist_options_html("character"),
        "__FREEFORM_OPTIONS_HTML__": render_tag_datalist_options_html("freeform"),
    }
