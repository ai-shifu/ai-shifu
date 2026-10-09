# Progressive HTML alongside typed lesson text

## Purpose / Big Picture

Keep the typewriter effect for lesson and follow-up prose while displaying
received HTML immediately and progressively, including unclosed HTML fragments.
HTML must not wait for either a complete block or the preceding prose queue.

## Progress

- [x] 2026-10-09 UTC: Traced the pinned markdown-flow-ui 0.2.29 renderer and confirmed that raw mixed content enters the text queue before HTML segmentation.
- [x] 2026-10-09 UTC: Prepared clean branches from current remote main in both repositories.
- [x] 2026-10-09 UTC: Implemented segment-aware typing in markdown-flow-ui PR https://github.com/ai-shifu/markdown-flow-ui/pull/248; 566 unit tests, lint, format, package tests, export types, Storybook build and Chromium interaction passed.
- [x] 2026-10-09 UTC: Verified the actual built renderer with React 18.3.1 and real iframe DOM; AI-Shifu 2,975 Jest tests passed. Consumer typecheck has only the same two existing test errors as the current pin.
- [x] 2026-10-09 UTC: User confirmed formal version 0.2.30 from sunner/progressive-html-rendering at fb08875e619bd251b8ff9975ebc6e9fd8c7ade41; dispatched Publish (manual) run 37920734690 with these exact inputs.
- [x] 2026-10-09 11:08 UTC: Verified npm 0.2.30 is available from the official registry with gitHead fb08875e619bd251b8ff9975ebc6e9fd8c7ade41, matching the confirmed source.
- [x] 2026-10-09 UTC: Updated AI-Shifu's exact release pin and lockfile. The installed npm 0.2.30 renderer passed the React 18.3.1 iframe/prose smoke test; library PR CI is green, including Sonar.
- [x] 2026-10-09 UTC: The complete repository gate passed for the dependency upgrade, and the consumer PR was prepared. Type checking against the published package matches the previous pin's two existing admin test errors exactly.
- [ ] 2026-10-09 UTC: After the consumer PR is merged and the Web build is deployed, verify the first HTML block in the affected live lesson.

## Surprises & Discoveries

Reading mode intentionally stores prose and HTML in one text element. The
existing sandbox already renders incomplete HTML progressively and maintains
its iframe across content updates. Historical content bypasses typing.

The library's AGENTS.md requires explicit confirmation of the version, branch,
and full source SHA before a formal npm release. Development publication is
allowed without that confirmation. AI-Shifu main requires a stable release pin.

## Decision Log

- 2026-10-09: Segment the received source before applying typing. HTML is
  displayed from the latest received snapshot; only prose consumes the queue.
- 2026-10-09: Preserve one element, existing callback contracts, and stable
  sandbox identities. Do not change backend paging or stored learning records.
- 2026-10-09: This corrects rendering timing without adding a user action or
  analytics contract. No new tracking event is introduced.

## Outcomes & Retrospective

Implementation and local verification are complete in the library PR. Formal
release inputs confirmed by the user: version 0.2.30, branch
sunner/progressive-html-rendering, source SHA
fb08875e619bd251b8ff9975ebc6e9fd8c7ade41. Publish run 37920734690 succeeded,
and the official npm registry confirms the same source SHA. The library CI
passed functional, package and browser checks. Sonar duplication was confined
to new tests; those 33 scenarios were parameterized without changing the
published runtime source; its latest CI, including Sonar, is green. The consumer
pin and integrity match the official release, and the installed npm renderer
passes the React 18.3.1 iframe/prose smoke test. Production deployment is outside
the current change; the live lesson will require the updated Web build. Keep the
plan active until that external acceptance is verified.

## Context and Orientation

The owning library is ai-shifu/markdown-flow-ui, principally
src/components/ContentRender/ContentRender.tsx and utils/split-content.ts.
AI-Shifu consumes its exact release through src/web/package.json and
src/web/package-lock.json. ContentBlock and AskBlock pass mixed source strings
to ContentRender, so the shared library owns the fix.

## Plan of Work

Create source segments first, keep HTML outside the text timer, and project the
typed prose back into its original segment positions. Keep invisible prose
positions stable so their appearance does not remount existing sandboxes. Add
mixed-stream regressions and a reproducible Storybook example, then validate the
library package and consuming application before preparing the stable bump.

## Concrete Steps

1. Run focused HTML and existing typewriter tests.
2. Run the library unit suite, formatting, lint, package build and export checks.
3. Exercise the built mixed-content story and AI-Shifu content/gate tests.
4. Prepare a ready library PR and exact formal release inputs.
5. After release confirmation, publish via Publish (manual), verify npm, and
   update the exact AI-Shifu pin and lockfile in a focused PR.

## Validation and Acceptance

Unclosed HTML must reach the sandbox without advancing fake timers. HTML
appends must update while preceding prose is still typing. Prose before and
after HTML must retain existing pacing and order. Sandboxes must not remount
when prose appears. Completion must wait for all prose and account for the
current received snapshot. Fenced HTML examples must remain code. Existing
plain-text pacing, grapheme, streaming deadline and history behavior must pass.

## Idempotence and Recovery

Use isolated branches and preserve unrelated local checkouts. Keep release
publishing behind the library's exact-input confirmation rule. Do not merge a
development pin to main. A dependency rollback restores the previous exact pin
and matching lockfile; no data migration is required.

## Interfaces and Dependencies

Preserve ContentRender's public props and completion callback API. Internal
typing progress must include immediately displayed HTML while tracking only
prose in the timed queue. AI-Shifu uses the exact published release 0.2.30;
its lockfile records the official registry tarball and integrity.
