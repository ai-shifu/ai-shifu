# Operator Course Detail Tab Splitting

## Purpose / Big Picture

Keep `src/cook-web/src/app/admin/operations/[shifu_bid]/page.tsx` as the route
entry for the operator course detail page, but progressively split heavy tab UI
into dedicated local components so the page stays reviewable and safe to extend.
Phase A focuses only on the credit usage tab because it is the newest and most
self-contained block. Later phases can split the users tab and the chapters tab
without changing backend contracts.

## Progress

- [x] 2026-05-13 18:10 CST: Reviewed the course detail page structure and
  confirmed the credit usage tab is the safest first extraction target.
- [x] 2026-05-13 18:35 CST: Split the credit usage tab into a dedicated sibling
  component while keeping request/state orchestration in `page.tsx`.
- [x] 2026-05-13 18:45 CST: Recorded the later users/chapters split order in the
  requirement and optimization docs.
- [ ] 2026-05-13 18:50 CST: Split the users tab into a dedicated local
  component after the credit usage extraction stabilizes.
- [ ] 2026-05-13 18:50 CST: Split the chapters table and chapter-detail display
  helpers after the users tab extraction stabilizes.

## Surprises & Discoveries

- The page had already grown past 3,000 lines before the credit usage block was
  extracted, so even “small” tab additions now create high review overhead.
- The credit usage tab owns its own column-sizing behavior and filter rendering,
  which makes it a good first split candidate without forcing route-level state
  changes.
- The repository already contains a reusable `ClearableTextInput` under
  `src/cook-web/src/app/admin/operations/orders/orderUiShared.tsx`, which can be
  reused instead of adding another one-off input implementation.

## Decision Log

- Decision: split only the credit usage tab in this pass.
  - Why: it keeps the refactor aligned with the active feature branch and avoids
    mixing older chapter/user logic into the same regression surface.
- Decision: keep data fetching, tab switching, and route context in
  `page.tsx`.
  - Why: this preserves current behavior and leaves later extractions with a
    stable orchestration layer.
- Decision: record later tab splits in docs now instead of trying to finish the
  whole page in one pass.
  - Why: the user explicitly wants staged follow-up work, not a one-shot page
    rewrite.

## Outcomes & Retrospective

- Phase A should leave the course detail page functionally unchanged for
  operators while reducing the size of `page.tsx` and isolating the newest tab.
- If this pattern proves stable, the same route-orchestration plus local-tab
  rendering split can be repeated for the users and chapters areas.

## Context and Orientation

Relevant files:

- `src/cook-web/src/app/admin/operations/[shifu_bid]/page.tsx`
- `src/cook-web/src/app/admin/operations/[shifu_bid]/CourseCreditUsageTab.tsx`
- `src/cook-web/src/app/admin/operations/operation-course-types.ts`
- `src/cook-web/src/app/admin/operations/[shifu_bid]/page.test.tsx`
- `docs/product-specs/operator-course-detail-page.md`
- `docs/需求和优化.md`

The page already owns three bottom tabs: chapters, users, and credit usage.
This plan does not redesign their behavior. It only changes where tab-local UI
lives.

## Plan of Work

1. Isolate the credit usage tab rendering into a sibling component.
2. Keep page-level request/state orchestration in `page.tsx`.
3. Reuse existing shared admin UI pieces where possible.
4. Record the next split order in the requirement and optimization docs.
5. Validate with focused frontend tests and lightweight static checks.

## Concrete Steps

1. Add or reuse shared UI types needed by both `page.tsx` and the new credit
   usage component.
2. Create `CourseCreditUsageTab.tsx` beside the route entry.
3. Move tab-local filter rendering, table rendering, pagination rendering, and
   column-width behavior into the new component.
4. Replace the inline credit usage tab JSX in `page.tsx` with the new
   component.
5. Update docs with the future split sequence.
6. Run the focused course detail frontend test and local syntax/diff checks.

## Validation and Acceptance

- The course detail page still opens and switches tabs as before.
- The credit usage tab still loads on demand and shows the same filters, rows,
  and pagination behavior.
- The existing focused test at
  `src/cook-web/src/app/admin/operations/[shifu_bid]/page.test.tsx` passes.
- No new syntax errors are introduced in touched frontend files.

## Idempotence and Recovery

- Re-running the refactor should be safe because the route-level contracts do
  not change.
- If a later tab split stalls, the page remains usable because each extraction
  is scoped to one tab at a time.
- If column-width behavior regresses, the fallback is to keep the route-level
  fetch/state work intact and restore only the extracted tab component.

## Interfaces and Dependencies

- Frontend route entry: `src/cook-web/src/app/admin/operations/[shifu_bid]/page.tsx`
- Shared admin UI pieces:
  - `AdminTableShell`
  - `AdminPagination`
  - `AdminDateRangeFilter`
  - `useAdminResizableColumns`
- Shared typed contract surface:
  `src/cook-web/src/app/admin/operations/operation-course-types.ts`
- Documentation surfaces:
  - `docs/product-specs/operator-course-detail-page.md`
  - `docs/需求和优化.md`
