# Remove deprecated Pydantic `Field(required=...)` metadata

## Purpose / Big Picture

Remove deprecated `required` keyword arguments from backend Pydantic `Field`
declarations without changing which fields are required, accepted values,
defaults, aliases, serialized payloads, SSE events, or OpenAPI contracts. The
work lands in two focused pull requests so admin DTOs can be verified before
runtime learning and public DTOs are touched.

## Progress

- [x] 2026-09-21 18:00 CST: Counted 737 deprecated declarations across eight
  DTO files: 621 admin declarations and 116 runtime/public declarations.
- [x] 2026-09-21 18:15 CST: Captured the complete pre-migration field, validation schema,
  serialization schema, and registered Swagger baseline for the admin batch.
- [x] 2026-09-21 18:25 CST: Added an AST-based staged regression gate with an explicit temporary
  allowlist for the 116 declarations assigned to the second pull request.
- [x] 2026-09-21 18:30 CST: Removed the 621 admin `required` keyword arguments without changing any
  other field declaration.
- [x] 2026-09-21 18:45 CST: Compared the complete post-migration contracts and ran representative
  DTO, route, JSON, and OpenAPI tests for the admin modules.
- [x] 2026-09-21 21:00 CST: In a second pull request, removed the remaining 116 declarations, removed
  the temporary allowlist, and enable the repository-wide zero-residual gate.

## Surprises & Discoveries

- Pydantic 2.13.5 treats `required=` as deprecated extra JSON Schema metadata;
  it does not decide whether a field may be omitted.
- All 737 occurrences are confined to eight DTO modules. CLI and config
  `required=` arguments are unrelated and must not be changed.

## Decision Log

- Decision: Only remove the Pydantic `Field` keyword named `required`.
  Rationale: omission is determined by a default or default factory, while the
  annotation determines accepted values. Changing annotations, ellipses,
  defaults, factories, or aliases would alter the API contract.
- Decision: Split at the admin/runtime boundary. Rationale: the first batch is
  large but operationally cohesive, while learning/SSE DTOs warrant their own
  regression run.
- Decision: Use AST enforcement rather than text matching. Rationale: it must
  detect multiline calls and qualified or aliased `Field` calls without
  confusing Click/config arguments.

## Outcomes & Retrospective

The first batch removed 621 deprecated keyword arguments from 79 admin DTO
models. Complete before/after comparison preserved field requiredness, types,
defaults, factories, aliases, both Pydantic Schema modes, and registered
Swagger standard required arrays. The only Schema change was removal of the
deprecated boolean property metadata. Focused admin route and DTO regression
tests passed; one database test failed only while multiple database suites ran
concurrently and passed on isolated rerun.

The second batch removed the remaining 116 keyword arguments from 27 learning,
course, and user DTO models. The same full contract comparison passed, and the
AST guard now enforces zero `Field(required=...)` declarations across backend
services. Focused DTO and SSE tests, all 643 shifu tests, and all 632 user tests
passed. The learn suite passed 1,250 tests with 6 skips; its 37 failures all
exercise an unchanged live-follow-up route that assigns Flask's read-only
`Request.max_content_length` property in the local dependency version, outside
this migration's files and behavior.

## Context and Orientation

The first batch owns these modules:

- `src/api/flaskr/service/dashboard/dtos.py`
- `src/api/flaskr/service/order/admin_dtos.py`
- `src/api/flaskr/service/promo/admin_dtos.py`
- `src/api/flaskr/service/shifu/admin_dtos_courses.py`
- `src/api/flaskr/service/shifu/admin_dtos_users.py`

The second batch owns `shifu/dtos.py`, `learn/learn_dtos.py`, and
`user/dtos.py`. DTOs serialize through a mix of Pydantic, hand-written
`__json__()`, `AutoJsonMixin`, the shared `fmt()` sink, SSE emitters, and the
repository Swagger registry, so `model_dump()` alone is not sufficient.

## Plan of Work

Before editing, enumerate every Pydantic model defined in the first-batch
modules and capture every field's `is_required()`, annotation, default,
default factory, validation alias, and serialization alias. Capture both
validation and serialization JSON Schema plus registered Swagger schemas.

Add a small AST checker that rejects `required=` in cleaned modules and
requires the second-batch temporary allowlist to match exact file counts. Then
remove only the keyword argument in the first-batch modules. Compare the full
post-edit model and Schema state against the baseline. The only permitted
Schema difference is removal of a boolean property-level `required` key; all
standard list-valued `required` arrays at every nesting level must remain.

Run representative behavior tests for missing fields, defaults, invalid
inputs, nested DTOs, pagination, enums, money, UTC datetime serialization,
actual route JSON, and actual generated OpenAPI. No real credit or package
grant is performed.

## Concrete Steps

1. Create `chore/pydantic-admin-dto-compat` from current `main`.
2. Capture the first-batch baseline in a disposable local artifact.
3. Add and test the staged AST checker.
4. Remove 621 first-batch keyword arguments mechanically.
5. Run the complete contract comparator and fresh-process warning import.
6. Run focused service tests, Ruff/format checks, developer-tool validation,
   architecture boundaries, unit-of-work checks, and diff review.
7. Commit and open the first pull request after user authorization.

## Validation and Acceptance

- All first-batch Pydantic models preserve requiredness, annotations,
  defaults, factories, and validation/serialization aliases.
- Validation and serialization schemas differ only by removal of deprecated
  boolean property metadata; no list-valued `required` array changes.
- Actual Swagger output preserves all standard required arrays.
- Representative model validation, `model_dump()`, `__json__()` / `fmt()`,
  route JSON, SSE, money, datetime, enum, nested, and pagination behavior is
  unchanged.
- Fresh subprocess import of every first-batch module emits no warning for
  Pydantic `Field(required=...)`.
- The AST checker reports zero first-batch declarations and exactly the
  documented temporary second-batch inventory; warnings are not suppressed.

## Idempotence and Recovery

The source rewrite only deletes named keyword arguments and can be rerun
safely after the AST inventory reports no target in a cleaned file. The local
baseline is disposable and can be regenerated from the parent commit. If a
contract comparison reports any other difference, restore only that field's
declaration and investigate instead of weakening the comparator.

## Interfaces and Dependencies

This work uses Pydantic 2.13.5, the shared Swagger registry in
`flaskr.common.swagger`, Flask JSON formatting in `flaskr.route.common.fmt`,
and the existing admin route and DTO pytest suites. It has no database schema,
external provider, frontend analytics, or environment-variable dependency.
