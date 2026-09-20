# Backend Service: check_risk

This module owns risk-control persistence and text moderation checks used to
screen content before it proceeds through downstream flows.

Entry files in this directory: `funcs.py`, `models.py`.

## Do

- Keep moderation result persistence and provider interaction in the service
  helpers instead of scattering them across callers.
- Preserve business-key linkage between a risk decision and the content or
  request context that triggered it.
- Keep safe fallback behavior explicit when the upstream risk provider fails
  or times out.

## Avoid

- Do not let routes or unrelated services call providers directly and skip
  this normalization layer.
- Do not store partial moderation records without the context needed to audit
  the decision later.
- Do not silently downgrade failure behavior without documenting the new risk
  posture in tests and task notes.

## Tests

Add focused regression tests under `src/api/tests/service/check_risk/` when
changing this service behavior.
