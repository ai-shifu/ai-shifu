# AI-Shifu Backend Scripts

This directory contains utilities for developing and operating the AI-Shifu backend.

## evaluate_mdf_interactions.py

Use this evaluator when editing the MarkdownFlow prompts in
`src/api/markdownflow/engine/prompts/`. Run it from `src/api` with Python 3.11
and the dependencies in `requirements.txt`. It runs the course engine, validates
the controls with the MarkdownFlow renderer, and submits scripted learner answers.

```bash
python scripts/evaluate_mdf_interactions.py
python scripts/evaluate_mdf_interactions.py --suite smoke
python scripts/evaluate_mdf_interactions.py --list
python scripts/evaluate_mdf_interactions.py --case <case-id> --json /tmp/interaction-replay.json
```

Offline mode replays sanitized model text and tool calls from the bundled catalog.
It checks parsing, tool retries, answer storage, and continuation without network
access or provider credentials. Use `--cases <path>` to load another catalog of the
same shape. The [coverage inventory](mdf_interactions/README.md) lists the
short teaching paths and the replay regressions. Start with `--suite smoke`
for the core controls and multi-turn teaching paths. Langfuse access is only
needed when curating examples.

Live mode sends the checkout's current prompts to a configured model provider
through the backend model adapter. Set credentials in the local `src/api/.env`
or shell environment, for example `OPENAI_API_KEY` and, when applicable,
`OPENAI_BASE_URL`. Use an explicit model ID available from that provider.
The gateway can discover models from configured providers at startup. To
restrict discovery to the provider you want to test, set `SKIP_LOAD_DOTENV=1`
and supply that provider's configuration in the shell. The model provider bills
live calls. Both modes run without starting the web app, API, MySQL, or Redis.
The evaluator uses local session state and skips application usage writes and
Langfuse tracing.

Live steps with `prose_question` ask a model to verify that the visible teaching
prose invites the learner to answer the intended question. Equivalent wording
passes. An empty response, a related topic without a request to answer, or a
different question fails. The check runs independently of control assertions.
The judge can abstain when the intent or scope is ambiguous. It defaults to the
teaching model. Use the same `--judge-model` when comparing teaching models.
Set `--second-judge-model <model-id>` to get a second judgment on the same prose.
Each configured judge makes at most one additional provider request per
eligible step. An abstention or disagreement puts the original question, exact
learner-facing prose, and each judge's decision and reason in the human review
list. Judge requests and tokens have their own totals. A failed judge request
or invalid decision is a call failure. Offline mode applies replay assertions
such as `replay_prose_once` and marks semantic checks as unevaluated.

For each live learner action, an engine turn that ends after visible teaching
can continue automatically with the same session. The evaluator stops on a
question (including narrated controls), completion, an error, or a turn with
no visible teaching. The local run allows up to eight automatic continuations
per learner action and reports reaching that limit as a behavior failure.
Offline replay still checks the recorded engine turn for each fixture step.

In live mode, an assertion failure stays in the report and the evaluator still
submits the next fixture answer when the displayed control accepts it. For
example, it clicks an authored navigation button if the expected value is
available despite a control mismatch. If the planned submission is unavailable,
the evaluator stops that case.

```bash
python scripts/evaluate_mdf_interactions.py --live --model <model-id> --temperature 0 \
  --suite smoke --repeat 3 --json /tmp/interaction-baseline.json
# Edit the local prompt files, then run the same cases and model settings.
python scripts/evaluate_mdf_interactions.py --live --model <model-id> --temperature 0 \
  --suite smoke --repeat 3 --json /tmp/interaction-candidate.json \
  --compare /tmp/interaction-baseline.json
```

Each report includes the prompt and case fingerprints, model settings, per-run
outcomes, failed checks, rendered controls, teaching text, usage, and elapsed
time. The terminal and JSON report include totals by criterion for
`passed`, `failed`, `needs_review`, and `not_evaluated`. The count is per
assertion, including individual phrase checks within a step. Unreachable
steps and unavailable control fields count as unevaluated. Use
`results[].steps[].criteria` to inspect a step and `review_items` for
the cases that need a human decision. Each review item identifies the
case, repeat, and step.

