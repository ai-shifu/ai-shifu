# Backend Service: feedback

This module owns user feedback submission persistence and helper logic for
collecting qualitative product feedback.

Entry files in this directory: `funs.py`, `models.py`.

## Do

- Keep feedback submission validation close to the persistence helper so
  callers do not invent divergent checks.
- Preserve the link between feedback content, user identity, and any optional
  contact information captured with the report.
- Treat this service as a write-oriented boundary and add explicit query
  helpers before expanding read behavior.

## Avoid

- Do not duplicate feedback persistence logic in route handlers or frontend
  adapters.
- Do not accept new feedback payload fields without updating storage,
  validation, and any downstream notifications together.
- Do not ignore the existing file naming quirk of `funs.py`; follow local
  structure unless you are deliberately refactoring it.

## Tests

`cd src/api && pytest tests/service/feedback/ -q`
