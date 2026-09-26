# Cook Web Domain: app

This module owns Next.js App Router entry points, route-group layouts, route
handlers, and page-level composition for learner, admin, and legal surfaces.

Entry files in this directory: `layout.tsx`, `page.tsx`, `admin/layout.tsx`,
`c/layout.tsx`.

## Do

- Keep route entry concerns in App Router files and move reusable logic into
  components, hooks, stores, or `lib/` when it spreads.
- Preserve route-parameter handling, redirect behavior, and metadata semantics
  across both the modern and legacy route groups.
- Treat app-route changes as integration changes that may affect auth, request
  bootstrapping, and shared providers.

- Root layouts, error entries and global providers import exact store modules;
  do not load the `@/store` barrel while bootstrapping or handling a crash.

## Avoid

- Do not embed large business helpers directly in `page.tsx` files when they
  belong in shared modules.
- Do not fork learner and admin route logic unless product behavior really
  diverges.
- Do not hardcode route parsing when shared URL or state helpers already exist
  in the frontend codebase.

## Tests

`cd src/web && npm run test -- src/app/`

## Related Skills

- `src/web/skills/deep-link-lessonid-routing/SKILL.md`
- `src/web/skills/chat-layout-width-detection/SKILL.md`
