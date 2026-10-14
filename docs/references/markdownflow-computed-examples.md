# Computed integer-program examples

The AI-Shifu host enables the optional `Engine(computed_examples=True)` capability.
Portable engines keep it off by default. It is offered only for a supported
returned authored text input, where ordinary feedback already waits for native
validation. Initial, unsupported and text-only turns retain the existing schema
and streaming behavior. This is not a second lesson DSL or an answer grader.

## Same-response contract

A model can attach `computed_example` to its **existing** `interact` call. The
payload declares initial PC, registers, data cells and instructions. It accepts
no model-authored result rows, final values, summary or asserted termination.
The backend executes those declarations and emits ordinary Markdown containing
that exact program, its initial state and the computed state table before the
existing controls. This adds no model request, planning tool or learner input.
Native retries and all original request/input budgets remain unchanged.

A computed response uses only that one existing interaction, with the current
feedback object when required. It cannot accompany a checking direction or
another tool call, or an unavailable confirm pause. The source/phase, input representability, author navigation
and memory guards still apply before any artifact is delivered. Invalid calls
retain original arguments and retry errors. On these supported buffered turns,
they contribute no visible artifact or rejected prose. Initial and unsupported
turns do not offer this field or promise whole-response withholding. If a model
invents it on such a turn, the artifact is refused and mixed side effects stay
blocked; already streamed prose remains in saved teaching. Canonical displayed text is saved as normal teaching alongside
the original tool arguments and survives the usual session round trip.

The optional field is explicitly an object in the offered Ark/OpenAI/DashScope
schemas; it is omitted, along with its definitions, when unavailable. Native
validation stays authoritative. A provider accepting a schema does not establish
strict decoding or a first-generation model pass.

With the capability enabled, the SDK's native before-tool-validation hook applies
the sole-call check to every tool, including supplied AbstractToolsets, before
custom argument validators or tool functions run. Normal standalone custom calls
retain their behavior; a rejected computed batch cannot invoke their side effects.

## Explicit machine

- One instruction occupies one address; ordinary fall-through advances PC by 1.
  Initial PC and branch targets identify declared instructions.
- Register names are short ASCII identifiers; PC is reserved for control flow.
  All referenced registers and data cells require explicit initialization.
  Registers and data are mutable integer state; data/code addresses cannot overlap.
- SET copies an integer or another register; ADD/SUB update a register using an
  integer or register operand. LOAD reads a declared data address into a register;
  STORE writes the named register into a declared data address.
- JMP takes an explicit target. JZ/JNZ compare the named register with zero;
  JLT compares it with its integer/register operand. HALT stops execution.
- At most 32 instructions, 8 registers, 16 data cells and 32 executed steps; addresses
  range 0..4095 and all values stay within plus/minus one billion. Out-of-range
  arithmetic is refused; no overflow or implicit initial value is inferred.
  The 32-step ceiling keeps simultaneous maximum-width state columns and program
  declarations within the existing 16 KiB artifact limit. It does not raise any
  model request, token, input or retry budget.
- There is no external code, eval/exec, input/output, filesystem/network access,
  float arithmetic, self-modifying code or arbitrary instruction implementation.

On a supported turn with this capability enabled, empty, unparseable or non-object
interact JSON remains buffered through native validation even when the separate
feedback contract is off. Original arguments and retry errors remain evidence;
failed prose never becomes delivered teaching.

The table includes initial state and states after actual instructions. HALT is
shown only when reached. An exactly repeated complete PC/register/data state
establishes a cycle only in this deterministic no-IO language. An optional finite
`steps` prefix ends with an ellipsis and never proves termination. Exhausting the
execution budget without such a prefix refuses the artifact; it is not a halt.

## Rendering and ownership

All output remains ordinary `ContentDelta`/saved `TextPart`. The current shared
1.0 `StreamFormatter`, pager and element adapter own splitting, type, numbering,
HTML attachments, history and audio. No frontend, DTO, SSE, session schema or
new parser is introduced. Code and tables keep their existing visual/speech
classification; listening still synthesizes only existing speakable text.

### Accepted-use analytics contract

- Business question: does the optional capability produce canonical artifacts
  in real learner streams, and in which learning mode?
- Metric: weekly raw accepted artifact-stream emissions grouped by learning mode.
  This is not a distinct-user count, an offered-to-used conversion rate, proof of
  browser visibility, a factual score, or a billing record. Missing best-effort
  events do not prove zero use; actual model schemas/calls stay in Langfuse.
