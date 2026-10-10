# Progressive HTML alongside typed lesson text

## Purpose / Big Picture

Keep the typewriter effect for lesson and follow-up prose while displaying
content in source order. HTML waits until all preceding prose has finished
typing, then displays the latest received fragment immediately and progressively,
including unclosed HTML. HTML itself never receives a character-by-character
typewriter effect; HTML-only snapshots display immediately.

## Progress

- [x] 2026-10-09 UTC: Traced the pinned markdown-flow-ui 0.2.29 renderer and confirmed that raw mixed content enters the text queue before HTML segmentation.
- [x] 2026-10-09 UTC: Prepared clean branches from current remote main in both repositories.
- [x] 2026-10-09 UTC: Implemented segment-aware typing in markdown-flow-ui PR https://github.com/ai-shifu/markdown-flow-ui/pull/248; 566 unit tests, lint, format, package tests, export types, Storybook build and Chromium interaction passed.
- [x] 2026-10-09 UTC: Verified the actual built renderer with React 18.3.1 and real iframe DOM; AI-Shifu 2,975 Jest tests passed. Consumer typecheck has only the same two existing test errors as the current pin.
- [x] 2026-10-09 UTC: User confirmed formal version 0.2.30 from sunner/progressive-html-rendering at fb08875e619bd251b8ff9975ebc6e9fd8c7ade41; dispatched Publish (manual) run 37920734690 with these exact inputs.
- [x] 2026-10-09 11:08 UTC: Verified npm 0.2.30 is available from the official registry with gitHead fb08875e619bd251b8ff9975ebc6e9fd8c7ade41, matching the confirmed source.
- [x] 2026-10-09 UTC: Updated AI-Shifu's exact release pin and lockfile. The installed npm 0.2.30 renderer passed the React 18.3.1 iframe/prose smoke test; library PR CI is green, including Sonar.
- [x] 2026-10-09 UTC: The complete repository gate passed for the dependency upgrade, and the consumer PR was prepared. Type checking against the published package matches the previous pin's two existing admin test errors exactly.
- [x] 2026-10-09 14:00 UTC: Library review fixes through 83f27ced6fa6a357bf895087cb91e22baef60045 passed 773 unit tests, package checks and current-head CI. All 13 existing review threads were resolved after verification; version 0.2.31 is prepared but unpublished.
- [x] 2026-10-09 UTC: Compared the frontend with the exact pinned markdown-flow 0.3.4 wheel and reproduced missing block roots, HTML-comment false positives, quadratic suffix parsing, and video remounts caused by preceding Markdown structures or trailing link definitions.
- [x] 2026-10-09 UTC: Replaced recursive streaming detection with one source analysis and an absolute-offset scan in library commit 95482b9; 199 focused tests passed, including legacy behavior and oversized-source parse counts. Same Chrome 400-block single-character append benchmark improved from about 2.3 seconds to 13.5 milliseconds.
- [x] 2026-10-09 UTC: Compiled native-video Markdown from each complete received run once per snapshot and projected visible text without reparsing on typing ticks or replacing existing video ancestors. Added entity/escape, control activation, Mermaid recovery and unfinished SVG regressions.
- [x] 2026-10-09 UTC: Fixed current-head review feedback for nontext leaf pacing and direct AST type dependencies in separate commits 5c7e826 and 50f132e. Native presentation and sibling/pending-video boundaries are fixed in ff1ee45; four locale Storybook failures are repaired without changing their assertions.
- [x] 2026-10-09 UTC: Preserved the ordinary renderer's HTML indentation/newline normalization in stable video runs, mapping normalized AST positions back to the original source. Separate commit 4647370 covers custom controls, raw typing budgets, CRLF, entities and unfinished SVG.
- [x] 2026-10-09 UTC: Protected parsed and pending link/image/reference metadata from HTML and SVG extraction, including the typed render prefix and stable-video path. Real HTML inside block bodies remains immediate; invalid links do not consume following markup.
- [x] 2026-10-09 UTC: Fixed image-alt extraction in separate commit d05c417, including pending labels, nested brackets, later reference definitions, exact final alt values, escaped characters and entities.
- [x] 2026-10-09 UTC: Fixed the new resumed-prose quoted/list-fence review in separate commit 47ec978. Shared absolute-offset fence detection prevents code-internal pending metadata from hiding real HTML, and normalization preserves container indentation through both rendering paths.
- [x] 2026-10-09 UTC: Validated the final expanded regressions, browser iframe identity, parser counts and measured scaling. All 1,151 unit tests and all 143 browser tests pass.
- [x] 2026-10-09 UTC: Added the missing direct pnpm parser entry in independent commit 2a284a1. Verified the wide-SVG review as a false positive in real Chrome and added persistent browser coverage in ceae774, including ContentRender stories in CI.
- [x] 2026-10-09 UTC: Fixed generated task-checkbox activation in independent commit e9493f1. The received AST supplies each marker's raw range without per-tick parsing; all 1,191 unit tests, 143 browser tests and 24 real-Chrome task combinations pass.
- [x] 2026-10-09 UTC: Fixed ordinary structural activation in independent commit 84818c7. Code toolbars, list bullets and table borders wait for their own source start; immediate HTML/video ancestors stay active. All 1,261 unit tests, 143 browser tests, 24 new real-Chrome structure combinations and 24 repeated task combinations pass.
- [x] 2026-10-09 UTC: Fixed the source-tree declaration omission in independent commit 3aecd9c by naming its existing immutable return type. The build emits the missing internal declaration without TS7056, and npm pack includes it; package, export types and Storybook build pass.
- [x] 2026-10-09 18:23 UTC: Current library head 3aecd9c passes all CI checks. After the required five-minute wait, Codex reports its review completed for this head, all 22 threads are resolved, no new actionable feedback remains, and GitHub reports the PR clean and mergeable.
- [x] 2026-10-09 21:23 UTC: Library PR 248 merged. The user confirmed version 0.2.31, main and full SHA ddbd3cab2d3ece13575d3047c672c3c4cc02165a. Publish run 37992324098 succeeded; the official npm registry confirms that version, source SHA and latest tag.
- [x] 2026-10-09 21:25 UTC: Synced consumer PR 3069 with main in 09a27d9. Bump markdown-flow-ui run 37993184719 succeeded and produced 74737a8, pinning 0.2.31 exactly with the official tarball integrity.
- [x] 2026-10-09 21:36 UTC: Clean-installed the consumer with Node 22.16.0 / npm 10.9.2 and removed only three redundant nested React peer lock entries. The actual npm 0.2.31 renderer passes the persistent progressive HTML/backend roots/code boundary/video-state regression with natural React 18.3.1 resolution and no warnings. The isolated official 0.2.30 control fails specifically on immediate figure rendering.
- [x] 2026-10-09 21:36 UTC: Consumer focused tests pass (8 suites / 161 tests), and the full suite passes (258 suites / 3,001 tests). Typecheck output matches the post-main-sync baseline exactly, with only two existing admin user-page test errors. Development tools and the complete repository pre-commit gate pass. Frontend CI now includes the actual installed-package regression; current-head CI and reviews are tracked in PR 3069 before merging.
- [x] 2026-10-09 22:23 UTC: Moved the installed-package regression into six normal Jest cases, reusing the existing test configuration and JSDOM environment. Removed the standalone script and extra CI step. All 3,007 tests in 259 suites pass; typecheck still matches the same two-error baseline. An isolated official 0.2.30 Jest control fails the expected figure, aside and video cases, while 0.2.31 passes all six.
- [x] 2026-10-09 22:51 UTC: Consumer PR 3069 merged with the exact 0.2.31 release.
- [x] 2026-10-09 UTC: Library PR 251 merged with source-order HTML and native-video activation. Prepare the exact 0.2.32 consumer upgrade and update the installed-renderer regression to match the revised timing requirement.
- [x] 2026-10-09 UTC: The local 0.2.32 package candidate passes all nine renderer behavior cases and 3,010 frontend tests in 259 suites. The manifest/lockfile identity case remains excluded until official publication. The official 0.2.31 control fails seven new ordering assertions. Type checking is byte-identical to the original 0.2.31 baseline, with only the same two admin user-page test errors; focused lint, formatting, development tools, repository harness and architecture boundaries pass.
- [x] 2026-10-10 00:50 UTC: Verified official 0.2.32 publication from the human-confirmed main commit 4f8680d5c8eff4efab32e35d754c1e24301201fb. Publish run 38006389531 succeeded; registry version, gitHead, latest tag and tarball shasum match. Generated the exact consumer lock through npm 10.9.2 with only the package pin, version, registry URL and integrity changed; no nested React peers or local candidate paths were introduced.
- [x] 2026-10-10 UTC: Clean-installed official 0.2.32 with Node 22.16.0 / npm 10.9.2 after syncing consumer main through f7d552fe. All 3,040 frontend tests in 260 suites pass, including every installed-renderer behavior and manifest/lockfile identity case. The renderer naturally shares the app's React 18.3.1 instance. Typecheck output is byte-identical to the 0.2.31 baseline, with only the same two existing admin user-page test errors.
- [x] 2026-10-10 UTC: Development tools and the complete repository-wide lefthook gate pass. The focused consumer upgrade is prepared for review with only the manifest, npm-generated lock, installed-renderer regression and this plan changed.
- [ ] After the consumer upgrade is merged and the Web build is deployed, verify ordered prose and progressive HTML in the affected live lesson.

