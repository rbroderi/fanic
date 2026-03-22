from __future__ import annotations

from html import escape

REPORT_ISSUES: list[tuple[str, str]] = [
    ("copyright-dmca", "Copyright infringement (DMCA)"),
    ("illegal-content", "Illegal content"),
    (
        "child-sexual-abuse-material",
        "Child sexual abuse material (CSAM)",
    ),
    ("hate-harassment", "Hate, harassment, or targeted abuse"),
    ("violent-extremism", "Violent extremism or terror content"),
    ("fraud-spam", "Fraud, scam, spam, or malware"),
    ("privacy-doxxing", "Privacy violation or doxxing"),
    ("other", "Other policy concern"),
]

REPORT_ISSUE_LABEL_BY_TYPE = {issue_type: label for issue_type, label in REPORT_ISSUES}


def normalize_report_issue_type(issue_type: str) -> str:
    normalized = issue_type.strip()
    if normalized in REPORT_ISSUE_LABEL_BY_TYPE:
        return normalized
    return "other"


def report_issue_label(issue_type: str) -> str:
    normalized = normalize_report_issue_type(issue_type)
    return REPORT_ISSUE_LABEL_BY_TYPE[normalized]


def report_issue_options_html(selected_issue_type: str) -> str:
    normalized_selected = normalize_report_issue_type(selected_issue_type)
    options: list[str] = []
    for issue_type, label in REPORT_ISSUES:
        selected_attr = " selected" if issue_type == normalized_selected else ""
        options.append(
            f'<option value="{escape(issue_type)}"{selected_attr}>{escape(label)}</option>'
        )
    return "".join(options)
