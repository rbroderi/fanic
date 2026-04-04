from fanic.cylinder_sites.fanicsite.user.profile_get_helpers import display_name_status
from fanic.cylinder_sites.fanicsite.user.profile_get_helpers import onboarding_status
from fanic.cylinder_sites.fanicsite.user.profile_get_helpers import preference_status
from fanic.cylinder_sites.fanicsite.user.profile_get_helpers import profile_visibility
from fanic.cylinder_sites.fanicsite.user.profile_get_helpers import theme_status


def test_preference_status_mapping() -> None:
    saved = preference_status("saved")
    assert saved.text == "Preference saved."
    assert saved.css_class == "success"
    assert saved.hidden_attr == ""

    default = preference_status("other")
    assert default.text == ""
    assert default.css_class == ""
    assert default.hidden_attr == "hidden"


def test_display_name_status_mapping() -> None:
    saved = display_name_status("display-name-saved")
    assert saved.css_class == "success"
    assert saved.hidden_attr == ""

    invalid = display_name_status("display-name-invalid")
    assert "Display name must use only letters and numbers" in invalid.text
    assert invalid.css_class == "error"
    assert invalid.hidden_attr == ""

    default = display_name_status("other")
    assert default.text == ""
    assert default.css_class == ""
    assert default.hidden_attr == "hidden"


def test_theme_status_mapping() -> None:
    saved = theme_status("theme_saved")
    assert saved.text == "Theme preferences saved."
    assert saved.css_class == "success"

    parse_error = theme_status("theme_parse_error")
    assert parse_error.text == "Invalid theme.toml format."
    assert parse_error.css_class == "error"


def test_onboarding_status_handles_already_complete_override() -> None:
    visible = onboarding_status("onboarding-already-complete", requires_onboarding=True)
    assert visible.text == "Onboarding has already been completed for this account."
    assert visible.css_class == "error"
    assert visible.hidden_attr == ""

    hidden = onboarding_status("onboarding-already-complete", requires_onboarding=False)
    assert hidden.text == ""
    assert hidden.css_class == ""
    assert hidden.hidden_attr == "hidden"


def test_onboarding_status_mapping_for_required_and_underage() -> None:
    required = onboarding_status("onboarding-required", requires_onboarding=True)
    assert required.text == "Please finish onboarding before using the rest of the site."
    assert required.css_class == "error"
    assert required.hidden_attr == ""

    underage = onboarding_status("underage-restricted", requires_onboarding=False)
    assert underage.text == "Your account is currently limited to this page."
    assert underage.css_class == "error"
    assert underage.hidden_attr == ""


def test_profile_visibility_mapping() -> None:
    visible = profile_visibility(True)
    assert visible.onboarding_hidden_attr == ""
    assert visible.account_summary_hidden_attr == "hidden"
    assert visible.appearance_hidden_attr == "hidden"
    assert visible.public_link_hidden_attr == "hidden"
    assert visible.immutable_public_link_hidden_attr == "hidden"
    assert visible.theme_form_hidden_attr == "hidden"
    assert visible.history_hidden_attr == "hidden"

    default = profile_visibility(False)
    assert default.onboarding_hidden_attr == "hidden"
    assert default.account_summary_hidden_attr == ""
    assert default.appearance_hidden_attr == ""
    assert default.public_link_hidden_attr == ""
    assert default.immutable_public_link_hidden_attr == ""
    assert default.theme_form_hidden_attr == ""
    assert default.history_hidden_attr == ""