## Surprises & Discoveries

Reading mode intentionally stores prose and HTML in one text element. The
existing sandbox already renders incomplete HTML progressively and maintains
its iframe across content updates. Historical content bypasses typing.

The current library publishing rules require a formal release from main, after
the version preparation has merged and a human confirms the version, main and
full source SHA. The earlier feature-branch confirmation was consumed by the
0.2.30 release. The user subsequently confirmed the exact merged main SHA for
0.2.31, and that release is now published. AI-Shifu main requires a stable
release pin. A successful Publish run precedes registry availability: npm
reported package processing for several minutes before the version, gitHead,
integrity and latest tag could all be read back from the official registry.

The backend comparison uses the exact markdown-flow 0.3.4 package from
requirements.txt, not the older neighboring checkout. Its HTML root set is
broader than the frontend's former set. Its line buffering and listen-mode
pagination are different contracts and must not delay HTML in reading mode.
The former frontend splitter reparsed every remaining suffix, while masked
Markdown strings changed sibling ordinals and link-definition resolution during
typing. Both require structural fixes rather than more special-case masking.

Expanding detection must not change presentation: putting every new backend
root into the sandbox broke authored preformatted code, alerts, details and
heading anchors. Four existing locale browser stories reproduced the regression.
Detection now separates received-HTML timing from the fixed native/sandbox
presentation policy; all four original browser assertions pass.

