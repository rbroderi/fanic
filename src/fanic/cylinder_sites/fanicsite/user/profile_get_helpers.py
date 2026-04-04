from collections.abc import Mapping
from collections.abc import Sequence
from dataclasses import dataclass
from html import escape


@dataclass(frozen=True)
class StatusPayload:
    text: str
    css_class: str
    hidden_attr: str


@dataclass(frozen=True)
class ProfileVisibility:
    onboarding_hidden_attr: str
    account_summary_hidden_attr: str
    appearance_hidden_attr: str
    public_link_hidden_attr: str
    immutable_public_link_hidden_attr: str
    theme_form_hidden_attr: str
    history_hidden_attr: str


def recent_history_html(history_rows: Sequence[Mapping[str, object]]) -> str:
    if not history_rows:
        return '<p class="profile-meta">No reading history yet.</p>'

    items: list[str] = []
    for row in history_rows:
        work_id = escape(str(row.get("work_id", "")))
        work_title = escape(str(row.get("work_title", "Untitled")))
        page_index = escape(str(row.get("page_index", 1)))
        updated_at = escape(str(row.get("updated_at", "")))
        items.append(
            f'<li><a href="/tools/reader/{work_id}">{work_title}</a> '
            f'<span class="profile-meta">(continue at page {page_index}; last viewed {updated_at})</span></li>'
        )
    return '<ul class="work-links">' + "".join(items) + "</ul>"


def preference_status(save_msg: str) -> StatusPayload:
    if save_msg == "saved":
        return StatusPayload(text="Preference saved.", css_class="success", hidden_attr="")
    return StatusPayload(text="", css_class="", hidden_attr="hidden")


def display_name_status(save_msg: str) -> StatusPayload:
    match save_msg:
        case "display-name-saved":
            return StatusPayload(text="Profile details updated.", css_class="success", hidden_attr="")
        case "display-name-invalid":
            return StatusPayload(
                text="Display name must use only letters and numbers, and age selection is required.",
                css_class="error",
                hidden_attr="",
            )
        case "display-name-taken":
            return StatusPayload(
                text="That display name is already in use.",
                css_class="error",
                hidden_attr="",
            )
        case _:
            return StatusPayload(text="", css_class="", hidden_attr="hidden")


def theme_status(save_msg: str) -> StatusPayload:
    match save_msg:
        case "theme_saved":
            return StatusPayload(text="Theme preferences saved.", css_class="success", hidden_attr="")
        case "theme_parse_error":
            return StatusPayload(text="Invalid theme.toml format.", css_class="error", hidden_attr="")
        case "theme_upload_error":
            return StatusPayload(
                text="Failed to read uploaded theme.toml file.",
                css_class="error",
                hidden_attr="",
            )
        case _:
            return StatusPayload(text="", css_class="", hidden_attr="hidden")


def onboarding_status(save_msg: str, *, requires_onboarding: bool) -> StatusPayload:
    match save_msg:
        case "onboarding-required":
            status = StatusPayload(
                text="Please finish onboarding before using the rest of the site.",
                css_class="error",
                hidden_attr="",
            )
        case "onboarding-saved":
            status = StatusPayload(text="Profile details saved.", css_class="success", hidden_attr="")
        case "onboarding-invalid":
            status = StatusPayload(
                text="Display name must use only letters and numbers, and age selection is required.",
                css_class="error",
                hidden_attr="",
            )
        case "onboarding-name-taken":
            status = StatusPayload(
                text="That display name is already in use.",
                css_class="error",
                hidden_attr="",
            )
        case "onboarding-already-complete":
            status = StatusPayload(
                text="Onboarding has already been completed for this account.",
                css_class="error",
                hidden_attr="",
            )
        case "underage-restricted":
            status = StatusPayload(
                text="Your account is currently limited to this page.",
                css_class="error",
                hidden_attr="",
            )
        case _:
            status = StatusPayload(text="", css_class="", hidden_attr="hidden")

    if save_msg == "onboarding-already-complete" and not requires_onboarding:
        return StatusPayload(text="", css_class="", hidden_attr="hidden")
    return status


def profile_visibility(requires_onboarding: bool) -> ProfileVisibility:
    onboarding_hidden_attr = "" if requires_onboarding else "hidden"
    account_summary_hidden_attr = "hidden" if requires_onboarding else ""
    appearance_hidden_attr = "hidden" if requires_onboarding else ""
    public_link_hidden_attr = "hidden" if requires_onboarding else ""
    immutable_public_link_hidden_attr = "hidden" if requires_onboarding else ""
    theme_form_hidden_attr = "hidden" if requires_onboarding else ""
    history_hidden_attr = "hidden" if requires_onboarding else ""
    return ProfileVisibility(
        onboarding_hidden_attr=onboarding_hidden_attr,
        account_summary_hidden_attr=account_summary_hidden_attr,
        appearance_hidden_attr=appearance_hidden_attr,
        public_link_hidden_attr=public_link_hidden_attr,
        immutable_public_link_hidden_attr=immutable_public_link_hidden_attr,
        theme_form_hidden_attr=theme_form_hidden_attr,
        history_hidden_attr=history_hidden_attr,
    )
