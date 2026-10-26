# Backend Service: llm

This module owns thin LLM-facing HTTP route registration that should stay
aligned with the shared LiteLLM integration layer.

Entry files in this directory: `route.py`.

## Do

- Treat `src/api/flaskr/api/llm/__init__.py` as the shared provider
  integration layer and keep this service route-focused.
- Preserve OpenAI-compatible request and response expectations when proxying
  provider traffic.
- Add provider-specific behavior only when the shared wrapper cannot
  reasonably absorb it.

## Avoid

- Do not duplicate LiteLLM or provider-registration logic in this service
  subtree.
- Do not couple route behavior tightly to one vendor when multiple
  OpenAI-compatible providers must coexist.
- Do not expose provider secrets, base URLs, or unsupported internal error
  details in API responses.

## Tests

Add focused regression tests under `src/api/tests/service/llm/` when changing
this service behavior.