The stable-video path must preserve the ordinary renderer's normalization, not
just its AST structure. Normalized parsing uses a monotonic map back to raw
source offsets so CRLF, indentation, entities and escapes retain their original
typing and completion budgets. Link titles can contain markup-looking examples;
both complete metadata and legitimate unfinished titles need protection across
segmentation, SVG extraction and render-prefix parsing. Invalid link syntax must
release that protection so subsequent real HTML is not hidden.

The final review also identified the missing direct remark-parse entry in the
pnpm importer. A three-line correction removes that new mismatch without
regenerating unrelated packages. Frozen-lockfile checks on isolated before/after
copies prove the correction. The current main baseline already has a separate
remark-flow manifest/lock specifier mismatch (^1.3.4 versus ^1.2.0); that existing
issue remains outside this rendering change. With only that baseline mismatch
normalized in the isolated control, the previous lock fails for remark-parse
and the corrected lock passes.

The SVG-wrapper review was verified against actual browser behavior before
changing the tree. Existing CSS already gives both wrapper tags display:block,
width:100% and overflow-x:auto. All eight real-Chrome combinations of standalone
or inline SVG, typing on/off and both pacing modes displayed a 1,600 px SVG
inside a 400 px scroll box and accepted scrollLeft=100. Existing video DOM,
parent, browsing window and state remained stable through prose/HTML appends,
with no extra loads or page errors. The proposed tag-name-only rewrite was
withdrawn: it would put block elements inside paragraphs without fixing a
reproduced layout problem. A browser regression records the actual contract.

The complete received tree also needs source-budget activation for ordinary
containers. Stable structure must not expose future code tools, list bullets or
table borders. Generated table parents use their positioned descendants, while
missing-column cells use their direct row; authored empty leaves keep their
existing end boundary. Loose task paragraphs include their recovered child
marker's start without changing text cursors, source positions or checkbox timing.

