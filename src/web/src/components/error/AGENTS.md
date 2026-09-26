# Error fallback components

This directory owns `AppErrorFallback.tsx`, shared by App Router route and
root-layout error entries. Inherit all other frontend/component rules.

## Local i18n exception

Minimal static fallback labels are allowed only in this shared crash component.
It uses those same labels for route-level and root-layout failures because it
cannot assume i18n or its providers initialized successfully, regardless of the
subsystem that failed. Keep ordinary business errors and normal
UI copy in shared i18n JSON. This exception does not authorize new static copy
in unrelated components, pages, or analytics payloads.

Do not import the store barrel or require runtime providers to show a crash.
Use the [error-boundary skill](../../../skills/app-error-boundary-display/SKILL.md)
for displayed diagnostics and sensitive-data exclusions.

## Tests

Run `cd src/web && npm test -- --runInBand --runTestsByPath src/components/error/AppErrorFallback.test.tsx`.
