# Skip learner memory for fixed interaction actions

## Purpose / Big Picture

Learner memory should reflect answers that can vary. A confirmation or a single fixed option lets the learner advance. Saving that selection as a personal answer can replace useful memory with a button value.

## Progress

- [x] 2026-11-18 07:03 CST: Traced learner memory and Profile evidence to the resolved native interaction.
- [x] 2026-11-18 07:10 CST: Replaced the continuation-specific rule and added coverage for fixed actions and restored text inputs.
- [x] 2026-11-18 07:16 CST: Verified the MarkdownFlow, Course and Profile suites, the interaction catalog, and architecture boundaries.
- [x] 2026-11-18 09:50 CST: Reproduced the legacy Profile finding and reused authored input repair before evaluating eligibility. All 216 Profile tests and 3,400 MarkdownFlow tests passed.

## Surprises & Discoveries

An authored input can regain its free-text field during repair. Decide whether an interaction can collect an answer after that repair. Profile also reads accepted tool results when building a draft.

## Decision Log

- Apply the rule to the resolved controls. A fixed choice skips memory even when the interaction has an authored binding or a model-provided question.
- Keep the existing model instructions and tool arguments. The backend decides whether to save the submitted interaction answer.
- Preserve the control shape, bindings used for submitting answers, and tool results used for lesson progression and history.

## Outcomes & Retrospective

The shared rule covers authored and generated controls. A fixed click still
returns a result to the model and skips the memory event. Profile applies the
same rule when reading previously accepted answers. Restored controls use their
repaired shape for both paths. The MarkdownFlow suite passed 3,400 tests and the
Course and Profile suites passed 2,254 tests. All 57 offline replay cases met
their expectations, including the two intentionally reproduced failures.
Legacy Profile histories that only contain raw tool arguments recover authored
text inputs before deciding whether the accepted answer can inform a draft.

## Context and Orientation

`InteractionSpec` describes the resolved control. `Engine.run_turn` is the source of interaction memory events, and `profile_answer_evidence` supplies accepted answers to the Profile draft. The [learner memory contract](../../product-specs/learner-memory-admission.md) covers both paths.

## Plan of Work

Replace the continuation-specific normalizer with one eligibility rule shared by the engine and Profile. Verify that a control can carry a memory binding and that a fixed selection still skips storage.

## Concrete Steps

Use the existing FunctionModel tests for fixed controls, restored sessions, choices with alternatives, and text input. Replay the interaction catalog and run the Course and Profile suites with the pinned backend dependencies.

## Validation and Acceptance

Clicking a fixed control advances the lesson without a memory update, including after reloading. Choices with alternatives and controls that accept free text continue to store eligible answers. Profile evidence contains variable answers.

## Idempotence and Recovery

The rule applies at submission and evidence read time. Existing memory rows and interaction history are retained. No migration is needed.

## Interfaces and Dependencies

The engine and Profile use the same eligibility property on `InteractionSpec`. The session and control formats remain compatible with saved data.