A pass after a model validation retry or automatic continuation is reported
as a recovery. Reports count the two kinds of recovery separately and include
each engine turn's outcome. They also distinguish reproduced historical
failures, behavior failures, and provider failures. Generate a fresh baseline
when the report version or selected fixtures change. `--compare` requires
matching mode, teaching model, judge models and instructions, temperature,
case selection, and repeat count.

The exit status is 0 when all cases meet their expectations, 1 for behavior
failures, 2 for invocation, provider, or comparison errors, and 3 for pending
human review in a run without behavior or call failures. Review items remain
in the report when the run also has another failure.

### Review and annotate results

With `--json`, the evaluator also writes a sibling `.review.html` file,
including when assertions fail or a verdict needs review. Open it in a browser.
Use the case and step navigation, filter by criterion or review status, and
expand the criterion to compare expected and observed evidence. The page shows
the submitted values and text, authored prompts, visible teaching and controls,
memory changes, per-turn prose, model tool arguments, and retry feedback.
The source blocks preserve exact strings and expose full step data. For visual
blocks, the prose preview extracts the text and leaves the source available.

Choose a human verdict and enter a note on any criterion. Uncertain verdicts
appear in the human review filter. The criterion table counts automatic and
human verdicts in separate columns. The browser saves edits by run, case,
repeat, step, and criterion. Export the annotations to JSON for a portable
copy. Import restores matching entries, and keeps and counts local edits when
both files have different annotations for the same criterion.

Use one page to compare runs with the same fixture selection, or regenerate a
page from a saved report without invoking a model.

```bash
python scripts/mdf_interaction_review.py /tmp/interaction-baseline.json \
  /tmp/interaction-candidate.json --output /tmp/interaction-comparison.html
```

New reports carry the fixture snapshot. For an earlier version 5 report, the
review tool attaches the current catalog only when its selected case fingerprint
matches. Pass `--cases /path/to/original-cases.json` to use an older catalog.
The page uses the evidence available in each report. Model-call arguments and
retry feedback are available for runs saved with the updated evaluator.

### Curating fixtures

For a new trace-derived case, reconstruct a teaching excerpt and answer with
original wording. Keep the interaction syntax, displayed and submitted value
relationship, bindings, and sequence of model attempts needed to reproduce it.
Set expectations from the teaching script and the learner behavior it calls for.
Use a separate replay expectation when the recorded output shows a historical
failure. Review the JSON before committing it to ensure its text and metadata
contain no raw course or learner data. Use synthetic cases for behaviors that
are missing from the sampled traces.

## backfill_profile_onboarding_assistant_prompts.py

Run this once when adding a new supported language to an installation with an
existing profile-onboarding configuration. Use the upgraded API runtime, with its
database and LLM settings available, before exposing the new locale in the learner UI.
For a Docker Compose installation, run from the repository root:

```bash
cd docker
docker compose -f docker-compose.latest.yml exec -T ai-shifu-api python scripts/backfill_profile_onboarding_assistant_prompts.py --locale ur-PK
docker compose -f docker-compose.latest.yml exec -T ai-shifu-api python scripts/backfill_profile_onboarding_assistant_prompts.py --locale ur-PK --apply
```

For a source-checkout installation, run from the repository root instead:

```bash
cd src/api
python scripts/backfill_profile_onboarding_assistant_prompts.py --locale ur-PK
python scripts/backfill_profile_onboarding_assistant_prompts.py --locale ur-PK --apply
```

The first command previews the stored configuration without a model call or
write. `--apply` localizes the saved master prompt and atomically fills missing
registered locales, preserving existing translations. Omitting `--locale`
continues to target Spanish for compatibility with older runbooks. It prints only a status
and configuration revision plus the generated locale codes, never the prompt
text. If an older map lacks languages besides Urdu, the existing save path
fills those missing languages in the same run. `already_present` means a
repeat run has nothing to do. `no_configuration` or `no_master_prompt` means
there is no saved prompt to translate; configure the onboarding prompt through
the operator UI if that feature is needed. A generation or concurrent-save
failure leaves the previous configuration intact; retry after resolving it.
Existing learner sessions retain their original frozen prompt.