The build previously exited successfully despite a TS7056 diagnostic that
prevented the new source-analysis declaration file from being emitted. Public
export checking alone missed this because library checking is skipped. Naming
the helper's already-declared immutable return alias fixes declaration emission;
both the generated file and its presence in npm pack were checked explicitly.

The consumer's existing lockfile retained a nested React 19 / React DOM 19 peer
installation below markdown-flow-ui while the app uses React 18.3.1. A clean
0.2.31 installation reproduced an invalid hook call in the new direct npm
renderer check. Next's App Router aliases unify those imports in the application,
so this is not evidence of the same failure in the deployed browser. The earlier
temporary Node smoke also unified React explicitly. Remove only the three
redundant nested React, React DOM and scheduler lock entries, validated with
npm 10.9.2's package-lock-only resolver. Every other package version remains
unchanged; the persistent check must run using natural module resolution.

The public renderer export loads in the existing Next/Jest configuration without
transformer exceptions or resolver changes. Its normal Jest suite uses the
existing JSDOM with inline vendor scripts disabled, matching the original DOM
regression's scope, and a local structured-clone fallback for JSDOM's missing
browser API. Fake timers verify that HTML and native videos wait for preceding
prose, that eligible HTML and subsequent appends appear without typing, and that
existing video state survives while the prose clock advances.

## Decision Log

- 2026-10-09 UTC: The user's revised timing requirement supersedes the earlier
  immediate-HTML timing decisions below. Reveal each HTML or native-video
  block only after its preceding prose is visible. Keep eligible HTML outside
  the text timer and stream its latest received fragment without waiting for
  closing tags. Preserve existing media identity while later prose types.
- 2026-10-09: Segment the received source before applying typing. HTML is
  displayed from the latest received snapshot; only prose consumes the queue.
- 2026-10-09: Preserve one element, existing callback contracts, and stable
  sandbox identities. Do not change backend paging or stored learning records.
- 2026-10-09: This corrects rendering timing without adding a user action or
  analytics contract. No new tracking event is introduced.
- 2026-10-09: Align streaming HTML block roots with backend 0.3.4, while retaining
  the frontend's code/math protections and immediate handling of incomplete
  chunks. Keep the public nonstreaming splitter's legacy behavior.
- 2026-10-09: Keep pre, details, summary, aside, blockquote, ul, ol, dl and
  table as native immediate HTML, preserving host Markdown CSS, CodeBlock and
  authored language/direction. Other visual/widget roots stay in the sandbox.
  Native blocks containing real document/widget resources use a narrow sandbox
  fallback; native data-tag=video frames are exempt. Quoted attributes, comments
  and raw-text examples do not trigger fallback. Hide incomplete native opening
  headers, but render received block bodies without waiting for closing tags.
- 2026-10-09: Share an immutable source AST analysis and scan absolute source
  offsets. Compile native-video Markdown runs once per snapshot; typing changes
  text visibility, not parsed structure. If sandbox boundaries require separate
  Markdown parsing, parse only nonoverlapping runs whose total length is bounded
  by the received source, never recursive suffixes or typing projections.
- 2026-10-09: Stable video identity applies while typing an already received
  Markdown structure and appending independent prose/HTML. New source that
  changes Markdown grammar (for example, a formerly missing reference
  definition) can legitimately change the media's parent structure, as in the
  ordinary renderer. Do not freeze old semantics or delay received HTML to
  conceal such source changes.
- 2026-10-09: Reuse the app's compatible React 18 peer installation instead of
  retaining an unnecessary nested React 19. Verify the installed npm renderer
  directly in frontend CI, without library mocks or module-resolution patches.
- 2026-10-09: Keep the installed-renderer regression in the existing Jest suite
  and normal frontend test command so it uses the same reporting and CI path
  as the other frontend tests.
- 2026-10-09: Parse normalized stable-video source only when a received snapshot
  changes, then restore raw positions before projecting visibility. Keep public
  callbacks and budgets in authored-source coordinates. Protect unfinished link
  metadata in render copies without changing the received source or valid final
  link attributes; expire pending protection when the syntax becomes invalid.

## Outcomes & Retrospective

