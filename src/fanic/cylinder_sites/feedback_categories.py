from enum import StrEnum
from html import escape
from typing import Self


class FeedbackCategory(StrEnum):
    BUG_REPORT = "Bug report"
    PERFORMANCE = "Performance issue"
    USABILITY_UX = "Usability or UX improvement"
    ACCESSIBILITY = "Accessibility issue"
    CONTENT_DISCOVERY = "Search, tagging, or discovery improvement"
    FEATURE_REQUEST = "Feature request"
    OTHER = "Other site feedback"

    def name_to_dash(self) -> str:
        return self.name.lower().replace("_", "-")

    @classmethod
    def from_dash_name(cls, dash_name: str) -> Self | None:
        normalized = dash_name.strip()
        for category in cls:
            if category.name_to_dash() == normalized:
                return category
        return None


def normalize_feedback_category(category: str) -> str:
    resolved = FeedbackCategory.from_dash_name(category)
    if resolved is not None:
        return resolved.name_to_dash()
    return FeedbackCategory.OTHER.name_to_dash()


def feedback_category_label(category: str) -> str:
    resolved = FeedbackCategory.from_dash_name(category)
    resolved_category = resolved if resolved is not None else FeedbackCategory.OTHER
    return str(resolved_category)


def feedback_category_options_html(selected_category: str) -> str:
    normalized_selected = normalize_feedback_category(selected_category)
    options: list[str] = []
    for category in FeedbackCategory:
        dash_name = category.name_to_dash()
        selected_attr = " selected" if dash_name == normalized_selected else ""
        options.append(f'<option value="{escape(dash_name)}"{selected_attr}>{escape(str(category))}</option>')
    return "".join(options)
