from enum import StrEnum
from html import escape
from typing import Self


class ReportStatusType(StrEnum):
    OPEN = "Open"
    RE_OPEN = "Re-open"
    RESOLVED = "Resolved"
    FALSE_REPORT = "False report"
    NEEDS_RESEARCH = "More research needed"

    def name_to_dash(self) -> str:
        return self.name.lower().replace("_", "-")

    @classmethod
    def from_dash_name(cls, dash_name: str) -> Self | None:
        normalized = dash_name.strip()
        for status in cls:
            if status.name_to_dash() == normalized:
                return status
        return None


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
    normalized_selected = normalize_report_status(selected_status)
    options: list[str] = []
    for status in ReportStatusType:
        status_dash_name = status.name_to_dash()
        selected_attr = " selected" if status_dash_name == normalized_selected else ""
        options.append(f'<option value="{escape(status_dash_name)}"{selected_attr}>{escape(str(status))}</option>')
    return "".join(options)
