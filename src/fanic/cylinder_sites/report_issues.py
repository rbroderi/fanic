from __future__ import annotations

from enum import StrEnum
from html import escape


class ReportIssueType(StrEnum):
    COPYRIGHT_DMCA = "Copyright infringement (DMCA)"
    ILLEGAL_CONTENT = "Illegal content"
    CHILD_SEXUAL_ABUSE_MATERIAL = "Child sexual abuse material (CSAM)"
    HATE_HARASSMENT = "Hate, harassment, or targeted abuse"
    VIOLENT_EXTREMISM = "Violent extremism or terror content"
    FRAUD_SPAM = "Fraud, scam, spam, or malware"
    PRIVACY_DOXXING = "Privacy violation or doxxing"
    OTHER = "Other policy concern"

    def name_to_dash(self) -> str:
        return self.name.lower().replace("_", "-")

    @classmethod
    def from_dash_name(cls, dash_name: str) -> ReportIssueType | None:
        normalized = dash_name.strip()
        for issue_type in cls:
            if issue_type.name_to_dash() == normalized:
                return issue_type
        return None


def normalize_report_issue_type(issue_type: str) -> str:
    resolved = ReportIssueType.from_dash_name(issue_type)
    if resolved is not None:
        return resolved.name_to_dash()
    return ReportIssueType.OTHER.name_to_dash()


def report_issue_label(issue_type: str) -> str:
    resolved = ReportIssueType.from_dash_name(issue_type)
    resolved_issue_type = resolved if resolved is not None else ReportIssueType.OTHER
    return str(resolved_issue_type)


def report_issue_options_html(selected_issue_type: str) -> str:
    normalized_selected = normalize_report_issue_type(selected_issue_type)
    options: list[str] = []
    for issue_type in ReportIssueType:
        issue_dash_name = issue_type.name_to_dash()
        selected_attr = " selected" if issue_dash_name == normalized_selected else ""
        options.append(
            f'<option value="{escape(issue_dash_name)}"{selected_attr}>{escape(str(issue_type))}</option>'
        )
    return "".join(options)
