from dataclasses import dataclass

from fanic.cylinder_sites.common.protocols import FormLike
from fanic.repository.users import LocalUserRow


@dataclass(frozen=True)
class OnboardingFormData:
    display_name: str
    is_over_18: bool


@dataclass(frozen=True)
class OnboardingDisplayState:
    display_name: str
    over_18_yes_selected: str
    over_18_no_selected: str


def parse_onboarding_form(form: FormLike) -> OnboardingFormData | None:
    display_name_raw = form.get("display_name", "")
    display_name = display_name_raw.strip()
    is_over_18_raw = form.get("is_over_18", "")
    is_over_18_normalized = is_over_18_raw.strip().lower()

    match is_over_18_normalized:
        case "yes":
            is_over_18 = True
        case "no":
            is_over_18 = False
        case _:
            return None

    return OnboardingFormData(display_name=display_name, is_over_18=is_over_18)


def onboarding_display_state(
    username: str,
    local_user: LocalUserRow | None,
) -> OnboardingDisplayState:
    display_name = username
    is_over_18: bool | None = None
    if local_user is not None:
        display_name = str(local_user.get("display_name", username))
        raw_over_18 = local_user.get("is_over_18")
        is_over_18 = raw_over_18 if isinstance(raw_over_18, bool) else None

    over_18_yes_selected = "selected" if is_over_18 is True else ""
    over_18_no_selected = "selected" if is_over_18 is False else ""
    return OnboardingDisplayState(
        display_name=display_name,
        over_18_yes_selected=over_18_yes_selected,
        over_18_no_selected=over_18_no_selected,
    )
