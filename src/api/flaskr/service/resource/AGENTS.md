# Backend Service: resource

This module owns resource metadata and resource-usage persistence, currently
centered on the service data model layer.

Entry files in this directory: `models.py`.

## Do

- Keep resource and usage records aligned with business-key and index
  conventions because other modules may read them indirectly.
- Treat this directory as a data-model boundary until explicit service helpers
  or routes are introduced.
- Add new query or mutation helpers here instead of scattering raw resource
  table access through unrelated services.

## Avoid

- Do not let other modules invent incompatible meanings for resource rows or
  usage rows without updating the owning models.
- Do not grow hidden behavior in compiled artifacts or untracked files when
  the checked-in model layer is the source of truth.
- Do not skip migration review when resource columns or indexes move.

## Tests

Add focused regression tests under `src/api/tests/service/resource/` when
changing this service behavior.
