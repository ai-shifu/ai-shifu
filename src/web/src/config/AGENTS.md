# Cook Web Domain: config

This module owns frontend runtime environment helpers and supporting
documentation for browser-visible configuration.

Entry files in this directory: `environment.ts`, `ENVIRONMENT_CONFIG.md`.

## Do

- Keep browser-safe environment reads centralized so pages and components do
  not branch on raw process variables.
- Preserve the contract between backend `/api/config` output and local
  environment defaults consumed on the frontend.
- Treat configuration docs as part of the public developer interface for Cook
  Web setup and troubleshooting.

## Avoid

- Do not scatter environment parsing across components or hooks when
  `environment.ts` should stay the source of truth.
- Do not expose secrets or server-only config values in frontend code or docs.
- Do not let docs drift from runtime behavior when adding or removing frontend
  configuration flags.

## Tests

`cd src/web && npm run test -- src/config/`