- Event: `learner_computed_example_streamed`, after the accepted canonical
  artifact fragments have been yielded, before the existing input control.
  Invalid/retried payloads, omitted fields and initial unsupported calls do not
  emit. Loading stored history emits nothing. A deliberate new regeneration or
  rewind counts again only if it actually streams a new accepted artifact.
- Population: published learner requests, including guests, members and internal
  testing. Teacher/editor preview is excluded. Deployment/site configuration
  separates environments; this event has no test-user classifier and must not
  be presented as production-only adoption without a site's traffic filter.
- Count/deduplication: one event per accepted native tool-call identity within
  one engine turn; no persisted cross-request deduplication. The identity is used
  in memory only and never sent. Retry responses and rerendering cannot inflate it.
- Producer: an optional zero-content engine observer, bound by the lesson host
  to the shared bounded asynchronous server tracking path. It never changes the
  formatter, frontend, SSE, DTO or stored teaching. Missing configuration, full
  queue, worker/network failure or an observer exception cannot change delivery.
- Complete feature payload: `{surface: "learner", learning_mode: "read" | "listen"
  | "classroom"}`. Both fields are non-personal low-cardinality enums required to
  distinguish product surface and mode. No identity, course/lesson/call ID,
  prompt, program, state, value, answer, generated text, URL or error is sent.
  The transport envelope has the configured website, fixed server hostname,
  fixed `/backend/lesson/computed-example` route and the fixed event name. No
  identify metadata, browser context or referrer is added.
- Consumer: weekly aggregate capability-use counts by mode in Umami. New additive
  family, no historical rename/backfill or checked-in dashboard to migrate.
  Compare environment-scoped event counts only; do not join these anonymous
  counts one-to-one to learners, traces, ledger rows or correctness outcomes.
- Verification: native SDK timing/deduplication/rejection/omission/history and
  callback-failure controls; host preview/mode wiring; exact delivered payload,
  asynchronous queue/config/network failure and sensitive-field exclusions.
  Local tests do not establish deployed Umami ingestion or browser exposure.

The shared [analytics contract](frontend-product-analytics.md) remains normative.
Generated programs and teaching text must never enter event metadata.

## What remains unverified

A correct execution table does **not** establish that the model selected the
requested example, followed authored brevity/disclosure rules or explained its
meaning correctly. Surrounding prose remains model-authored and is not certified.
The model must not repeat or reinterpret the numeric program/table in prose;
compliance with that instruction still needs independent real-model acceptance.
Never use this capability to repair author/learner source or introduce new passing
criteria. It does not provide model judgments about permissions or knowledge.

Controlled tests establish numerical semantics, native one-request delivery,
rejected-response isolation and existing formatter/storage compatibility. They
cannot release #3122's original fast-model factual failure or the fresh ordinary
HTTP eleven-question natural-compaction/statistics/summary/billing gate.

## Independent ordinary-classroom result (2026-10-14)

Code head 1d8f5ee8e passed its eleven CI checks and actual Codex/CodeRabbit reviews.
Deployed sim-8cf56ef matches that runtime; both Ready APIs match 73 source files
and pass 531 isolated SDK/logging cases. Controlled guarantees remain as scoped.

The first fresh balanced-model knowledge follow-up fails: it calls a program a
two-iteration loop, but its explicitly labelled ADD body executes once before
HALT. Arithmetic and termination are correct. All four actual follow-up inputs
offer computed_example and its guidance; all calls omit that optional field.
No real computed artifact is exercised, so this experiment does not establish
coverage of freely written examples or full classroom factual correctness.

Stop after two ordinary HTTP requests and five generations, all 46.09 credits
settled with raw-output/token/attempt/block/owner/source binding. Three native
retries remain separate from factual acceptance. Six history elements match
streamed types and content exactly across two reads; rejected responses have no
saved TextParts. Source and prior classrooms remain unchanged. A read-only
browser probe reaches login and is not a visual pass. Keep #3137 and #3122 held;
eleven questions, natural compression, actual summaries and final statistics
remain incomplete. No paid replay, resampling, course rewrite or budget increase
follows this failure.

See the [execution plan](../exec-plans/active/mdf2-computed-examples.md) for current
implementation, review, deployment and acceptance receipts.
