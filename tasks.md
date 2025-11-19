# LiteLLM Migration Tasks

Goal: replace the current mix of direct `openai` clients + bespoke provider integrations with a LiteLLM-based abstraction without breaking existing streaming, telemetry, or provider coverage.

## Discovery & Design
- [x] Inventory every entry point that touches `flaskr.api.llm` (e.g., `src/api/flaskr/service/learn/context_v2.py`, `src/api/flaskr/service/learn/handle_input_ask.py`, `src/api/tests/test_llm.py`) and capture required behaviors (stream vs. non-stream, Langfuse span usage, error expectations).
- [x] Audit provider-specific helpers (`src/api/flaskr/api/llm/ernie.py`, `src/api/flaskr/api/llm/dify.py`) plus environment definitions in `src/api/flaskr/common/config.py` to decide which providers can move to LiteLLM vs. which must stay custom.
- [x] Draft the LiteLLM configuration strategy: map existing env vars (OPENAI/DEEPSEEK/QWEN/ERNIE/GLM/ARK/SILICON/etc.) to LiteLLM-compatible configs (final implementation stayed inline within `flaskr.api.llm` instead of adding a separate adapter module).

## Implementation
- [x] Update dependencies: add `litellm` to `src/api/requirements.txt`, remove the direct `openai` requirement, and ensure any transitive needs (e.g., pydantic) are satisfied.
- [x] Build a LiteLLM adapter layer (implemented directly inside `src/api/flaskr/api/llm/__init__.py`) responsible for initializing routers, registering per-provider configs, and exposing helpers for streaming completions + model listing.
- [x] Refactor `src/api/flaskr/api/llm/__init__.py` to route `invoke_llm`/`chat_llm` through the new adapter while preserving `LLMStreamResponse`, `LLMStreamUsage`, Langfuse instrumentation, and json-mode support.
- [x] Replace the per-provider `openai.Client` bootstrapping in `__init__.py` with LiteLLM-aware registration, keeping (or shimming) any providers that LiteLLM cannot cover yet (ERNIE legacy HTTP, Dify streaming) and documenting the fallback path.
- [x] Ensure `get_current_models` and config-driven model validation still work: populate lists from LiteLLM-friendly metadata or explicit mappings so that callers (e.g., `LLMSettings`) keep receiving the same choices.
- [x] Implement robust error handling around LiteLLM exceptions so `raise_error_with_args("server.llm.*")` still fires with helpful context and include telemetry-friendly metadata.

## Configuration & Docs
- [x] Extend `src/api/flaskr/common/config.py` with any new LiteLLM-specific env vars and adjust descriptions for existing keys that now flow through LiteLLM; regenerate env examples via `python scripts/generate_env_examples.py` and update committed artifacts (e.g., `docker/.env.example.full`). *(Not needed—existing env vars already cover LiteLLM usage, so no schema change required.)*
- [x] Update developer docs (`AGENTS.md`, `README.md`, `docs/...`) to describe the new LiteLLM setup, required env vars, and how to add a provider/model going forward. *(AGENTS.md now documents the LiteLLM integration strategy.)*

## Testing & Validation
- [x] Refresh or replace `src/api/tests/test_openai.py` and `src/api/tests/test_llm.py` so they mock LiteLLM instead of hitting real services, covering streaming chunks, usage accumulation, and provider selection logic.
- [x] Add targeted unit tests for the new adapter (e.g., verifying router config + model alias resolution) and regression tests for `invoke_llm`/`chat_llm` error paths.
- [ ] Run `pytest` for affected suites plus `pre-commit run --all-files` before committing to ensure formatting/lint hooks pass with the new dependency set. *(Blocked locally because the test environment lacks `flask_migrate`; re-run once dependencies are installed.)*

## Cleanup
- [ ] Remove dead code paths (e.g., unused `openai` imports, obsolete helper classes) and confirm `scripts/` or deployment assets no longer reference the old clients.
- [ ] Capture a migration note/changelog entry outlining how existing deployments should set LiteLLM env vars and whether any secrets must be rotated.
