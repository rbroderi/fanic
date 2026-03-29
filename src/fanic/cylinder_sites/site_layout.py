from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SiteHeaderParts:
    nav_links: str
    meta_html: str
    extra_html: str


_NAV_LINKS_BY_TEMPLATE: dict[str, str] = {
    "cbz-format.html": '__ADMIN_REPORTS_LINK__<a href="/cbz-format" aria-current="page">CBZ SPEC INFO</a>',
    "dmca.html": '__ADMIN_REPORTS_LINK__<a href="/dmca" aria-current="page">DMCA</a>',
    "fanart-gallery.html": '<a href="/?view=fanart" aria-current="page">Browse fanart</a><a href="/">Browse comics</a>',
    "fanart-upload.html": '<a href="/?view=fanart">Browse fanart</a><a href="/">Browse comics</a>',
    "faq.html": '__ADMIN_REPORTS_LINK__<a href="/cbz-format">CBZ SPEC INFO</a><a href="/faq" aria-current="page">FAQ</a>',
    "feedback.html": '__ADMIN_REPORTS_LINK__<a href="/feedback" aria-current="page">Feedback</a>',
    "ingest.html": '__ADMIN_REPORTS_LINK__<a href="/cbz-format">CBZ SPEC INFO</a>',
    "login.html": '__ADMIN_REPORTS_LINK__<a href="/account/login" aria-current="page">Login</a>',
    "notification.html": '__ADMIN_REPORTS_LINK__<a href="/user/profile">Profile</a><a href="/user/notifications" aria-current="page">Notification</a>',
    "profile.html": '__ADMIN_REPORTS_LINK__<a href="/user/profile" aria-current="page">Profile</a>',
    "profile-public.html": '__ADMIN_REPORTS_LINK__<a href="/user/profile">Profile</a>',
    "terms.html": '__ADMIN_REPORTS_LINK__<a href="/cbz-format">CBZ SPEC INFO</a><a href="/terms" aria-current="page">Terms</a>',
}

_META_BY_TEMPLATE: dict[str, str] = {
    "fanart-gallery.html": '<p class="profile-meta">Fanart Gallery</p>',
    "fanart-upload.html": '<p class="profile-meta">Fanart Upload</p>',
}

_EXTRA_BY_TEMPLATE: dict[str, str] = {
    "index.html": (
        '<section class="home-tabs-shell" aria-label="Browse views tabs">'
        '<nav class="browse-tabs" aria-label="Browse views">'
        '<a href="/?view=comics" __COMICS_TAB_CURRENT__>Comics</a>'
        '<a href="/?view=fanart" __FANART_TAB_CURRENT__>Fanart</a>'
        "</nav>"
        "</section>"
        '<p class="profile-meta" __VIEW_TAGLINE_HIDDEN_ATTR__>+Fanart</p>'
    )
}


def site_header_parts_for_template(template_name: str) -> SiteHeaderParts:
    nav_links = _NAV_LINKS_BY_TEMPLATE.get(template_name)
    nav_result = nav_links if nav_links is not None else "__ADMIN_REPORTS_LINK__"

    meta_html = _META_BY_TEMPLATE.get(template_name)
    if meta_html is None:
        meta_result = (
            "" if template_name in {"index.html", "reader.html"} else '<p class="profile-meta">__SITE_TAGLINE__</p>'
        )
    else:
        meta_result = meta_html

    extra_html = _EXTRA_BY_TEMPLATE.get(template_name)
    extra_result = extra_html if extra_html is not None else ""
    return SiteHeaderParts(
        nav_links=nav_result,
        meta_html=meta_result,
        extra_html=extra_result,
    )
