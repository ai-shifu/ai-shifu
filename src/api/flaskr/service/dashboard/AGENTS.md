# Backend Service: dashboard

This module owns dashboard reporting routes, DTOs, and aggregate metrics for
admin and course-level reporting surfaces.

Entry files in this directory: `routes.py`, `funcs.py`, `dtos.py`.

## Do

- Keep dashboard DTO shapes stable because frontend admin pages depend on the
  serialized field names and formatting.
- Preserve centralized money, ratio, and percentage formatting in the
  dashboard helper layer.
- Treat dashboard queries as reporting logic with access-control expectations,
  not as general-purpose business mutations.

## Avoid

- Do not move formatting logic into routes or frontend pages when the backend
  DTO contract already defines the presentation shape.
- Do not add heavy reporting queries without checking query scope, pagination,
  and filter defaults.
- Do not widen dashboard data access without preserving existing permission or
  audience assumptions.

## Tests

`cd src/api && pytest tests/service/dashboard/ -q`
