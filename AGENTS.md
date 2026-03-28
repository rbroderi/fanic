# AGENTS.md

## Python Coalescing Style Guide

Use explicit ternary expressions for fallback/defaulting in Python code.

- Preferred: `x = y if y else z`
- Avoid: `x = y or z`

Apply this rule to:
- Assignments
- Return expressions
- Argument values

Keep boolean logic unchanged when it is actual control-flow logic (not coalescing):
- Keep forms like `if a or b:`

## Examples

- Preferred: `data = metadata if metadata else {}`
- Preferred: `name = raw_name if raw_name else "untitled"`
- Preferred: `return value if value else fallback`
- Avoid: `data = metadata or {}`
- Avoid: `name = raw_name or "untitled"`
- Avoid: `return value or fallback`

## Auto-Fix Expectation

When editing Python files, also scan nearby changes for coalescing-style fallbacks and normalize them to the preferred ternary form in the same edit.

- Scope: touched lines and closely related statements in the same function/module
- Do not rewrite boolean control flow such as `if a or b:`

## Import Re-Export Style

When importing symbols intended as module-level API exports, use explicit same-name alias imports.

- Preferred: `from fanic.cylinder_main import create_app as create_app`
- Preferred: `from fanic.cylinder_main import serve as serve`
- Avoid: `from fanic.cylinder_main import create_app, serve`

Apply this pattern consistently across the project for these API-style imports.

## File-Based Routing Standard

Treat file-based routing as a strict project convention.

- Route handler file and folder structure must mirror URL structure.
- Admin routes must live under `fanicsite/admin/` in the filesystem.
- Avoid adding handlers in unrelated locations and checking a different route path in code.

Examples:

- `/admin/users` -> `src/fanic/cylinder_sites/fanicsite/admin/users.ex.get.py` and `.../users.ex.post.py`
- `/admin/reports` -> `src/fanic/cylinder_sites/fanicsite/admin/reports.ex.get.py` and `.../reports.ex.post.py`
- `/users/{username}` -> `src/fanic/cylinder_sites/fanicsite/users.ex.get.py`

When moving or adding routes:

- Move files to match the URL tree rather than keeping legacy file locations.
- Update tests to import the new file paths.
- Prefer lightweight path assertions only as safety checks, not as a substitute for filesystem-route alignment.

## Site Cleanup Standards

Treat the following as project-wide style standards for route/helper cleanup work.

### Finite Choice Values: Use `StrEnum`

When a module has a fixed set of string choices (status values, issue types, roles), model them as `StrEnum` instead of ad-hoc tuple/dict constants.

- Put labels on enum values when labels are user-facing.
- Add helper methods/classmethods for wire-format parsing where needed.
- Prefer explicit conversion helpers over scattered string literals.

Patterns:

- Preferred: `name_to_dash()` for enum-name to wire-value conversion.
- Preferred: `from_dash_name()` or `from_value()` for parsing inbound values.
- Preferred: centralized helpers like `normalize_*`, `*_label`, `*_options_html`.
- Avoid: repeated inline string checks for the same finite set.

### Message/Action Dispatch: Prefer `match`

For single-variable branch dispatch (for example `msg` or `action` maps), prefer `match`/`case` over long `if/elif` chains.

- Scope: route message mapping helpers and similar dispatch utilities.
- Keep fallback/default behavior in `case _`.

### Structured Multi-Field Returns: Use Dataclasses

When returning multiple named fields (especially status payloads used by templates), use a small dataclass instead of anonymous tuples.

- Preferred: small frozen dataclass with explicit field names.
- Example fields: `text`, `css_class`, `hidden_attr`.
- Avoid: tuple returns like `(text, status_class, hidden_attr)` for semantic payloads.

### Large HTML Assembly: Use Dedented Triple-Quoted f-Strings

For large HTML blocks, prefer multiline f-strings with `textwrap.dedent(...).strip()`.

- Preferred: readable block templates in source.
- Avoid: long `"..." + "..." + f"..."` concatenation chains.
- Preserve explicit `escape(...)` calls for user/data fields.

### Dynamic Route Module Caveat

Route modules are dynamically loaded in tests. If a route module defines dataclasses, avoid patterns that can cause annotation-resolution import errors under dynamic loading.

- Keep dataclass route modules compatible with the test loader behavior.
- If needed, avoid postponed-annotation patterns that break dataclass processing in this environment.

## Protocol Runtime Checkability Standard

When defining `Protocol` types, always append the `@runtime_checkable` decorator.

- Preferred:
	- `from typing import Protocol, runtime_checkable`
	- `@runtime_checkable`
	- `class StartResponseProtocol(Protocol): ...`
- Avoid:
	- Protocol classes without `@runtime_checkable`

Rationale:

- Runtime validators in this project may perform `isinstance(...)` checks on protocol-typed annotations.
- Non-runtime-checkable protocols can trigger runtime type-checking errors.
