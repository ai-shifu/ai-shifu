# Shared Admin Table Component

## Context

The admin operations and order pages already share a large amount of table
behavior, but the shared logic still lives inside individual pages today.

Current repetition exists across:

- `src/cook-web/src/app/admin/operations/page.tsx`
- `src/cook-web/src/app/admin/orders/page.tsx`
- `src/cook-web/src/app/admin/operations/users/page.tsx`
- `src/cook-web/src/app/admin/operations/[shifu_bid]/page.tsx`
- `src/cook-web/src/app/admin/operations/users/[user_bid]/page.tsx`

The repeated patterns include:

- loading / empty / table / footer shell structure
- resizable columns with width persistence in `localStorage`
- sticky right-side action columns
- repeated tooltip-based truncated text rendering
- repeated pagination placement and composition

Two prerequisite frontend refactors were delivered independently first:

- PR `#1542`: shared admin pagination component
- PR `#1545`: shared admin tooltip text component

This shared table work builds on top of those merged utilities and reuses them
as runtime dependencies in the migrated admin pages.

## Goals

- Introduce a shared admin table layer for operations and order pages.
- Reduce repeated table shell and column-resize logic across admin pages.
- Preserve current UX for resizable columns and sticky action columns.
- Keep pagination and tooltip text reusable as independent components.
- Make the first migration small enough to validate safely on two pages before
  wider rollout.

## Non-Goals

- Do not replace `src/cook-web/src/components/ui/Table.tsx` with an admin-only
  implementation.
- Do not merge pagination, tooltip text, and admin table shell into one
  monolithic component.
- Do not abstract page-specific filters, data fetching, dialogs, or row-level
  business actions in the first version.
- Do not force every admin table to support pagination or tooltip text.

## Existing Layering

The current and target layering should remain:

1. Base UI table primitives
   - `src/cook-web/src/components/ui/Table.tsx`
2. Independent admin utilities
   - `src/cook-web/src/app/admin/components/AdminPagination.tsx`
   - `src/cook-web/src/app/admin/components/AdminTooltipText.tsx`
3. New admin table capability layer
   - `AdminTableShell`
   - `useAdminResizableColumns`
   - sticky column style helpers
4. Page-specific business rendering
   - column definitions
   - row content
   - filters
   - dialogs
   - actions

## Proposed Shared Admin Table Layer

### 1. `AdminTableShell`

Suggested path:

- `src/cook-web/src/app/admin/components/AdminTableShell.tsx`

Responsibilities:

- render the common table container shell
- render loading state
- render empty state
- render the provided table markup
- render an optional footer slot
- optionally wrap the subtree with `TooltipProvider`

Suggested props:

- `loading`
- `isEmpty`
- `emptyContent`
- `emptyColSpan`
- `table`
- `footer`
- `withTooltipProvider`
- `containerClassName`
- `tableWrapperClassName`

Important boundary:

- `AdminTableShell` does not own pagination logic
- `AdminTableShell` does not own tooltip text logic
- `AdminTableShell` does not own column definitions or row rendering

It only provides the stable outer structure.

### 2. `useAdminResizableColumns`

Suggested path:

- `src/cook-web/src/app/admin/hooks/useAdminResizableColumns.ts`

Responsibilities:

- initialize column widths from defaults
- enforce min / max width limits
- track drag-resize interaction
- persist manual widths to `localStorage`
- restore widths after reload
- expose width styles for headers and cells
- expose resize handle rendering or props

Suggested API shape:

```ts
const { columnWidths, getColumnStyle, getResizeHandleProps } =
  useAdminResizableColumns({
    storageKey: 'adminOrdersColumnWidths',
    defaultWidths,
    minWidth: 80,
    maxWidth: 360,
  });
```

Design requirements:

- match the current user-facing resize behavior as closely as possible
- keep the API generic enough for orders, operations, and course detail tables
- avoid coupling to a specific page data type

### 3. Sticky Right Column Helpers

Suggested path:

- `src/cook-web/src/app/admin/components/adminTableStyles.ts`
  or a similarly named local helper file

Responsibilities:

- centralize shared sticky-right header styles
- centralize shared sticky-right cell styles
- preserve shadow, separator, and z-index behavior

Important boundary:

- keep this lightweight in v1
- do not introduce a heavyweight dedicated sticky-column component unless the
  first migration proves that helper functions or class constants are
  insufficient

## Why Pagination And Tooltip Stay Independent

