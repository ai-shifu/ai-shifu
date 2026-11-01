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
- [x] 2026-11-01 10:28 UTC: Full pinned-environment backend suite passed: 15,249
  tests, 109 skips and 41 subtests. Repository-wide lefthook checks, architecture
  boundaries and the unit-of-work ratchet passed.
- [x] 2026-11-01 10:28 UTC: Independent candidate review found no concrete HTTP
  bypass or regression. Ready PR #3292 contains this focused contract change.
- [x] 2026-11-01 10:51 UTC: Updated the feature branch onto main after PRs #3294
  and #3295 were externally merged. Both exception sources behind the relocated
  CodeQL #183 finding are now fixed in this branch; the PR diff stays HTTP-only.
- [ ] 2026-11-01 10:28 UTC: Obtain current PR CI results. Main alert closure
  requires a human merge and new scan.

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
- 2026-11-01: Do not resolve CodeQL #183 merely because its source fix exists in
  another PR. Refresh this feature branch after that PR is merged, revalidate
  the actual current source, and close the thread only after verification.

## Outcomes & Retrospective

Focused and full backend verification and repository checks pass. The initial
reused Python environment had stale dependency versions and a missing SOCKS
extra; a fresh environment installed from `requirements-ci.txt` passed with
process proxy variables removed. PR #3292 is ready for review. Default-branch
alerts remain open until a human merge and subsequent scan; this is not deployed.

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

Full result: `PYTHONPATH=. python -m pytest -n 2 --dist loadfile -q --tb=short
-p no:testmon tests` from `src/api` passed 15,249 tests and 41 subtests, with
109 existing skips. Dependencies came from `src/api/requirements-ci.txt`; the
process unset upper/lowercase HTTP, HTTPS and ALL proxy variables. The run also
included the independent notification, export and parser fixes being submitted
in separate PRs. `lefthook run pre-commit --all-files`,
`python3 scripts/check_architecture_boundaries.py` and
`python3 scripts/check_uow_commit_sites.py` passed.

## Idempotence and Recovery

The change adds no data migration or persistent state. Re-running tests is safe.
Revert the focused response-contract commit to roll back, including its caller
and test updates, so response construction remains consistent.

## Interfaces and Dependencies

`make_common_response(data: object)` changes its internal Python return type
from `str` to Flask `Response`; the HTTP JSON payload shape is unchanged.
Existing Flask, `json`, and `fmt()` dependencies suffice. There are no new
external services, environment variables, dependencies, or user actions.
