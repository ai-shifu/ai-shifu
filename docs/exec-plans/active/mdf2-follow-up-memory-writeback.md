# Admit and persist memory from completed follow-up answers

## Purpose / Big Picture

The shared follow-up reader now sees current-course notes. Complete the default
text LLM path with declared-or-requested writes, reusing the existing memory tool,
semantic admission, gateway, native-thread bridge and scoped profile facade.

## Progress

- [x] 2026-10-09T02:05:00Z: Start from manually merged #3056, main 676d60528.
  Final backend CI passes 10,781 tests / 23 expected skips, plus eight contracts.
- [x] 2026-10-09T02:20:00Z: Real sim baseline responds to an explicit remember
  request but stores no matching note. Actual tool, provider-fallback, storage,
  retained-version, deletion/reset and rollback regressions pass.
- [x] 2026-10-09T02:20:00Z: Host/factory integration passes 109 focused tests,
  including idle cancellation and declared system-profile scope. First extended
  suite passes 4,826 tests / four subtests / eleven expected skips.
- [x] 2026-10-09T02:35:00Z: Final extended suite passes 4,828 tests / four
  subtests / eleven expected skips. All three real gateway factory regressions
  pass separately (default, fallback and Get Biji synthesis). Repository gates
  pass with the new helper staged; architecture drift remains zero.
- [ ] Run local gates, open a focused PR, deploy sim and reply to AI opinions.

## Surprises & Discoveries

Follow-up history flushes during streaming, then its host commits after the stream
fully drains. The native engine bridge already owns asynchronous model execution
and cancellation under gevent. Reusing it avoids running an event loop on request
greenlets. External provider-only answers must remain independent of LLM setup.

## Decision Log

- Keep ordinary 1.0 and external provider-only routing unchanged. Only an actual
  contextual LLM call gets the memory tool; no hidden extraction call per question.
- Author permission comes from the active lesson's main script collection names,
  not references, course instructions, old questions or provider knowledge.
- Reuse engine remember admission and capacity checks; raw current learner input
  is the only request evidence. Declared system fields retain existing semantics;
  all other values stay in the current course. Deleted keys require new consent.
- Buffer approved updates on the native producer. On completed consumption, stage
  them on the host with the existing post-stream history commit. No DB writes on
  the producer, failed calls, rejected guardrails, disconnects or previews.
- Lock the original learning attempt and compare deletion generations during the
  final write. A reset or concurrent deletion cannot be undone by stale output.

## Outcomes & Retrospective

Implementation and local verification are complete. Deployed acceptance is pending.

## Context and Orientation

handle_input_ask.py constructs providers and contextual LLM factories.
context_v2.py owns post-stream history durability. agent/engine/tools.py owns
remember admission/capacity; agent/bridge.py owns thread/loop cancellation.
The memory facade stages scoped variables and filters deletion generations.

## Plan of Work

Use a small follow-up Agent with only the existing remember tool. Preserve the
shared context and provider registry. Buffer successful tool proposals, then let
the existing text host stage them in its final transaction with ask history.

## Concrete Steps

1. Exercise actual FunctionModel tool calls: declared/requested/denied/deleted,
   capacity, actual current-input evidence, failed streams and consumer closure.
2. Cover real storage and host dispatch: course/user isolation, reset/deletion races,
   preview isolation and atomic rollback with history.
3. Verify normal provider factories, metering, local gates and sim HTTP behavior.
4. Reply to every AI opinion in its original discussion; user merges main.

## Validation and Acceptance

Completed eligible text follow-ups persist admitted facts and subsequent fresh
requests recall them. Casual undeclared facts, forged quotes, system/reference
writes without author permission and stale/deleted attempts do not persist.
Tool events never enter user SSE or visible classroom history. Ordinary no-tool answers
use one existing model request; there is no extraction call per question. Each
answer permits at most five model requests and three tool calls; undeclared
proposals can add up to three independently bounded admission requests. Provider-only and Live writes are not completed
by this increment; their existing context and routing remain intact.

## Idempotence and Recovery

Only dedicated internal sim learners receive test writes. Sim shares the CN
production database; production probes are read-only. Private evidence stays out
of Git. No production engine switch or 1.0 removal.

## Interfaces and Dependencies

No schema, dependency, environment variable or public SSE changes. Any internal
optional handoff parameter is coordinated between the text host and ask handler.