### Pagination

Pagination should stay independent because:

- not every admin table paginates
- pagination is not inherently table-specific
- some dialog tables or summary tables are intentionally unpaginated

The table shell should expose a footer slot, and pages should pass
`AdminPagination` only when needed.

### Tooltip Text

Tooltip text should stay independent because:

- not every cell needs truncation help
- some cells render badges, buttons, or multi-line custom content
- the tooltip component is already a useful independent primitive outside the
  future table shell

Pages should continue to opt into `AdminTooltipText` at the cell level.

## Recommended Composition Pattern

After the prerequisite PRs merge, target page composition should resemble:

```tsx
<AdminTableShell
  loading={loading}
  isEmpty={items.length === 0}
  emptyContent={emptyText}
  emptyColSpan={columnCount}
  table={
    <Table>
      {/* header + body defined by the page */}
    </Table>
  }
  footer={
    pageCount > 1 ? (
      <AdminPagination
        pageIndex={pageIndex}
        pageCount={pageCount}
        onPageChange={handlePageChange}
      />
    ) : null
  }
  withTooltipProvider
/>
```

Cell content remains page-owned:

```tsx
<AdminTooltipText text={value} />
```

## Rollout Plan

### Phase 0: Prerequisites Landed

This rollout started after the shared admin pagination and shared admin tooltip
refactors landed in `main`.

Branch preparation for this implementation:

- update local `main`
- rebase or recreate `refactor/shared-table-component` from the latest `main`

### Phase 1: Build Shared Capabilities

Implemented in this PR:

- `AdminTableShell`
- `useAdminResizableColumns`
- sticky-right style helpers

These shared capabilities are now used by the migrated admin pages below.

### Phase 2: First Migration Targets

Migrated first in this rollout:

- `src/cook-web/src/app/admin/operations/page.tsx`
- `src/cook-web/src/app/admin/orders/page.tsx`

Reasons:

- both are standard list pages
- both use pagination
- both use resizable columns
- both use sticky right-side action columns
- both are the cleanest validation targets for the new shared layer

### Phase 3: Secondary Migration

Migrated next:

- `src/cook-web/src/app/admin/operations/users/page.tsx`

This page is more complex but still follows the same list-page structure.

### Phase 4: Complex Page Migration

Migrated last:

- `src/cook-web/src/app/admin/operations/[shifu_bid]/page.tsx`

Reasons this page was left for the final migration step:

- it contains multiple tables
- it mixes detail-page concerns with table concerns
- it is the highest-risk page for over-abstraction

## Validation Plan

For each migrated page:

- run focused page tests first
- then run broader frontend validation

Required checks after meaningful frontend implementation work:

- `cd src/cook-web && npm run type-check`
- `cd src/cook-web && npm run lint`
- `pre-commit run -a`

For `src/cook-web/**/*.{js,ts,tsx,jsx}` changes, the frontend baseline remains:

- `cd src/cook-web && npm run type-check && npm run lint`

Current note for this branch:

- `npm run type-check` still reports known unrelated failures outside this PR
  under `src/cook-web/src/__tests__/...`,
  `src/cook-web/src/app/c/[[...id]]/...`, and
  `src/cook-web/src/components/shifu-edit/ShifuEdit.test.tsx`

Likely focused tests during rollout:

- `src/app/admin/operations/page.test.tsx`
- `src/app/admin/orders/page.test.tsx`
- `src/app/admin/operations/users/page.test.tsx`
- `src/app/admin/operations/[shifu_bid]/page.test.tsx`

## Risks And Guardrails

### Risk: Over-abstracting Page Logic

Guardrail:

- keep filters, requests, dialogs, and row actions inside each page

### Risk: Regressing Resize UX

Guardrail:

- match the current pointer interaction and persisted-width behavior closely
- migrate only two pages first before expanding scope

### Risk: Sticky Column Visual Regressions

Guardrail:

- centralize only the shared sticky-right styles first
- keep page-specific action content unchanged

### Risk: Waiting On Open PRs

Guardrail:

- do not begin the shared table implementation until PR `#1542` and PR `#1545`
  are both merged into `main`

## Expected Outcome

After this work:

- admin list pages should share one table shell pattern
- resizable column behavior should be maintained through one shared hook
- sticky right-side action column styling should stop being copy-pasted
- pagination and tooltip text remain independent and reusable
- future operations-style list pages should be cheaper to add and maintain
