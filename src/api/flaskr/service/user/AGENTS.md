# Backend Service: user

This module owns user records, auth credentials, verification-code flows,
token storage, temp-user handling, and auth-provider integration.

Entry files in this directory: `user.py`, `repository.py`, `models.py`,
`auth/factory.py`, `email_flow.py`.

## Do

- Keep credential lookup, token persistence, and provider dispatch in the
  shared repository and auth-factory paths.
- Preserve verification-code consumption rules and temp-user semantics so auth
  retries do not create inconsistent user state.
- Treat auth payloads, token fields, and credential models as shared contracts
  used by frontend login flows and backend guards.

## Avoid

- Do not bypass repository or token-store helpers when touching auth state,
  credential persistence, or verification flows.
- Do not add provider-specific branches to every caller when the auth factory
  should own that dispatch logic.
- Do not change user identifiers, avatar handling, or code-consumption rules
  without coordinated tests for retries and error paths.

## Tests

`cd src/api && pytest tests/service/user/ -q`

## Related Skills

- `src/api/skills/user-auth-flows/SKILL.md`
