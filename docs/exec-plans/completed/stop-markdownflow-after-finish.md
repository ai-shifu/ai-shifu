---
title: Stop model requests after lesson completion
status: completed
owner_surface: learner
last_reviewed: 2026-10-26
---

# Stop model requests after lesson completion

## Purpose / Big Picture

An accepted MarkdownFlow `finish` currently returns to the model as an ordinary
tool result. The model may produce an empty response, which the SDK retries,
charging for more input after the lesson is complete. End the run after the
current tool batch settles, preserving its teaching, tool results and usage.

## Progress

- [x] 2026-10-26 CST: Reproduce extra completion requests offline and inspect the
  SDK graph lifecycle, pending interactions, feedback validation and host tests.
- [x] 2026-10-26 CST: Fetch latest main and create an isolated repair branch.
- [x] 2026-10-26 CST: Add a public SDK capability that ends a settled finish batch.
- [x] 2026-10-26 CST: Verify focused completion regressions and update tests that require an
  extra request solely to obtain closing prose.
- [x] 2026-10-26 CST: Pass all offline engine tests, affected course/Profile host tests and
  repository gates, then prepare the focused repair for review.

## Surprises & Discoveries

- Making `finish` an SDK output tool discards a deferred final question emitted
  in the same response. Keep it a normal tool and let deferred results win.
- Breaking at a finish event can abandon sibling tools or validation. The public
  `after_node_run` capability runs after the entire tool batch has settled.
- The local environment has an older legacy MarkdownFlow package and Ruff.
  Isolated temporary dependency/tool directories keep shared environments intact.

## Decision Log

- Use the public `AbstractCapability.after_node_run` hook. Replace only a next
  model-request node after accepted completion, with no pending tool retry.
- Preserve all tool returns in the message history with the current run metadata;
  do not synthesize a provider response or modify recorded usage.
- Leave deferred interaction results and rejected-tool correction requests alone.
- Keep already streamed text from the same response, including text following a
  finish call in that response. Do not request new closing prose after completion.

## Outcomes & Retrospective

The reproduction now uses one model request instead of three. All 2,653 offline
engine tests and 403 affected course/Profile host tests pass. The focused
completion cases preserve final questions, sibling retries, tool history and
actual usage; an independent diff review found no actionable issues. The full
repository pre-commit gate passed with no unrelated file changes. The focused
repair is ready for review; deployment is outside this plan's scope.

## Context and Orientation

`src/api/markdownflow/engine/engine.py` constructs the SDK agent and converts its
events into native lesson events. `tools.py` validates and accepts completion.
`finish_run.py` owns the graph-boundary stop. Offline regressions live under
`src/api/tests/markdownflow/`; course and Profile hosts share the same engine.
The completion contract lives in the
[library design](../../design-docs/markdownflow-engine-library.md#completing-a-turn).

## Plan of Work

Add the terminal graph capability, verify exact request counts and session
round trips, retain sibling tools and final questions, then run the library and
affected application suites. Keep the change focused on completion requests.

## Concrete Steps

Run focused engine completion tests, then the full `tests/markdownflow/` suite.
Run the affected course agent and Profile runtime suites with the repository's
pinned legacy package available. Regenerate knowledge indexes, run the dev-tool
doctor, and run `lefthook run pre-commit --all-files` before committing.

## Validation and Acceptance

- A valid final response completes with one actual model request, including when
  a model would otherwise return an empty response or repeat the final line.
- Tool-call/return pairs, actual usage, summary and accepted teaching survive a
  Session serialization round trip; reopening completion makes no new request.
- Sibling memory writes settle, and a deferred final question remains answerable.
- Rejected completion or sibling tool validation still receives necessary retries.
- Buffered feedback, listening segments and course/Profile completion stay valid.

## Idempotence and Recovery

The capability has no persistent state. Existing sessions remain readable. A
rollback removes the capability without changing schemas or stored sessions.

## Interfaces and Dependencies

No public engine, event, tool, session or host interface changes. The capability
uses the existing pinned pydantic-ai and pydantic-graph packages' public APIs.
