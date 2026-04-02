from enum import StrEnum
from html import escape


class DashNameEnum(StrEnum):
    def name_to_dash(self) -> str:
        return self.name.lower().replace("_", "-")

    @classmethod
    def from_dash_name[_DashNameEnumT: DashNameEnum](
        cls: type[_DashNameEnumT], dash_name: str
    ) -> _DashNameEnumT | None:
        normalized = dash_name.strip()
        for item in cls:
            if item.name_to_dash() == normalized:
                return item
        return None


def options_html(
    enum_cls: type[DashNameEnum],
    *,
    selected_dash_name: str,
    fallback: DashNameEnum | None = None,
) -> str:
    selected = enum_cls.from_dash_name(selected_dash_name)
    resolved_selected = selected if selected is not None else fallback
    selected_value = resolved_selected.name_to_dash() if resolved_selected is not None else ""

    options: list[str] = []
    for item in enum_cls:
        dash_name = item.name_to_dash()
        selected_attr = " selected" if dash_name == selected_value else ""
        options.append(f'<option value="{escape(dash_name)}"{selected_attr}>{escape(str(item))}</option>')
    return "".join(options)