The source-order follow-up uses library PR 251 and the exact published 0.2.32
release from main at 4f8680d5c8eff4efab32e35d754c1e24301201fb. Publish run
38006389531 succeeded. At 2026-10-10 00:50 UTC, the official registry confirmed
the version, gitHead and latest tag, with tarball shasum
18b01e837f6d21472769a9051563e82785daee2f. The npm-generated lock records the
official registry integrity without unrelated package changes or nested React
peers. The consumer regression covers fixed and content-aware pacing,
unfinished sandbox/native HTML, HTML-only streams, deferred native videos and
retained video state while later content becomes eligible. The official clean
installation passes all 3,040 frontend tests in 260 suites, including the exact
installed-package, manifest and lockfile identity case. The app and renderer
naturally resolve the same React 18.3.1 instance. Typecheck output remains
byte-identical to the original two-error baseline. Development tools and the
complete repository-wide lefthook gate pass. The consumer upgrade is prepared
for review. The earlier local candidate is preview evidence only;
it passes all nine renderer behavior cases and 3,010 frontend
tests in 259 suites, with only the version/lockfile identity check excluded.
The official 0.2.31 control fails seven ordering assertions, confirming that
the new checks detect the previous eager-HTML behavior. Type checking matches
the original baseline byte for byte, with two existing admin test errors.
The earlier 0.2.31 rollout results follow for historical context.

Library PR 248 merged and the corrected 0.2.31 release was published from
main at ddbd3cab2d3ece13575d3047c672c3c4cc02165a, using the exact inputs
confirmed by the user. Publish run 37992324098 succeeded. The official npm
registry confirms that gitHead, version and latest tag; consumer bump run
37993184719 produced 74737a8 with the exact 0.2.31 pin and matching integrity
sha512-vLBCy48FGNuBzydt1lT4pHfIGKHDvYc9U6GXyoTLGHCKVMQ4J7SQRemdXfbXAnSyLqsd8CbA5cUm4L4kio3QWA==.
The merged source tree is identical to the final tested library branch tree.
The consumer clean installation uses the app's React 18.3.1 peer naturally,
without resolver patches. The persistent installed-package regression verifies
unfinished HTML and appends before prose ticks, backend figure/aside roots,
inert fenced examples and stable video DOM, parent, browsing window and state.
The six normal Jest cases also advance the prose clock while preserving video
state. The official 0.2.30 Jest control fails figure, aside and video assertions,
while 0.2.31 passes all six. All 3,007 consumer Jest tests in 259 suites pass.
Type checking has exactly the same two admin user-page test errors
as the current-main baseline before this upgrade, with byte-identical output.
Frontend CI includes the installed-package regression in its normal Jest suite;
there is no separate renderer script or additional workflow step.
Current-head CI and review convergence remain a PR merge requirement.
The final library source at 3aecd9c614a8c88420cd84ba68602129c64fc379 passes
1,261 unit tests in 81 files, lint, formatting, the package build and five asset
checks. Public export checks and the built renderer's four React 18.3.1 smoke
checks pass. All 143 browser regressions, including 24 ContentRender stories,
and the Storybook build pass locally. The CI browser job now includes those
ContentRender stories. Real Chrome retains iframe DOM, direct
parents, ancestors, browsing windows and state across 16 structure/pacing
combinations and eight native HTML boundary combinations, without extra loads.
Another 44 normalization/link-metadata combinations keep markup examples inert,
raw callback lengths exact and real videos stable with typing on/off and both
pacing modes. Another 40 real-Chrome image/fence combinations and 40 per-tick
container-fence component cases cover ordinary and stable-video rendering,
backtick/tilde markers and normalization without changing custom HTML controls.
Focused regressions also cover legitimate pending titles, invalid links, adjacent HTML roots, block-body text, CRLF, entities and escapes.
Full-project type checking has only the same pre-existing ten errors in
ScrollToBottomControl.stories.tsx. Current-head CI run 37972247499 passes,
including 1,261 unit tests and 143 Chromium browser tests. The release-version
check and SonarCloud also pass; Cursor's check is neutral. A live review refresh
after the five-minute wait confirms all 22 threads resolved, no new actionable
feedback and a completed Codex review for 3aecd9c. CodeRabbit remains paused
after its earlier reviews; its success status is not a new review of this head.
The library PR was clean and mergeable before merging. Verified feedback was replied
to and resolved after independent
commits 4647370, 0ea2333, 47ec978, 2a284a1, e9493f1 and 84818c7. The wide-SVG finding was
checked against existing CSS and eight real-Chrome cases, replied to with the
measurements, and resolved as invalid; ceae774 adds persistent behavior coverage
without changing the working runtime tree. Another 24 real-Chrome task-list
combinations and 24 component cases verify checkbox activation at the first
budget covering its closing bracket, including tabs, quoted CRLF, cross-line
markers, nested/loose items and authored HTML inputs. Existing video identity,
state, checked/disabled semantics and raw callbacks remain stable. Chrome also
passes 24 structural activation combinations covering deferred ordinary
containers, generated table ranges, authored empty-cell boundaries, native HTML
normalization and stable immediate media ancestors. The source-tree declaration
fix in 3aecd9c removes TS7056; its internal declaration is emitted and included
in the npm package without changing the immutable type contract.
Production deployment is outside the current change; the live lesson will
require the updated Web build. Keep the plan active until that external
acceptance is verified.

