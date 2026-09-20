# Safe Outbound URL Validation

## Purpose / Big Picture

Provide one backend boundary for requests to user-controlled URLs. The boundary
must reject internal network targets, pin connections to validated DNS results,
revalidate redirects, and bound response size and request duration. Remote image
imports and Dify will adopt it in later focused pull requests.

## Progress

- [x] 2026-09-19 10:30 CST: Reviewed the remote-image and Dify request paths.
- [x] 2026-09-19 11:20 CST: Implemented the shared validation and request boundary.
- [x] 2026-09-19 11:35 CST: Added focused security and compatibility tests.
- [x] 2026-09-19 11:50 CST: Ran focused and repository verification.

## Surprises & Discoveries

- The current remote-image and Dify paths call `requests` directly and share no
  outbound URL policy.
- A validation-only helper would leave a DNS rebinding gap between validation
  and connection, so this plan includes a connection boundary that receives the
  already validated IP address.

## Decision Log

- Decision: private destinations are denied by default. A self-hosted deployment
  may opt into an exact trusted origin, including its explicit port; there is no
  blanket localhost or private-network bypass.
- Decision: this pull request adds the reusable boundary only. Business-specific
  adoption remains in separate remote-image and Dify pull requests.

## Outcomes & Retrospective

The shared boundary now rejects non-public destinations by default, pins the
connection to a validated DNS result, preserves the original TLS identity,
revalidates every redirect, prevents credential or request-body forwarding to
another origin, and bounds time and response bytes. Exact trusted origins keep
self-hosted local integrations possible without a blanket private-network
bypass. The focused suite passes 27 tests. The wider common suite passes 301
tests and has one unrelated existing Feishu log-capture failure that reproduces
in isolation.

## Context and Orientation

Shared backend helpers live under `src/api/flaskr/common/`. URL policy and
response handling live in `safe_outbound.py`; the small pinned TLS/HTTP transport
lives in `safe_outbound_transport.py`. The first consumers
will be `src/api/flaskr/service/shifu/funcs.py::upload_url` and
`src/api/flaskr/service/learn/ask_provider_adapters/dify_adapter.py`.

## Plan of Work

Add a policy object, URL/DNS validation, a pinned outbound HTTP transport,
manual redirect processing, bounded response reads, and exact-origin trust for
operator-controlled local integrations.

## Concrete Steps

1. Add the shared module and typed exceptions/results.
2. Add unit tests using injected DNS and transport fakes.
3. Run focused pytest, Ruff, compilation, and repository harness checks.

## Validation and Acceptance

Acceptance requires public HTTPS requests to retain the original hostname for
TLS while connecting to a validated IP. Local, private, link-local, reserved,
mixed public/private DNS, unsafe ports, credential-bearing URLs, unsafe
redirects, redirect loops, and oversized bodies must be rejected. An exact
trusted local origin must remain usable for self-hosted development.

## Idempotence and Recovery

The work adds no database state or migration. Reverting the module and tests
fully removes the capability because no business path adopts it in this PR.

## Interfaces and Dependencies

The implementation uses Python URL, IP, socket, and TLS primitives plus the
repository's existing urllib3 dependency. DNS resolution and transport are
injectable so security behavior is deterministic in tests.
