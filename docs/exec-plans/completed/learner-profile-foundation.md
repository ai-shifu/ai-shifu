# Learner Profile Foundation

## Purpose / Big Picture

The learner-profile foundation provides one canonical, cross-course learner
context while preserving the existing legacy profile and course-variable
contracts. It supplies Teaching, Ask, and formal preview with the same
teacher-owned Course Prompt plus JSON-encoded learner data.

## Progress

- [x] 2026-08-15 CST: Canonical profile persistence, compatibility behavior,
      prompt composition, migration graph, and focused regression coverage are
      complete.

## Surprises & Discoveries

The legacy questionnaire and `sys_*` variables remain active compatibility
interfaces. Canonical profile data supplements them; it does not replace or
rewrite their existing storage or runtime behavior.

## Decision Log

- Canonical learner context is stored independently from legacy variables.
- Course Prompt text remains teacher-authored and unchanged.
- Learner context is encoded as untrusted data, never as instruction authority.
- Empty learner context leaves the Course Prompt byte-for-byte unchanged.
- Teaching, Ask, and formal preview share the same composed prompt.

## Outcomes & Retrospective

The system now has a durable learner-profile contract without changing old
course data or the legacy onboarding wire protocol. Current learner facts can
personalize relevant examples, terminology, emphasis, forms of address, and
language style, while course design remains owned by the human teacher.

## Context and Orientation

- Persistence and profile-state behavior:
  `src/api/flaskr/service/profile/learner_profile.py`
- Authenticated learner-profile API:
  `src/api/flaskr/route/user.py`
- Legacy variable storage and runtime projection:
  `src/api/flaskr/service/profile/funcs.py`
- Prompt composition:
  `src/api/flaskr/service/profile/learner_profile_prompt.py`
- Teaching and formal preview consumers:
  `src/api/flaskr/service/learn/context_v2.py`
- Ask consumer:
  `src/api/flaskr/service/learn/handle_input_ask.py`

## Plan of Work

No further foundation extraction is planned. Future changes must preserve the
canonical/legacy separation and the shared prompt-composition contract.

## Concrete Steps

For a future change, update the canonical profile service, API DTOs, prompt
composer, and all three runtime consumers together; add focused tests for the
affected contract before changing legacy compatibility paths.

## Validation and Acceptance

- `user_users.learner_profile` and
  `user_users.learner_profile_updated_at` are managed atomically with the
  fixed profile onboarding handled state.
- Canonical GET, PUT, and DELETE remain authenticated and compatible with
  legacy onboarding behavior.
- Legacy `sys_*` writes, reads, parser behavior, and old-course runtime
  substitution remain unchanged.
- A composed prompt contains the original Course Prompt and JSON-encoded
  learner data only when learner context exists.
- Learner directives cannot override platform, runtime, or teacher-owned
  course instructions.
- Teaching, Ask, and formal preview receive the same canonical learner context.
- The Alembic graph has one head: merge revision `f9a2b3c4d5e6` joins learner
  profile revision `c8f1a2d3e4b5` and TTS revision `e7b3c9d1f5a2`.

## Idempotence and Recovery

All changes are ordinary source, migration, and test changes. Re-running
focused tests and migration-head validation is safe. Do not rewrite applied
migrations; future sibling migration heads require a separate no-DDL merge
revision.

## Interfaces and Dependencies

- Database: canonical fields on `user_users` and the existing
  `user_onboarding_states` profile onboarding row.
- API: `GET|PUT|DELETE /api/user/learner-profile`; legacy
  `GET|POST /api/user/profile-onboarding[/complete]` remains stable.
- Prompt API: `build_course_prompt(course_prompt, learner=...)` produces the
  shared effective prompt.
- Dependencies: MarkdownFlow continues to consume one `document_prompt`
  string; no provider-specific learner-profile parameter is required.
