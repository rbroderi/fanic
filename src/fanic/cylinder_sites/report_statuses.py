from fanic.cylinder_sites.enum_helpers import DashNameEnum
from fanic.cylinder_sites.enum_helpers import options_html


class ReportStatusType(DashNameEnum):
    OPEN = "Open"
    RE_OPEN = "Re-open"
    RESOLVED = "Resolved"
    FALSE_REPORT = "False report"
    NEEDS_RESEARCH = "More research needed"


def normalize_report_status(status: str) -> str:
    resolved = ReportStatusType.from_dash_name(status)
    if resolved is not None:
        return resolved.name_to_dash()
    return ""


def report_status_label(status: str) -> str:
    resolved = ReportStatusType.from_dash_name(status)
    if resolved is not None:
        return str(resolved)
    normalized = status.strip()
    return normalized if normalized else str(ReportStatusType.OPEN)


def report_status_options_html(selected_status: str) -> str:
    return options_html(ReportStatusType, selected_dash_name=selected_status)
