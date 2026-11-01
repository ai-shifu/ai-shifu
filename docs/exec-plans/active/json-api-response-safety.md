# Serve shared API envelopes as inert JSON

## Purpose / Big Picture

Prevent API payloads containing user-controlled HTML from being interpreted as
HTML documents. Twenty-nine open CodeQL `py/reflective-xss` alerts on main
`dc2aceb0e1472116a4c9c327af4765e4b4a3bb39` share the same response boundary:
`make_common_response()` serializes a JSON string, and Flask gives string route
returns the default HTML media type. The response body and envelope must remain
compatible with existing browser and external API consumers.

## Progress

- [x] 2026-11-01 10:15 UTC: Traced the shared HTML response boundary and audited
  every direct helper caller, response wrapper, and direct-body test consumer.
- [x] 2026-11-01 10:15 UTC: Return an explicit JSON response, preserve custom
  serialization, and coordinate route annotations and wrapper consumers.
- [x] 2026-11-01 10:18 UTC: Focused malicious-input and compatibility checks
  passed (130 tests); baseline and candidate payload bytes match, while the
  response media type changes from HTML to JSON.
- [ ] 2026-11-01 10:18 UTC: Complete the full backend suite and repository checks.
- [ ] 2026-11-01 10:15 UTC: Obtain independent candidate review and current PR CI
  results. Main alert closure requires a human-authorized merge and new scan.

## Surprises & Discoveries

- Several consumers already wrapped the serialized value in a second Flask
  response. Those wrappers must be removed when the helper itself returns a
  response; otherwise the helper's new return value becomes an invalid body.
- Stripe's legacy webhook must preserve provider-selected HTTP status codes.
- Direct Python tests parsed helper returns using `json.loads()`. They now
  inspect `Response.get_json()`, matching the new internal return contract.

## Decision Log

- 2026-11-01: Enforce the media type at the shared response producer, retaining
  `json.dumps(default=fmt, ensure_ascii=False)` rather than changing DTO, decimal,
  Unicode, or UTC serialization through Flask's separate JSON provider.
- 2026-11-01: Add `nosniff`, following the existing live follow-up response
  precedent. Keep file and SSE response creation unchanged.
- 2026-11-01: Keep export-path, regex, and diagnostic findings in independent PRs.

## Outcomes & Retrospective

Focused verification passes. The full backend suite and repository checks are
still in progress. No claim is made that the default-branch alerts have closed
or that this change is deployed.

## Context and Orientation

The response producer lives in `src/api/flaskr/common/http.py` and is re-exported
by `src/api/flaskr/route/common.py`. Route consumers span authoring, billing,
learner, profile, user, and other API modules. The canonical success envelope
is documented in `docs/engineering-baseline.md` under API Contract Baseline.
The root and backend `AGENTS.md` files require coordinated shared-contract
changes, existing helpers, focused regressions, and repository checks.

## Plan of Work

Return a `Response` with the existing JSON body and explicit JSON headers.
Update direct helper consumers, including nested response construction and
annotations, and document the internal return contract. Test hostile HTML
without altering decoded payloads, then verify normal serialization, webhook
statuses, activation imports, direct view invocation, and live follow-up output.

## Concrete Steps

1. Inspect every helper reference and enclosing function's return paths.
2. Change the producer and remove redundant body wrappers in legacy order and
   live follow-up routes; preserve statuses and cookies.
3. Add `tests/common/test_http_json_response.py` and adapt direct-body tests.
4. Run focused tests with the configured Python environment from `src/api`,
   then run affected backend suites and repository harness checks.
5. Submit a ready PR, inspect its current checks, and leave merging to humans.

## Validation and Acceptance

- HTML script, SVG, and closing-script payloads decode unchanged as JSON while
  receiving `application/json` and `nosniff` headers.
- The envelope, null behavior, Unicode, nested DTOs, decimals, dates, and UTC
  timestamps retain their previous JSON representation.
- Stripe webhook responses retain their provider-selected 202/400/409 statuses;
  activation imports and live follow-up responses remain parseable JSON.
- Existing affected backend tests, lint, architecture, and repository harness
  checks pass. Record exact commands and results before completing this plan.
- PR CodeQL results must be checked separately from default-branch alert state.

Focused result: from `src/api`, `PYTHONPATH=. python -m pytest -q
tests/common/test_http_json_response.py tests/service/billing/test_value_objects.py
tests/service/order/test_order_route_contracts.py
tests/service/learn/test_listen_elements.py
tests/service/learn/test_live_follow_up_route_boundaries.py
tests/service/learn/test_learn_stream_response_cleanup.py` passed all 130 tests.
An isolated baseline-helper route returned `text/html`; the candidate returned
`application/json` with the same bytes and the `nosniff` header.

## Idempotence and Recovery

The change adds no data migration or persistent state. Re-running tests is safe.
Revert the focused response-contract commit to roll back, including its caller
and test updates, so response construction remains consistent.

## Interfaces and Dependencies

`make_common_response(data: object)` changes its internal Python return type
from `str` to Flask `Response`; the HTTP JSON payload shape is unchanged.
Existing Flask, `json`, and `fmt()` dependencies suffice. There are no new
external services, environment variables, dependencies, or user actions.
