# Local MarkdownFlow slide comparison ExecPlan

## Purpose / Big Picture

A person manually runs a standalone script to compare the four specified models
on real authorized published slide-generation prompts. The output is one offline
HTML page: one model per column, one prompt set per row, all slide pages visible.
The script also provides integration coverage by calling the main generation and
rendering paths directly.

## Progress

- [x] 2026-09-08 UTC: Implemented authorized published snapshots, exact provider
  routes, isolated generation, complete capture, and resumable private artifacts.
- [x] 2026-09-08 UTC: Moved all evaluation implementation into
  `scripts/markdownflow-arena/`, retaining direct production-code reuse and no
  diff under `src/api`, `src/web`, or `src/i18n`.
- [x] 2026-09-08 UTC: Applied the user's revised scope: slide-generation only,
  local HTML comparison, no Feishu publication, voting, pairings, or scoring.
- [x] 2026-09-08 UTC: Built a local page from three existing slide prompt sets:
  four model columns, ten complete slide works, forty-seven captured pages, one
  text-only output, and one truncated output. No model calls were repeated.
- [x] 2026-09-08 UTC: Passed 133 focused Python tests and verified the local
  Chromium page: four columns, three rows, all forty-seven PNGs decoded, no
  external requests, prompt expansion, and image zoom/open/close.
- [x] 2026-09-08 UTC: Passed the repository-wide gate and prepared the existing
  PR description for standalone local slide comparison delivery.

## Surprises & Discoveries

- Generic HTML and conditional slide-format guidelines do not establish a slide
  generation task; selection now requires generation intent.
- A model may finish normally but return only prose. Such output must be an
  explicit missing-slide cell, not a successful slide render.
- The original mixed batch has three usable slide cases, rather than twelve.
  Its cached results can be shown immediately; new runs request twelve eligible
  slide cases and report a shortage rather than including other content.
- Existing PDFs may include metadata-only changes. The local HTML embeds verified
  PNG pages and does not depend on PDF identity or external attachment state.

## Decision Log

- User requested a standalone, manually invoked script that reuses main-flow
  code. All orchestration, capture, local copy, dependencies, and tests live under
  the script directory; production code has no evaluation extension.
- User replaced Feishu voting with a local side-by-side page and narrowed the
  sample to slide generation. External publishers and score modules are removed.
- Preserve original published prompts, including required narration, rather than
  injecting new slide-only instructions. Only slide elements are compared.
- Display model identities directly. Preserve failed/missing cells and every page.
- Schema 2 supports slide-only runs. A report-only command reads the slide subset
  of schema 1 without remote calls; generation resume does not migrate mixed runs.
- Keep existing paid outputs and external resources untouched. The local page is
  a private artifact containing escaped prompt details and embedded images.

## Outcomes & Retrospective

The existing paid results now have a portable local comparison page. The revised
pipeline contains no Feishu dependency or voting requirement. Main generation
and rendering paths remain real dependencies, with isolated observation for
finish reasons, elapsed time, and available usage. Final checks are recorded in
Progress before code delivery.

## Context and Orientation

The tool is under `scripts/markdownflow-arena/`. `source.py` freezes current
prompt-authorized published rows and samples self-contained slide blocks.
`engine.py` invokes shared MarkdownFlow, `chat_llm`, and preview adapters.
`observe.py` records provider completion metadata without altering production
source. `pipeline.py` checkpoints model output separately from rendering and
local HTML. `report.py`, `report.css`, and `report.js` own the comparison page.
The renderer uses official pinned UI components in a loopback browser.

## Plan of Work

Keep existing source authorization and generation contracts. Narrow case
selection to slide intent, classify text-only output explicitly, remove pairing
and publication stages, and atomically build a static local report. Preserve all
pages in each cell and provide keyboard-accessible image zoom. Update CLI,
operator documentation, tests, and the existing PR around this final scope.

## Concrete Steps

1. Run source, engine, worker, pipeline, and report tests.
2. Generate `comparison.html` from the existing private batch without model calls.
3. Open the local page in Chromium; verify all columns, rows, image decoding,
   prompt expansion, zoom, and zero remote requests.
4. Run Ruff and the repository-wide lefthook gate, then commit and push the PR.

## Validation and Acceptance

The script samples only authorized published slide-generation tasks and invokes
the four exact specified models. Identical inputs and process isolation remain
covered. Resume does not repeat successful model calls after local failures.
The HTML has exactly one column per configured model, one row per slide case,
and every verified slide image, with failures visible. No Feishu CLI, remote
publication, or vote collection runs. Production source remains unchanged.

## Idempotence and Recovery

Run locks and atomic manifests protect private progress. `run --resume` rechecks
permissions and route IDs; model result checkpoints survive report/render errors.
`report --run-dir` rebuilds an HTML page from local files only, including the
slide subset of a legacy mixed run. It checks file ownership paths and recorded
image hashes before atomically replacing the existing page.

## Interfaces and Dependencies

Manual commands are `run --config`, `run --resume`, and `report --run-dir`.
Workers accept bounded JSON requests in separate backend-capable processes.
The operator environment provides backend requirements and credentials; the
renderer has its own npm lock and Chromium. The HTML is self-contained with
embedded PNGs, escaped prompt text, local styles, and a small zoom script.
