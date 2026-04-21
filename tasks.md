# Operator User Points

- [x] Confirm the points scope and branch naming for operator user management
- [x] Add phase-1 operator user list credit fields and provisional UI
- [x] Align the product direction to the final flow: list summary + detail credits section
- [x] Extend backend operator user summaries with `credits_expire_at`
- [x] Add backend operator user credits detail API and focused pytest coverage
- [x] Replace the user list credit columns with `available_credits` and `credits_expire_at`
- [x] Add user detail credits overview, credits detail tab, and `#credits` jump behavior
- [x] Update shared frontend types / i18n copy / page tests for the new credits UX
- [x] Remove the low-value `source_bid` column from the operator credits detail table
- [x] Add operator-facing credit type/source/note display mapping for ledger rows
- [x] Run focused backend and frontend verification for the touched operator user flows

## Verification Notes

- `cd src/api && pytest tests/service/shifu/test_admin_users.py -q` ✅
- `cd src/cook-web && npm run test -- src/app/admin/operations/users/page.test.tsx --runTestsByPath 'src/app/admin/operations/users/[user_bid]/page.test.tsx'` ✅
- `cd src/cook-web && npx eslint 'src/app/admin/operations/users/[user_bid]/page.tsx' 'src/app/admin/operations/users/[user_bid]/page.test.tsx' src/app/admin/operations/operation-user-types.ts` ✅
- `cd src/cook-web && npm run lint` ⚠️ still blocked by repository-wide existing warnings outside this task
- `cd src/cook-web && npm run type-check` ⚠️ blocked by pre-existing `markdown-flow-ui/slide` errors under `src/app/c/[[...id]]/`
- `python scripts/check_translations.py && python scripts/check_translation_usage.py --fail-on-unused` ✅
