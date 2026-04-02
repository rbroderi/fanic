from fanic.cylinder_sites.enum_helpers import DashNameEnum
from fanic.cylinder_sites.enum_helpers import options_html


class FeedbackCategory(DashNameEnum):
    BUG_REPORT = "Bug report"
    PERFORMANCE = "Performance issue"
    USABILITY_UX = "Usability or UX improvement"
    ACCESSIBILITY = "Accessibility issue"
    CONTENT_DISCOVERY = "Search, tagging, or discovery improvement"
    FEATURE_REQUEST = "Feature request"
    OTHER = "Other site feedback"


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
    return options_html(
        FeedbackCategory,
        selected_dash_name=selected_category,
        fallback=FeedbackCategory.OTHER,
    )
