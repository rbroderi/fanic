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