## Context and Orientation

The owning library is ai-shifu/markdown-flow-ui, principally
src/components/ContentRender/ContentRender.tsx and utils/split-content.ts.
AI-Shifu consumes its exact release through src/web/package.json and
src/web/package-lock.json. ContentBlock and AskBlock pass mixed source strings
to ContentRender, so the shared library owns the fix.

## Plan of Work

Create source segments first, keep HTML outside the text timer, and reveal each
block only when preceding prose reaches its source position. Project typed
prose back into its original segment positions. Keep invisible prose
positions stable so their appearance does not remount existing sandboxes. Add
mixed-stream regressions and a reproducible Storybook example, then validate the
library package and consuming application before preparing the stable bump.
Replace per-suffix parsing with one source AST analysis and a linear source
scan. Native videos must render against a stable AST so preceding headings,
independent lists/quotes and reference definitions cannot remount them. Expand
Storybook and regression fixtures to cover these boundaries and backend roots.

## Concrete Steps

1. Run focused HTML and existing typewriter tests.
2. Run the library unit suite, formatting, lint, package build and export checks.
3. Exercise the built mixed-content story and AI-Shifu content/gate tests.
4. Prepare a ready library PR and exact formal release inputs.
5. After release confirmation, publish via Publish (manual), verify npm, and
   update the exact AI-Shifu pin and lockfile in a focused PR.

## Validation and Acceptance

HTML after unfinished prose must remain absent until that prose finishes.
Once eligible, unclosed HTML must reach the sandbox without consuming another
typing tick, and HTML appends must update immediately. HTML-only snapshots must
render without advancing fake timers. Prose before and after HTML must retain
existing pacing and source order. Native videos follow the same preceding-prose
gate. Sandboxes must not remount
when prose appears. Completion must wait for all prose and account for the
current received snapshot. Fenced HTML examples must remain code. Existing
plain-text pacing, grapheme, streaming deadline and history behavior must pass.
Standalone backend block roots including figure, table, canvas, video, header,
nav and details must bypass typing. HTML inside comments, attributes, code or
math must stay inert. Native presentation blocks must retain their existing
styles, locale attributes and component behavior. Nontext prose leaves such as
thematic breaks and generated line breaks must follow their exact source budget.
Link titles and image alt text must remain literal while typing or receiving
partial syntax, including references with later definitions. Quoted and nested
list fences directly after HTML must retain their indentation and code scope;
unclosed examples inside them must not hide following real HTML or videos.
Streaming detection must parse once per input snapshot,
including sources larger than the bounded cache. Native-video iframe nodes,
parents and contentWindow sentinels must survive every typing tick and later
source appends, including preceding siblings and trailing reference definitions.

## Idempotence and Recovery

Use isolated branches and preserve unrelated local checkouts. Keep release
publishing behind the library's exact-input confirmation rule. Do not merge a
development pin to main. A dependency rollback restores the previous exact pin
and matching lockfile; no data migration is required.

## Interfaces and Dependencies

Preserve ContentRender's public props and completion callback API. Internal
typing progress must include eligible HTML while tracking only prose in the
timed queue. The consumer pins the exact published 0.2.32 release; its lockfile
records the official registry tarball and integrity, with no local candidate
paths or unrelated dependency changes.
