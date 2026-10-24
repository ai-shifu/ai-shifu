# Trusted Client IP Resolution

> Lifecycle review, 2026-09-26: Completed original scope. Trusted-proxy resolution and recorded focused request-chain tests shipped. Earlier permission/publish notes are historical. Merge evidence: [#2896](https://github.com/ai-shifu/ai-shifu/pull/2896) (`a1173269f`)

## Purpose / Big Picture

Several security and audit paths trust the first `X-Forwarded-For` value supplied by a caller. Replace those independent parsers with one resolver that accepts forwarding data only when the immediate connection comes from an explicitly configured proxy network.

## Progress

- [x] 2026-09-20 20:20 CST: Inspected every backend forwarded-IP consumer, nginx proxy behavior, and Docker port exposure.
- [x] 2026-09-20 20:32 CST: Implemented the shared resolver and configuration contract.
- [x] 2026-09-20 20:34 CST: Migrated request logging, auth, sessions, device authorization, referral, and payment request metadata.
- [x] 2026-09-20 20:46 CST: Added direct, nginx, CDN-chain, spoofing, malformed-header, IPv4-mapped IPv6, and shared-consumer tests.
- [x] 2026-09-20 20:48 CST: Verified 42 focused tests, 38 referral tests, 122 configuration/session tests, and the broader user suite boundary.
- [x] 2026-09-20 21:15 CST: Passed repository harness, architecture, UoW, diff, and full pre-commit gates; commit/push remains subject to user approval.
- [x] 2026-09-20 22:20 CST: Addressed review feedback by giving bundled nginx a dedicated fixed proxy address, trusting only that host in all three Compose modes, and normalizing IPv4-mapped IPv6 proxy networks.

## Surprises & Discoveries

- Production Docker Compose publishes nginx only; the API service has no host port. Development binds the API port to `127.0.0.1`, so it is not publicly exposed by the repository defaults.
- Nginx currently appends the peer address to `X-Forwarded-For`. A right-to-left trust walk is therefore sufficient and preserves CDN chains without trusting caller-supplied leftmost values.
- An empty backend default is safe for custom deployments but unsafe for the bundled proxy topology: all callers otherwise share nginx's address for IP-based limits. The bundled Compose files now provide a narrowly scoped `/32` default without changing the backend default.
- The broader user suite retains the known local `markdown_flow` mismatch: 405 tests pass and 36 profile-onboarding tests fail; one guided-routes module cannot collect because the installed package lacks `USER_ANSWER_CONTEXT_KEY`.

## Decision Log

- Decision: configure trusted proxy networks through `TRUSTED_PROXY_CIDRS`, defaulting to empty.
  Rationale: no proxy address range is safe to assume for every open-source deployment.
- Decision: walk a syntactically valid `X-Forwarded-For` chain from right to left, skipping only configured trusted networks.
  Rationale: this selects the first untrusted client hop and resists prepended spoofed values.
- Decision: ignore the complete forwarding header if any hop is malformed.
  Rationale: malformed or ambiguous input must fail closed to the TCP peer rather than bypass IP controls.
- Decision: attach bundled nginx, web, and API services to a dedicated proxy network and assign only nginx a fixed address.
  Rationale: the API can trust a single `/32` instead of every container on the general application network.

## Outcomes & Retrospective

All backend IP consumers now use one trust-aware result. Direct callers cannot change their address with a forwarding header, while explicitly trusted nginx/CDN chains resolve the first untrusted hop from the right. The production Compose API remains private and the development API remains loopback-only. Bundled Compose deployments trust their dedicated nginx host automatically; custom deployments retain the empty fail-closed backend default and must configure their exact proxy CIDRs.

## Context and Orientation

`flaskr/common/log.py` initializes `request.client_ip`, but user routes, session metadata, and referral routes currently repeat their own unsafe parsing. `docker/nginx.conf` and `nginx.dev.conf` append their TCP peer to `X-Forwarded-For`. The production API service is internal to Compose; nginx is the public entry point.

## Plan of Work

Add `flaskr/common/client_ip.py` as the single resolver. Register and document the trusted proxy CIDR setting. Make request logging assign the resolved value, and replace every duplicate parser with the helper. Preserve a deterministic fallback to the normalized TCP peer. Add focused unit and route-level regressions.

## Concrete Steps

1. Add CIDR parsing, validation, caching, and request resolution.
2. Migrate common logging, user routes, session creation, and referral events.
3. Update configuration examples and deployment guidance.
4. Add tests for direct spoofing, one and multiple trusted proxies, malformed chains, IPv6, and consumer integration.
5. Run user, referral, common logging, configuration, architecture, translation, and repository gates.

## Validation and Acceptance

- With no configured proxies, a forged `X-Forwarded-For` never changes the resolved TCP peer.
- With trusted nginx/CDN networks, the resolver returns the first untrusted hop walking from right to left.
- A forged value prepended before the real client is ignored because the real client is encountered first.
- Invalid or empty chain members fall back to the TCP peer and never produce an empty IP that skips rate limits.
- Request logs, verification limits, device authorization, session metadata, referral hashing, and payment requests receive the same resolved value.
- Repository Docker defaults do not expose the production API directly; development exposure remains loopback-only.

## Idempotence and Recovery

There is no database migration. Removing the configuration returns resolution to the TCP peer. Rollback restores legacy header behavior without persisted-data conversion.

## Interfaces and Dependencies

- Python `ipaddress` for normalized IPv4/IPv6 and CIDR membership.
- Flask request/current-app context.
- Existing nginx `X-Forwarded-For` append behavior.
