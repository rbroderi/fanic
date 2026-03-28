from enum import StrEnum
from html import escape

from fanic.repository import list_tag_names


class RatingChoice(StrEnum):
    NOT_RATED = "Not Rated"
    GENERAL_AUDIENCES = "General Audiences"
    TEEN_AND_UP_AUDIENCES = "Teen And Up Audiences"
    MATURE = "Mature"
    EXPLICIT = "Explicit"


RATING_CHOICES = [choice.value for choice in RatingChoice]


def selected_attr(actual: str, expected: str) -> str:
    return "selected" if actual == expected else ""


def render_options_html(names: list[str], selected: str) -> str:
    selected_norm = selected.strip().casefold()
    parts: list[str] = []
    for name in names:
        selected_attr_value = " selected" if name.strip().casefold() == selected_norm else ""
        parts.append(f'<option value="{escape(name)}"{selected_attr_value}>{escape(name)}</option>')
    return "".join(parts)


def render_tag_datalist_options_html(tag_type: str) -> str:
    return "".join(f'<option value="{escape(name)}"></option>' for name in list_tag_names(tag_type))


def render_common_tag_datalist_replacements() -> dict[str, str]:
    return {
        "__WARNINGS_OPTIONS_HTML__": render_tag_datalist_options_html("archive_warning"),
        "__FANDOM_OPTIONS_HTML__": render_tag_datalist_options_html("fandom"),
        "__RELATIONSHIP_OPTIONS_HTML__": render_tag_datalist_options_html("relationship"),
        "__CHARACTER_OPTIONS_HTML__": render_tag_datalist_options_html("character"),
        "__FREEFORM_OPTIONS_HTML__": render_tag_datalist_options_html("freeform"),
    }
