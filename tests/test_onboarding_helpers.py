from fanic.cylinder_sites.fanicsite.user.onboarding_helpers import (
    onboarding_display_state,
)
from fanic.cylinder_sites.fanicsite.user.onboarding_helpers import parse_onboarding_form
from fanic.repository.users import LocalUserRow


class _FormStub:
    def __init__(self, values: dict[str, str]) -> None:
        self._values: dict[str, str] = values

    def get(self, key: str, default: str = "") -> str:
        return self._values.get(key, default)


def test_parse_onboarding_form_accepts_yes_and_no() -> None:
    yes = parse_onboarding_form(_FormStub({"display_name": " Alice ", "is_over_18": " yes "}))
    assert yes is not None
    assert yes.display_name == "Alice"
    assert yes.is_over_18 is True

    no = parse_onboarding_form(_FormStub({"display_name": "Bob", "is_over_18": "no"}))
    assert no is not None
    assert no.display_name == "Bob"
    assert no.is_over_18 is False


def test_parse_onboarding_form_rejects_invalid_age_value() -> None:
    parsed = parse_onboarding_form(_FormStub({"display_name": "Alice", "is_over_18": "maybe"}))
    assert parsed is None


def test_onboarding_display_state_uses_local_user_when_present() -> None:
    local_user: LocalUserRow = {
        "username": "alice",
        "display_name": "AliceArtist",
        "email": "alice@example.com",
        "is_over_18": False,
        "age_gate_completed": False,
        "role": "user",
        "active": True,
        "created_at": "2026-03-22T00:00:00Z",
    }
    state = onboarding_display_state(
        "alice",
        local_user,
    )
    assert state.display_name == "AliceArtist"
    assert state.over_18_yes_selected == ""
    assert state.over_18_no_selected == "selected"


def test_onboarding_display_state_defaults_to_username_without_local_user() -> None:
    state = onboarding_display_state("alice", None)
    assert state.display_name == "alice"
    assert state.over_18_yes_selected == ""
    assert state.over_18_no_selected == ""
