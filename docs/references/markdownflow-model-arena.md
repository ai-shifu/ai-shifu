# MarkdownFlow model arena operator guide

The arena runs published teaching segments through four exact model versions
and places blind image/PDF comparisons in a dedicated Feishu Base. It is an
operator CLI, with no additional learner or teacher web route. A round defaults
to twelve cases and all six model pairs for each case.

## Prerequisites

- Install the pinned backend requirements and Cook Web dependencies (`npm ci`).
- Install a Playwright Chromium browser (`npx playwright install chromium` in
  `src/web`) and use one host for every artifact in the round.
- Authenticate the existing `lark-cli` user with Base, sharing, attachment, and
  workflow permissions. The CLI must support raw `api` calls. Resuming a Base
  from the earlier restricted setup also requires disabling its advanced permissions.
- Run the backend worker in the authorized production environment with the
  existing database, Redis, provider, and tracing configuration. The worker
  initializes only the required Flask services; it does not run migrations or
  expose routes. Snapshot extraction uses an independent read-only ORM session.

Copy `src/api/scripts/markdownflow_arena.example.json` to a private file outside
version control, replace the example owner phone, and set fixed learner variables
appropriate to the cases. Do not put provider credentials in this configuration;
the worker uses the existing configured provider wrappers.

`backend_command` is an optional argv array ending in
`markdownflow_arena.py worker`. It can invoke a container transport such as
`kubectl exec -i` with the checked-in worker deployed in a private temporary
directory. JSON input travels over stdin, never shell interpolation. The remote
worker must use the same code revision as the local coordinator, including the
optional completion observer in the shared LLM wrapper, the shared `prompts/`
templates, and the `i18n/` resources. Large worker responses use a versioned,
bounded gzip envelope to survive container transports. Operator transport
changes may update `config.backend_command` in the private manifest after a pod
replacement; keep frozen cases, models, and outputs unchanged.

If the production course model allowlist omits a requested model, optional
`model_routes` must list all four exact routes in the requested order, preserving
supplier prefixes. This extends the allowlist only inside the short-lived worker
process. Every route must still exist in the enabled provider's discovered
catalog; no model substitution or global deployment change occurs. Missing or
ambiguous versions fail before generation.

`renderer_command` is an optional argv array, for example `node`, the absolute
path to `src/web/scripts/markdownflow-arena/render.mjs`, and optionally
`--browser-path` plus an installed Chromium executable. The renderer appends
input/output arguments. `renderer_asset_hosts` explicitly permits HTTPS hosts
needed by course images; the default is offline. Network errors fail rendering
instead of silently producing incomplete work. See the renderer's README for
page slicing, font, sandbox, and PDF behavior.

## Run and recover

From the repository root, using the Python environment with backend dependencies:

```bash
python src/api/scripts/markdownflow_arena.py run --config /private/path/arena.json
python src/api/scripts/markdownflow_arena.py run --resume /private/path/arena_RUN_ID
python src/api/scripts/markdownflow_arena.py summarize --run-id arena_RUN_ID --run-root /private/path
```

The default private run root is the ignored
`artifacts/runs/markdownflow-arena/`. `--run-root` chooses another private
directory. Use `--smoke-only` to stop after two cases and their twelve matchups;
resume without that flag to finish the remaining cases. The normal command also
validates the first two cases before generating the remaining ten.

`manifest.json` is the versioned recovery source of truth. `snapshot.json` stores
authorized exact publication rows and skip reasons; per-work `artifact.json`
stores input hashes, raw output, adapted elements, exact model routing and
parameters, finish reasons, timing, and available token usage. `summary.json`
retains accepted/rejected vote IDs and aggregate statistics. These files and
their directories use owner-only permissions. Never commit or share this tree.

Completed generation is reused after a renderer, upload, or summary failure.
Successful initial runtime messages must have the same hash across models.
Publication records a fingerprint of the ordered PNG pages and rendering
settings. When that visible revision changes, the same matchup record and A/B
assignment are retained, old generated attachments are replaced, and its ready
time advances after the complete new attachments are verified. Earlier votes
remain in the raw table but do not score against the new revision. PDF metadata
alone does not change the visible revision.
Every run and publication rechecks prompt access against the configured owner.
Revocation stops new work; it does not retroactively recall previously downloaded
attachments. Keep previously shared content under the organization's retention
process if access must also be withdrawn.

A paid request interrupted before its result was checkpointed has an unknown
outcome. It is never retried automatically. Inspect private state before using
`--retry-failed`, which explicitly permits another request for failed/uncertain
generation. Previous attempts remain in the private artifact history. A
concurrent command is rejected by the run lock. Unknown Feishu
write outcomes require remote resource reconciliation before another creation;
the tool does not blindly retry non-idempotent writes.

## Reviewer and scoring contract

Reviewers see a neutral task description, A/B page attachments and complete
PDFs, and four buttons: A, B, tie, or both bad. Feishu workflows append the
clicked matchup record ID, actual click user, click time, and fixed choice.
The Chinese tables are named “待评审对局”, “原始投票”, and “管理与统计”; the
buttons are “A 更好”, “B 更好”, “差不多”, and “都不好”.

`feishu.permission_mode` defaults to `organization_editable`. Organization members
with the link can edit all three tables, including artworks and raw votes, as
requested for this collaborative review. The tool disables advanced permissions
on its dedicated Base and verifies button bindings before enabling the internal
editing link. External anonymous access stays disabled. Source prompts and the
mapping between each matchup's A/B sides and exact model identities stay in the
private manifest; the statistics table contains only model-level aggregates.
Because reviewers can edit vote rows, these statistics are for collaborative
comparison rather than tamper-resistant auditing.

Only the first valid vote for a batch, matchup, and reviewer counts. Missing
identity, invalid matchups/outcomes/timestamps, cross-batch rows and duplicates
do not score. Raw rows remain intact. Preference win rate is
`(wins + 0.5 * ties) / (wins + losses + ties)`; both-bad votes have their own rate.
Generation failures, truncation, and rendering failures remain separate and
never enter complete matchups. Rates without observations are null.

After delivery, a reviewer check can use two distinct ordinary reviewers: each votes on the
same matchup, one votes on another matchup, then repeats a vote on the first.
Verify one counted vote per person per matchup, correct click identities,
readable complete attachments, and organization editing access. An administrator
opening the Base does not prove these conditions.
The user chose to receive the automatically verified publication first and
perform this human voting check later.
Check the workspace's automation quota in the Feishu admin interface before a
large review campaign; unavailable quota telemetry is reported as unknown.
