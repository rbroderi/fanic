# FANIC Architecture Style Guide

## Route, Service, Repository Boundaries

- Route modules should focus on HTTP concerns only:
  - path matching
  - auth/session checks
  - request parsing
  - response rendering and redirects
- Domain/business rules should live in service functions, not route modules.
- Repository modules should perform persistence operations and row mapping only.

## Route Module Rules

- Keep route handlers short and dispatch to focused helper functions.
- Prefer small action handlers over long if/elif chains for tail-based routing.
- Keep shared request helpers in common modules (for example non-empty checks
  and form list extraction).

## Service Layer Rules

- Add a service when logic combines:
  - authorization
  - validation
  - one or more repository operations
- Service return values should be explicit and structured (for example dataclass
  result objects).
- Keep service APIs independent from concrete HTTP request objects.

## Repository Rules

- Centralize row-to-typed-dict mapping in one internal mapper per row type.
- Reuse shared coercion helpers from fanic.type_coercion for numeric parsing.
- Keep SQL, mapping, and file side effects explicit and localized.

## Validation Rules

- Keep field-level validation helpers in shared modules under common.
- Avoid duplicating tiny validators across routes.
- Use explicit conversion/defaulting (prefer ternary style for coalescing
  defaults).

## Scripting Rules (Audit/Tooling)

- Keep CLI argument contracts consistent between just recipes and scripts.
- Avoid duplicate parsing behavior in wrappers and called scripts.
- Ensure script modes are semantically meaningful (avoid no-op mode flags).
