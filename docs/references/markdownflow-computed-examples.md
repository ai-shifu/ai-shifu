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
turns do not offer this field or promise whole-response withholding. Canonical displayed text is saved as normal teaching alongside
the original tool arguments and survives the usual session round trip.

The optional field is explicitly an object in the offered Ark/OpenAI/DashScope
schemas; it is omitted, along with its definitions, when unavailable. Native
validation stays authoritative. A provider accepting a schema does not establish
strict decoding or a first-generation model pass.

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

This creates no new Cook Web action or invocation path; existing lesson/input
analytics remain unchanged. Generated programs and teaching text must not be
added to analytics metadata.

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

See the [execution plan](../exec-plans/active/mdf2-computed-examples.md) for current
implementation, review, deployment and acceptance receipts.
