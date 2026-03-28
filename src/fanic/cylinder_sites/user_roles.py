from enum import StrEnum
from typing import Self


class ManagedUserRole(StrEnum):
    SUPERADMIN = "superadmin"
    ADMIN = "admin"
    USER = "user"

    def label(self) -> str:
        if self is ManagedUserRole.SUPERADMIN:
            return "Superadmin"
        if self is ManagedUserRole.ADMIN:
            return "Admin"
        return "User"

    @classmethod
    def from_value(cls, value: str) -> Self | None:
        normalized = value.strip().lower()
        for role in cls:
            if role.value == normalized:
                return role
        return None


def is_privileged_role(role_value: str) -> bool:
    role = ManagedUserRole.from_value(role_value)
    return role in {ManagedUserRole.SUPERADMIN, ManagedUserRole.ADMIN}
