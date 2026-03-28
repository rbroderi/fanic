from fanic.cylinder_sites.common import STATIC_ROOT


def render_profile_shared_sections(replacements: dict[str, str]) -> str:
    html = (STATIC_ROOT / "profile-shared-sections.html").read_text(encoding="utf-8")
    for marker, value in replacements.items():
        html = html.replace(marker, value)
    return html
