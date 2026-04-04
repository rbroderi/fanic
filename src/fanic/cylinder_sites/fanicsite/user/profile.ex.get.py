from html import escape

from fanic.cylinder_sites.common.protocols import RequestLike
from fanic.cylinder_sites.common.protocols import ResponseLike
from fanic.cylinder_sites.common.responses import render_html_template
from fanic.cylinder_sites.common.responses import text_error
from fanic.cylinder_sites.common.session import current_user
from fanic.cylinder_sites.fanicsite.user.profile_get_helpers import (
    display_name_status as _display_name_status,
)
from fanic.cylinder_sites.fanicsite.user.profile_get_helpers import (
    onboarding_status as _onboarding_status,
)
from fanic.cylinder_sites.fanicsite.user.profile_get_helpers import (
    preference_status as _preference_status,
)
from fanic.cylinder_sites.fanicsite.user.profile_get_helpers import (
    profile_visibility as _profile_visibility,
)
from fanic.cylinder_sites.fanicsite.user.profile_get_helpers import (
    recent_history_html as _recent_history_html,
)
from fanic.cylinder_sites.fanicsite.user.profile_get_helpers import (
    theme_status as _theme_status,
)
from fanic.cylinder_sites.profile_shared import render_bookmarks_html
from fanic.cylinder_sites.profile_shared import render_fanart_html
from fanic.cylinder_sites.profile_shared import render_profile_shared_sections
from fanic.cylinder_sites.profile_shared import render_uploaded_works_html
from fanic.repository.fanart import list_fanart_items_by_uploader
from fanic.repository.users import get_local_user
from fanic.repository.users import get_user_theme_preference
from fanic.repository.users import list_recent_reading_history
from fanic.repository.users import list_user_bookmarks
from fanic.repository.users import user_prefers_explicit
from fanic.repository.users import user_prefers_mature
from fanic.repository.users import user_requires_onboarding
from fanic.repository.works import can_view_work
from fanic.repository.works import list_work_comments
from fanic.repository.works import list_works_by_uploader
from fanic.repository.works import work_kudos_count
from fanic.settings import get_settings


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    if request.path != "/user/profile":
        return text_error(response, "Not found", 404)

    username = current_user(request)
    save_msg = request.args.get("msg", "").strip()
    pref_status = _preference_status(save_msg)
    display_name_status = _display_name_status(save_msg)
    theme_status = _theme_status(save_msg)
    onboarding_status = _onboarding_status(save_msg, requires_onboarding=False)

    if username is None:
        shared_sections_html = render_profile_shared_sections(
            {
                "__PROFILE_UPLOADED_WORKS_HIDDEN_ATTR__": "hidden",
                "__PROFILE_UPLOADED_WORKS_HTML__": "",
                "__PROFILE_FANART_HIDDEN_ATTR__": "hidden",
                "__PROFILE_FANART_HTML__": "",
                "__PROFILE_BOOKMARKS_HIDDEN_ATTR__": "hidden",
                "__PROFILE_BOOKMARKS_HTML__": "",
            }
        )
        replacements = {
            "__PROFILE_PAGE_TITLE__": "FANIC Profile",
            "__PROFILE_CARD_TITLE__": "Your Profile",
            "__PROFILE_CARD_SUBTITLE__": "This page shows your current FANIC session state.",
            "__PROFILE_SUBTITLE_HIDDEN_ATTR__": "",
            "__PROFILE_STATUS__": "Not logged in.",
            "__PROFILE_STATUS_CLASS__": "error",
            "__PROFILE_STATUS_HIDDEN_ATTR__": "",
            "__PROFILE_ACCOUNT_SUMMARY_HIDDEN_ATTR__": "",
            "__PROFILE_APPEARANCE_HIDDEN_ATTR__": "",
            "__PROFILE_DETAILS__": 'Use <a href="/account/login">Login</a> to sign in.',
            "__PROFILE_PUBLIC_LINK_HIDDEN_ATTR__": "hidden",
            "__PROFILE_PUBLIC_HREF__": "",
            "__PROFILE_IMMUTABLE_PUBLIC_LINK_HIDDEN_ATTR__": "hidden",
            "__PROFILE_IMMUTABLE_PUBLIC_HREF__": "",
            "__PROFILE_SETTINGS_HIDDEN_ATTR__": "hidden",
            "__PROFILE_ONBOARDING_HIDDEN_ATTR__": "hidden",
            "__PROFILE_DISPLAY_NAME_VALUE__": "",
            "__PROFILE_IS_OVER_18_YES_SELECTED_ATTR__": "",
            "__PROFILE_IS_OVER_18_NO_SELECTED_ATTR__": "",
            "__PROFILE_ONBOARDING_STATUS__": onboarding_status.text,
            "__PROFILE_ONBOARDING_STATUS_CLASS__": onboarding_status.css_class,
            "__PROFILE_ONBOARDING_STATUS_HIDDEN_ATTR__": onboarding_status.hidden_attr,
            "__PROFILE_PREFS_HIDDEN_ATTR__": "hidden",
            "__PROFILE_DISPLAY_NAME_STATUS__": display_name_status.text,
            "__PROFILE_DISPLAY_NAME_STATUS_CLASS__": display_name_status.css_class,
            "__PROFILE_DISPLAY_NAME_STATUS_HIDDEN_ATTR__": display_name_status.hidden_attr,
            "__PROFILE_VIEW_MATURE_CHECKED_ATTR__": "",
            "__PROFILE_VIEW_EXPLICIT_CHECKED_ATTR__": "",
            "__PROFILE_PREF_STATUS__": pref_status.text,
            "__PROFILE_PREF_STATUS_CLASS__": pref_status.css_class,
            "__PROFILE_PREF_STATUS_HIDDEN_ATTR__": pref_status.hidden_attr,
            "__PROFILE_THEME_FORM_HIDDEN_ATTR__": "",
            "__PROFILE_CUSTOM_THEME_ENABLED_CHECKED_ATTR__": "",
            "__PROFILE_THEME_STATUS__": theme_status.text,
            "__PROFILE_THEME_STATUS_CLASS__": theme_status.css_class,
            "__PROFILE_THEME_STATUS_HIDDEN_ATTR__": theme_status.hidden_attr,
            "__PROFILE_HISTORY_HIDDEN_ATTR__": "hidden",
            "__PROFILE_HISTORY_LIMIT__": "0",
            "__PROFILE_HISTORY_HTML__": "",
            "__PROFILE_SHARED_SECTIONS__": shared_sections_html,
        }
    else:
        requires_onboarding = user_requires_onboarding(username)
        if requires_onboarding:
            response.status_code = 303
            response.content_type = "text/plain; charset=utf-8"
            response.headers["Location"] = "/user/onboarding?msg=onboarding-required"
            response.set_data("See Other: /user/onboarding?msg=onboarding-required")
            return response
        local_user = get_local_user(username)
        display_name = username
        is_over_18: bool | None = None
        if local_user is not None:
            display_name = local_user["display_name"]
            is_over_18 = local_user["is_over_18"]

        history_limit = get_settings().profile_history_limit
        recent_history = list_recent_reading_history(username, limit=history_limit)
        uploaded_works_raw = list_works_by_uploader(username)
        uploaded_works: list[dict[str, object]] = []
        for work in uploaded_works_raw:
            work_id = str(work.get("id", "")).strip()
            work_with_counts: dict[str, object] = dict(work)
            if work_id:
                work_with_counts["kudos_count"] = work_kudos_count(work_id)
                work_with_counts["comments_count"] = len(list_work_comments(work_id))
            else:
                work_with_counts["kudos_count"] = 0
                work_with_counts["comments_count"] = 0
            uploaded_works.append(work_with_counts)
        raw_bookmarks = list_user_bookmarks(username)
        fanart_items = list_fanart_items_by_uploader(username, limit=30)
        visible_bookmarks = [
            row for row in raw_bookmarks if can_view_work(username, {"rating": row.get("rating", "Not Rated")})
        ]
        shared_sections_html = render_profile_shared_sections(
            {
                "__PROFILE_UPLOADED_WORKS_HIDDEN_ATTR__": "hidden" if requires_onboarding else "",
                "__PROFILE_UPLOADED_WORKS_HTML__": render_uploaded_works_html(
                    uploaded_works,
                    include_stats=True,
                ),
                "__PROFILE_FANART_HIDDEN_ATTR__": "hidden" if requires_onboarding else "",
                "__PROFILE_FANART_HTML__": render_fanart_html(
                    username,
                    display_name,
                    fanart_items,
                    profile_kind="private",
                ),
                "__PROFILE_BOOKMARKS_HIDDEN_ATTR__": "hidden" if requires_onboarding else "",
                "__PROFILE_BOOKMARKS_HTML__": render_bookmarks_html(visible_bookmarks),
            }
        )
        view_mature_checked = "checked" if user_prefers_mature(username) else ""
        view_explicit_checked = "checked" if user_prefers_explicit(username) else ""
        theme_preference = get_user_theme_preference(username)
        custom_theme_checked = "checked" if theme_preference["enabled"] else ""
        visibility = _profile_visibility(requires_onboarding)
        onboarding_status = _onboarding_status(save_msg, requires_onboarding=requires_onboarding)

        over_18_yes_selected = "selected" if is_over_18 is True else ""
        over_18_no_selected = "selected" if is_over_18 is False else ""
        replacements = {
            "__PROFILE_PAGE_TITLE__": "FANIC Profile",
            "__PROFILE_CARD_TITLE__": "Your Profile",
            "__PROFILE_CARD_SUBTITLE__": "This page shows your current FANIC session state.",
            "__PROFILE_SUBTITLE_HIDDEN_ATTR__": "",
            "__PROFILE_STATUS__": "Logged in.",
            "__PROFILE_STATUS_CLASS__": "",
            "__PROFILE_STATUS_HIDDEN_ATTR__": "",
            "__PROFILE_ACCOUNT_SUMMARY_HIDDEN_ATTR__": visibility.account_summary_hidden_attr,
            "__PROFILE_APPEARANCE_HIDDEN_ATTR__": visibility.appearance_hidden_attr,
            "__PROFILE_DETAILS__": f"Display name: {escape(display_name)}",
            "__PROFILE_PUBLIC_LINK_HIDDEN_ATTR__": visibility.public_link_hidden_attr,
            "__PROFILE_PUBLIC_HREF__": f"/users/{escape(display_name)}",
            "__PROFILE_IMMUTABLE_PUBLIC_LINK_HIDDEN_ATTR__": visibility.immutable_public_link_hidden_attr,
            "__PROFILE_IMMUTABLE_PUBLIC_HREF__": f"/users/{escape(display_name)}",
            "__PROFILE_SETTINGS_HIDDEN_ATTR__": "",
            "__PROFILE_ONBOARDING_HIDDEN_ATTR__": visibility.onboarding_hidden_attr,
            "__PROFILE_DISPLAY_NAME_VALUE__": escape(display_name),
            "__PROFILE_IS_OVER_18_YES_SELECTED_ATTR__": over_18_yes_selected,
            "__PROFILE_IS_OVER_18_NO_SELECTED_ATTR__": over_18_no_selected,
            "__PROFILE_ONBOARDING_STATUS__": onboarding_status.text,
            "__PROFILE_ONBOARDING_STATUS_CLASS__": onboarding_status.css_class,
            "__PROFILE_ONBOARDING_STATUS_HIDDEN_ATTR__": onboarding_status.hidden_attr,
            "__PROFILE_PREFS_HIDDEN_ATTR__": "",
            "__PROFILE_DISPLAY_NAME_STATUS__": display_name_status.text,
            "__PROFILE_DISPLAY_NAME_STATUS_CLASS__": display_name_status.css_class,
            "__PROFILE_DISPLAY_NAME_STATUS_HIDDEN_ATTR__": display_name_status.hidden_attr,
            "__PROFILE_VIEW_MATURE_CHECKED_ATTR__": view_mature_checked,
            "__PROFILE_VIEW_EXPLICIT_CHECKED_ATTR__": view_explicit_checked,
            "__PROFILE_PREF_STATUS__": pref_status.text,
            "__PROFILE_PREF_STATUS_CLASS__": pref_status.css_class,
            "__PROFILE_PREF_STATUS_HIDDEN_ATTR__": pref_status.hidden_attr,
            "__PROFILE_THEME_FORM_HIDDEN_ATTR__": visibility.theme_form_hidden_attr,
            "__PROFILE_CUSTOM_THEME_ENABLED_CHECKED_ATTR__": custom_theme_checked,
            "__PROFILE_THEME_STATUS__": theme_status.text,
            "__PROFILE_THEME_STATUS_CLASS__": theme_status.css_class,
            "__PROFILE_THEME_STATUS_HIDDEN_ATTR__": theme_status.hidden_attr,
            "__PROFILE_HISTORY_HIDDEN_ATTR__": visibility.history_hidden_attr,
            "__PROFILE_HISTORY_LIMIT__": escape(str(history_limit)),
            "__PROFILE_HISTORY_HTML__": _recent_history_html(recent_history),
            "__PROFILE_SHARED_SECTIONS__": shared_sections_html,
        }

    return render_html_template(request, response, "profile.html", replacements)
