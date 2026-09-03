# TTS Provider Capabilities

## Purpose / Big Picture

Replace the provider-name sets scattered across the TTS orchestration layers
with a `ProviderCapabilities` declaration on each provider class. Adding a
provider then means declaring its behavior in one place instead of editing
validation, streaming, segmentation, and registry sets by hand, which is how
the four-tier rollout produced two follow-up incidents.

## Progress

- [x] 2026-09-03 16:30-16:45 CST (UTC+08:00): Inventoried every provider-name set: registry priority and
  auto-detect tuples, config exposure sets, strict validation sets, streaming
  empty-audio retry and non-speakable skip sets, the Volcengine timestamp and
  MiniMax HTTP stream selectors, and the segmentation byte-limit branches.
- [x] 2026-09-03 16:45-17:30 CST (UTC+08:00): Added `ProviderCapabilities` to `base.py`, declared it on all
  nine providers, and derived every former set from the declarations.
- [x] 2026-09-03 17:30-17:50 CST (UTC+08:00): Added a parity test that pins the former literal sets as
  golden values and proves the derived views reproduce them.
- [x] 2026-09-03 18:00-18:40 CST (UTC+08:00): Verified the refactor on the
  dev01 and devus test environments; the TTS config payloads match the
  pre-refactor output on both.
- [ ] Follow-up: extract the MiniMax HTTP and Volcengine timestamp
  request-scoped finalize paths from `StreamingTTSProcessor` into strategy
  objects selected through `request_scoped_stream`.

## Surprises & Discoveries

- Tests substitute minimal fake classes into `_PROVIDER_REGISTRY`, so the
  registry must treat entries as duck-typed and fall back to default
  capabilities when a class declares none.
- The empty provider name was in the streaming empty-audio retry set. Its
  meaning is "auto-detected provider", so the derived check keeps retrying for
  an empty name rather than resolving it through auto-detection.
- `should_use_minimax_http_stream` also treats an empty name as MiniMax; that
  historical auto-detection shortcut is preserved verbatim.

## Decision Log

- Capabilities are a frozen dataclass on the class (`ClassVar`), not a method,
  so registry code can read them without instantiating providers.
- Every flag defaults to the conservative value; providers opt in explicitly.
- The former module-level names (`_AUTO_DETECT_PROVIDER_PRIORITY`,
  `_CONFIG_REQUIRES_*`, `SUPPORTED_TTS_PROVIDERS`, `PROVIDERS_REQUIRING_*`)
  remain as derived views for one release so external readers do not break.
  Runtime checks read the capabilities directly.
- Request-scoped streams are named by string constants in `base.py`; the
  strategy extraction itself is deferred to a separate change because it moves
  two large generator methods and their subtitle bookkeeping.

## Outcomes & Retrospective

Provider behavior is declared next to the provider. `validation.py`,
`streaming_tts.py`, `pipeline.py`, `minimax_run_tts.py`, and the registry no
longer mention provider names. Existing behavior is unchanged, as proven by the
golden-value parity test and the existing TTS suites.

## Context and Orientation

Provider adapters live under `src/api/flaskr/api/tts/`; the registry is that
package's `__init__.py`. Orchestration lives under
`src/api/flaskr/service/tts/`: `validation.py` (strict course settings),
`streaming_tts.py` (listen-mode synthesis), `pipeline.py` (segmentation), and
`minimax_run_tts.py` (MiniMax HTTP stream selection).

## Plan of Work

Declare capabilities on the base class and every provider, add registry
helpers (`get_provider_capabilities`, `list_provider_names`), derive the
former sets from the declarations, switch each runtime check to read the
capabilities, and lock behavior with a parity test.

## Concrete Steps

1. Add `ProviderCapabilities` and the request-scoped stream constants to
   `base.py`; give `BaseTTSProvider` a default declaration.
2. Declare capabilities on all nine providers matching their former set
   membership exactly.
3. Add `get_provider_capabilities` and `list_provider_names` to the registry;
   derive auto-detection and config exposure from the declarations.
4. Switch `validation.py`, `streaming_tts.py`, `pipeline.py`, and
   `minimax_run_tts.py` to capability lookups.
5. Add `tests/service/tts/test_provider_capabilities_parity.py`.

## Validation and Acceptance

The parity test passes with the golden values equal to the pre-refactor
literals, and the full `tests/service/tts` suite plus the learn and shifu TTS
suites pass unchanged. A provider class without a declaration behaves like the
most conservative provider.

```bash
cd src/api
python -m pytest tests/service/tts -q
ruff check flaskr/api/tts flaskr/service/tts tests/service/tts
```

## Idempotence and Recovery

The change is a pure refactor with no configuration, database, or API
contract changes. Reverting the commit restores the literal sets.

## Interfaces and Dependencies

- New public names: `flaskr.api.tts.base.ProviderCapabilities`,
  `flaskr.api.tts.get_provider_capabilities`,
  `flaskr.api.tts.list_provider_names`.
- No new dependencies; no environment, database, DTO, or frontend changes.
