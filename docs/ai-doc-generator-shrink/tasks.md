# Tasks

Design: [AI Doc Generator Shrink And Baseline Restoration](./design.md)

- [x] Add the hand-maintained engineering baseline and keep `docs/README.md`
      aligned with the docs workflow.
- [x] Convert root, backend, and frontend `AGENTS.md` files to concise
      hand-maintained docs that link to the engineering baseline.
- [x] Shrink the generator to repetitive surfaces only and stop generating
      the core `AGENTS.md` and `.claude/rules` files.
- [x] Update validation to distinguish generated docs from hand-maintained
      docs and verify the new baseline links.
- [x] Regenerate generated files and run AI-doc validation plus focused
      pre-commit checks.