## generate_env_examples.py

Generates the environment configuration example file from the application's configuration definitions.

### Purpose

This script automatically generates `.env.example.full`, which contains every environment variable with defaults and documentation. Copy it to `.env`, configure a provider API key, and set `LLM_MODEL_1_ID` to a text model served by that provider before starting Docker. Only model 1's ID is required and has no default; IDs 2-9 are optional. Every model name is optional: omitted or blank names display the configured model ID. A name without an ID does not enable an option.

### Usage

From the `src/api` directory:

```bash
python scripts/generate_env_examples.py
```

### Output

The script generates one file in the `docker` directory:

- `.env.example.full` - Complete configuration reference used by Docker deployments

### Features

- Automatically extracts configuration from `flaskr.common.config`
- Groups variables by category (Database, Redis, Auth, LLM, etc.)
- Includes descriptions, types, and validation information
- Marks required variables clearly
- Handles multi-line descriptions
- Protects secret values by not including defaults
- Provides a summary of configuration requirements

### When to Use

Run this script when:

- Adding or editing environment variables in `config.py`
- Updating variable descriptions or requirements
- Refreshing the example template for onboarding/docs

### Example Output

The script reports current variable counts and required settings. Its required-settings output includes:

```
📌 Required variables that must be configured:
  [LLM]
    - LLM_MODEL_1_ID
      Routed text model for course model 1. Required; no default.
```

### Configuration Workflow

1. Run the generation script.
2. Copy `docker/.env.example.full` to `docker/.env`.
3. Edit `.env` and configure a provider API key, required `LLM_MODEL_1_ID` and any other secrets you need. Names are optional; blank names display the configured IDs. The template intentionally leaves model mappings empty.
4. For existing installations, complete [Upgrading to numbered models](../../../INSTALL_MANUAL.md#upgrading-to-numbered-models) before starting the new API or workers.
5. Never commit `.env` to version control.

## harness_diagnostics.py

Summarizes backend log evidence for a specific `X-Request-ID` so browser smoke
failures can be traced back to request-scoped server activity.

### Usage

From the `src/api` directory:

```bash
python scripts/harness_diagnostics.py --request-id <request-id>
```

### Output

- request id and detection mode (`langfuse-configured` or `local-log-only`)
- explicit trace-id hints when they appear in logs
- a bounded excerpt of matching `ai-shifu.log*` lines
- when the local dev observability stack is reachable, a Loki/Tempo
  summary plus Grafana explore links for the same request context
- the default dev harness now boots the API through
  `scripts/repair_dev_migration_state.py` before rerunning Alembic, so
  diagnostics can assume the self-healing path is part of normal startup

## grant_white_label.py

Onboards a single creator to white-label (custom domain + branding) by writing
the manual billing entitlement and a verified custom-domain binding. This is the
fast-path operator tool: branding/custom-domain entitlements are granted
manually and decoupled from paid products.

### Purpose

- Sets `branding_enabled` / `custom_domain_enabled` on a reusable manual
  entitlement snapshot for the creator (idempotent upsert).
- Writes the supplied logo / home / contact URLs into
  `feature_payload.branding`, which `/runtime-config` serves to the learner app
  so `/c` pages render the creator's logo and favicon automatically.
- Binds and marks the custom domain `verified` so published/preview links point
  at the creator's own host.

### Usage

From the `src/api` directory:

```bash
python scripts/grant_white_label.py \
  --creator-bid <creator_bid> \
  --host learn.example.com \
  --logo-wide-url https://cdn.example.com/wide.png \
  --logo-square-url https://cdn.example.com/square.png \
  --favicon-url https://cdn.example.com/favicon.ico
```

Use `--dry-run` to preview the changes without writing. Use `--no-custom-domain`
to grant branding only (skips the domain entitlement and binding). DNS still
needs the customer to CNAME the host to our ingress, and the ingress host rule
must be added separately (see `deploy-config`).
