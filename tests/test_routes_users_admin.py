from collections.abc import Callable
from types import ModuleType
from typing import Any
from typing import Protocol


class ResponseLike(Protocol):
    status_code: int
    content_type: str
    headers: dict[str, str]

    def set_data(self, data: str | bytes) -> None: ...


def _always_true(*_args: Any) -> bool:
    return True


def _current_user_alice(_: Any) -> str:
    return "alice"


def _current_user_admin(_: Any) -> str:
    return "admin"


def _role_user(_: str | None) -> str:
    return "user"


def _role_admin(_: str | None) -> str:
    return "admin"


def _role_superadmin(_: str | None) -> str:
    return "superadmin"


def _local_user_alice(_: str) -> dict[str, Any]:
    return {
        "username": "alice",
        "display_name": "Alice",
        "email": "alice@example.com",
        "role": "admin",
        "active": True,
        "created_at": "2026-03-22T00:00:00Z",
    }


def _local_user_bob(_: str) -> dict[str, Any]:
    return {
        "username": "bob",
        "display_name": "Bob",
        "email": None,
        "role": "user",
        "active": True,
        "created_at": "2026-03-22T00:00:00Z",
    }


def _delete_user_success(_: str) -> bool:
    return True


def test_users_get_dashboard_forbidden_for_non_admin(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: Any,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/admin/users.ex.get.py",
        "fanicsite_users_ex_get_dashboard_forbidden_test",
    )

    monkeypatch.setattr(module, "current_user", _current_user_alice)
    monkeypatch.setattr(module, "role_for_user", _role_user)

    request = dummy_request(path="/admin/users", args={})
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 403


def test_users_get_dashboard_uses_admin_template(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: Any,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/admin/users.ex.get.py",
        "fanicsite_users_ex_get_dashboard_template_test",
    )

    monkeypatch.setattr(module, "current_user", _current_user_admin)
    monkeypatch.setattr(module, "role_for_user", _role_superadmin)

    def fake_list_local_users(**_kwargs: Any) -> list[dict[str, Any]]:
        return [
            {
                "username": "alice",
                "display_name": "Alice",
                "email": "alice@example.com",
                "role": "user",
                "active": True,
                "created_at": "2026-03-22T00:00:00Z",
            }
        ]

    monkeypatch.setattr(
        module,
        "list_local_users",
        fake_list_local_users,
    )
    monkeypatch.setattr(module, "count_local_users", lambda: 1)

    captured: dict[str, Any] = {}

    def fake_render_html_template(
        request: Any,
        response: ResponseLike,
        template_name: str,
        replacements: dict[str, str],
    ) -> ResponseLike:
        _ = request
        captured["template_name"] = template_name
        captured["rows"] = replacements["__USERS_ROWS_HTML__"]
        response.set_data("ok")
        return response

    monkeypatch.setattr(module, "render_html_template", fake_render_html_template)

    request = dummy_request(path="/admin/users", args={})
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 200
    assert captured["template_name"] == "users-admin.html"
    assert "alice" in str(captured["rows"])


def test_users_post_forbidden_for_non_admin(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: Any,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/admin/users.ex.post.py",
        "fanicsite_users_ex_post_forbidden_test",
    )

    monkeypatch.setattr(module, "enforce_https_termination", _always_true)
    monkeypatch.setattr(module, "validate_csrf", _always_true)
    monkeypatch.setattr(module, "current_user", _current_user_alice)
    monkeypatch.setattr(module, "role_for_user", _role_user)

    request = dummy_request(path="/admin/users", method="POST", form={"user_action": "create"})
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 403


def test_users_post_create_user_redirects_created(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: Any,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/admin/users.ex.post.py",
        "fanicsite_users_ex_post_create_test",
    )

    monkeypatch.setattr(module, "enforce_https_termination", _always_true)
    monkeypatch.setattr(module, "validate_csrf", _always_true)
    monkeypatch.setattr(module, "current_user", _current_user_admin)
    monkeypatch.setattr(module, "role_for_user", _role_admin)

    captured: dict[str, Any] = {}

    def fake_create_user(
        username: str,
        *,
        display_name: str,
        email: str | None,
        role: str,
        active: bool,
    ) -> None:
        captured["username"] = username
        captured["display_name"] = display_name
        captured["email"] = email
        captured["role"] = role
        captured["active"] = active

    monkeypatch.setattr(module, "create_user", fake_create_user)

    request = dummy_request(
        path="/admin/users",
        method="POST",
        form={
            "user_action": "create",
            "username": "bob",
            "display_name": "",
            "email": "",
            "role": "user",
            "active": "1",
        },
    )
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 303
    assert result.headers.get("Location") == "/admin/users?msg=created"
    assert captured["username"] == "bob"
    assert captured["display_name"] == "bob"
    assert captured["email"] is None
    assert captured["role"] == "user"
    assert captured["active"] is True


def test_users_post_blocks_self_deactivation(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: Any,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/admin/users.ex.post.py",
        "fanicsite_users_ex_post_self_block_test",
    )

    monkeypatch.setattr(module, "enforce_https_termination", _always_true)
    monkeypatch.setattr(module, "validate_csrf", _always_true)
    monkeypatch.setattr(module, "current_user", _current_user_alice)
    monkeypatch.setattr(module, "role_for_user", _role_admin)
    monkeypatch.setattr(
        module,
        "get_local_user",
        _local_user_alice,
    )

    request = dummy_request(
        path="/admin/users",
        method="POST",
        form={"user_action": "set-active", "target_username": "alice", "active": "0"},
    )
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 303
    assert result.headers.get("Location") == "/admin/users?msg=self-action-blocked"


def test_users_post_remove_user_redirects_removed(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: Any,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/admin/users.ex.post.py",
        "fanicsite_users_ex_post_remove_test",
    )

    monkeypatch.setattr(module, "enforce_https_termination", _always_true)
    monkeypatch.setattr(module, "validate_csrf", _always_true)
    monkeypatch.setattr(module, "current_user", _current_user_admin)
    monkeypatch.setattr(module, "role_for_user", _role_admin)
    monkeypatch.setattr(
        module,
        "get_local_user",
        _local_user_bob,
    )
    monkeypatch.setattr(module, "delete_user", _delete_user_success)

    request = dummy_request(
        path="/admin/users",
        method="POST",
        form={"user_action": "remove", "target_username": "bob"},
    )
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 303
    assert result.headers.get("Location") == "/admin/users?msg=removed"


def test_users_post_admin_cannot_promote_superadmin(
    load_route_module: Callable[[str, str], ModuleType],
    dummy_request: Callable[..., Any],
    dummy_response: Callable[[], ResponseLike],
    monkeypatch: Any,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/admin/users.ex.post.py",
        "fanicsite_users_ex_post_promote_superadmin_forbidden_test",
    )

    monkeypatch.setattr(module, "enforce_https_termination", _always_true)
    monkeypatch.setattr(module, "validate_csrf", _always_true)
    monkeypatch.setattr(module, "current_user", _current_user_admin)
    monkeypatch.setattr(module, "role_for_user", _role_admin)
    monkeypatch.setattr(
        module,
        "get_local_user",
        _local_user_bob,
    )

    request = dummy_request(
        path="/admin/users",
        method="POST",
        form={
            "user_action": "set-role",
            "target_username": "bob",
            "role": "superadmin",
        },
    )
    response = dummy_response()
    result = module.main(request, response)

    assert result.status_code == 303
    assert result.headers.get("Location") == "/admin/users?msg=forbidden-action"
