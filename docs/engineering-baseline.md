# Engineering Baseline

This document is the canonical engineering baseline for the repository.
Repository-wide architecture notes, API norms, database conventions, testing
expectations, workflow rules, naming rules, and troubleshooting guidance live
here. The layered `AGENTS.md` files remain the hard-rule entry points, and
this handbook carries the expanded rationale, examples, and troubleshooting
details behind those rules.

## Quick Start

### Most Common Tasks

| Task | Command | Location |
|------|---------|----------|
| Start backend dev server | `flask run` | `cd src/api` |
| Start Cook Web (frontend & CMS) | `npm run dev` | `cd src/cook-web` |
| Run backend tests | `pytest` | `cd src/api` |
| Generate DB migration | `FLASK_APP=app.py flask db migrate -m "message"` | `cd src/api` |
| Apply DB migration | `FLASK_APP=app.py flask db upgrade` | `cd src/api` |
| Check code quality | `lefthook run pre-commit --all-files` | Root directory |
| Start all services (Docker) | `docker compose -f docker-compose.latest.yml up -d` | `cd docker` |
| Start Docker dev stack (build local latest) | `./dev_in_docker.sh` | `cd docker` |
| Build Cook Web dev image | `docker build ../src/cook-web -t ai-shifu-cook-web-dev -f ../src/cook-web/Dockerfile_DEV` | `cd docker` |

### Essential Environment Variables

```bash
# Backend (src/api/.env)
FLASK_APP=app.py

# Cook Web (src/cook-web/.env.local)
NEXT_PUBLIC_API_URL=http://localhost:5000
```

### Local Tooling Setup

Code-quality checks run through **lefthook** (a single Go binary that calls the
tools already installed on your machine). The git hooks only fire after
`lefthook install` has wired them into `.git/hooks`, and each hook shells out to
tools that must already be on `PATH`. One-time setup:

Install lefthook for your platform.

macOS (Homebrew):

```bash
brew install lefthook
```

Linux or Windows (npm):

```bash
npm install -g @evilmartians/lefthook
```

Then install the remaining development tools:

```bash
pip install ruff==0.16.3 commitizen==4.16.2 pre-commit-hooks==6.0.0
(cd src/cook-web && npm ci)   # provides prettier + eslint
lefthook install
```

> **Important:** if you skip `lefthook install` (or never install lefthook), the
> pre-commit checks are **silently skipped** on commit — nothing warns you, and
> the gap only surfaces later in CI. Run `lefthook install` once per clone.

Verify your environment any time (and before committing) with the doctor, which
reports exactly what is missing and how to install it:

```bash
python scripts/check_dev_tools.py            # core gaps fail; frontend gaps warn
python scripts/check_dev_tools.py --strict   # also fail on Cook Web tooling gaps
```

## Critical Requirements

### Must Do Before Any Commit

1. Confirm the toolchain is installed: `python scripts/check_dev_tools.py`
2. Run the lefthook checks: `lefthook run pre-commit`
3. Generate a migration for DB changes: `flask db migrate -m "description"`
4. Test the relevant change surface
5. Use English for code-facing text
6. For human-authored and coding-agent-authored commits, follow the git commit
   message requirements in
   [`AGENTS.md`](../AGENTS.md#git-commit-message-requirements)

### Common Pitfalls To Avoid

- Never edit applied migrations. Always create a new one.
- Do not hardcode user-facing strings. Use i18n keys.
- Do not create DB foreign key constraints for business-key relationships.
- Do not skip the lefthook checks.
- Do not commit secrets.
- Do not use Chinese in code or code-facing docs.

## Repository Overview

AI-Shifu is an AI-led chat platform that provides interactive, personalized
conversations across education, storytelling, product guides, and surveys.
Unlike traditional human-led chatbots, AI-Shifu follows an AI-led
conversation flow where users can ask questions and interact, but the AI
maintains control of the narrative progression.

## Architecture

The project follows a microservices architecture with two main components:

- Backend API (`src/api/`): Flask-based Python API with SQLAlchemy ORM
- Cook Web (`src/cook-web/`): Next.js-based unified frontend and content
  management interface

### Backend Architecture Notes

- Built with Flask, SQLAlchemy, and MySQL
- Plugin-based architecture with hot reload support under
  `flaskr/framework/plugin/`
- Service-layer organization with dedicated domains such as `shifu`, `learn`,
  `user`, `order`, `profile`, `lesson`, and `llm`
- Database migrations managed with Alembic under `migrations/`
- Shared localization data managed under `src/i18n/`

#### LLM Integration

- All server-side LLM calls are routed through LiteLLM inside
  `src/api/flaskr/api/llm/__init__.py`
- Provider credentials continue to live in `.env` via the existing API-key
  variables
- Prefer OpenAI-compatible providers so the shared LiteLLM wrapper can own the
  integration

### Frontend Architecture Notes

- Cook Web uses Next.js, TypeScript, and Tailwind CSS
- The frontend provides both learner-facing routes and authoring/admin tools
- Shared request handling lives in `src/cook-web/src/lib/request.ts` and
  `src/cook-web/src/lib/api.ts`
- Legacy `c-*` directories are still active compatibility surfaces

#### Unified Request System

The Cook Web frontend uses a single request system across routes such as
`/main` and `/c`.

Request flow:

1. Business layer calls an API function
2. API layer builds the request and delegates to the request client
3. Request client injects auth headers and performs the HTTP request
4. Business-code handling checks `response.code`
5. Business layer receives `response.data`

Keep request transport, business-code handling, and auth error processing in
that shared stack instead of recreating them in feature code.

## Database Model Conventions

Use consistent SQLAlchemy model ordering and field semantics.

### Complete Model Example

```python
from sqlalchemy import Column, BIGINT, String, SmallInteger, DateTime, func
from flaskr import db


class Order(db.Model):
    __tablename__ = "order_orders"
    __table_args__ = {"comment": "Order entities"}

    id = Column(BIGINT, primary_key=True, autoincrement=True)

    order_bid = Column(
        String(32),
        nullable=False,
        default="",
        index=True,
        comment="Order business identifier",
    )

    user_bid = Column(
        String(32),
        nullable=False,
        default="",
        index=True,
        comment="User business identifier",
    )

    amount = Column(
        BIGINT,
        nullable=False,
        default=0,
        comment="Order amount in cents",
    )

    status = Column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="Status: 0=pending, 1=paid, 2=cancelled",
    )

    deleted = Column(
        SmallInteger,
        nullable=False,
        default=0,
        index=True,
        comment="Deletion flag: 0=active, 1=deleted",
    )

    created_at = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        server_default=func.now(),
        comment="Creation timestamp",
    )

    created_user_bid = Column(
        String(32),
        nullable=False,
        index=True,
        default="",
        comment="Creator user business identifier",
    )

    updated_at = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        server_default=func.now(),
        onupdate=func.now(),
        comment="Last update timestamp",
    )

    updated_user_bid = Column(
        String(32),
        nullable=False,
        index=True,
        default="",
        comment="Last updater user business identifier",
    )
```

### Database Change Checklist

- [ ] Model changes made in `src/api/flaskr/service/[module]/models.py`
- [ ] Migration generated with `FLASK_APP=app.py flask db migrate -m "description"`
- [ ] Migration reviewed in `src/api/migrations/versions/`
- [ ] Migration file committed to version control
- [ ] Tests updated or added for the new model behavior
- [ ] Documentation updated when needed

### Migration Troubleshooting

| Problem | Solution |
|---------|----------|
| `flask: command not found` | `export FLASK_APP=app.py` or `python -m flask db migrate` |
| `Could not locate a Flask application` | `export FLASK_APP=app.py` |
| `Target database is not up to date` | Run `flask db current`, then `flask db upgrade` |
| Database connection errors | Verify `DATABASE_URL` or local DB credentials |
| Migration not detecting changes | Ensure the model is imported in the module init path |

Fresh MySQL replay smoke test:

```bash
cd src/api
RUN_MYSQL_MIGRATION_SMOKE=1 \
TEST_SQLALCHEMY_DATABASE_URI='mysql+pymysql://root:pass@127.0.0.1:33067/mysql?charset=utf8mb4' \
pytest -q tests/migrations/test_fresh_mysql_upgrade.py
```

## API Contract Baseline

### Standard Response Format

```json
{
  "code": 0,
  "message": "Success",
  "data": {}
}
```

### Common Error Code Expectations

| Code | Meaning | Typical Action |
|------|---------|----------------|
| 0 | Success | Process `data` |
| 1001 | Unauthorized | Redirect to login |
| 1004 | Token expired | Refresh token or force re-auth |
| 1005 | Invalid token | Clear token and redirect |
| 9002 | No permission | Show permission error |
| 5001+ | Business errors | Show the returned message |

### Authentication Headers

```javascript
{
  "Authorization": "Bearer {token}",
  "Token": "{token}",
  "X-Request-ID": "{uuid}"
}
```

## Testing Expectations

### Test File Structure

```text
src/api/tests/
├── conftest.py
├── service/
│   ├── shifu/
│   │   ├── test_models.py
│   │   ├── test_service.py
│   │   └── test_api.py
│   └── ...
└── common/
    └── fixtures/
        └── test_data.py
```

### Test Patterns

- Test file naming: `test_[module].py`
- Test function naming: `test_[function]_[scenario]`
- Group related tests in classes when it improves readability
- Cover both happy paths and the highest-risk failure path

### Coverage Requirements

- Aim for greater than 80 percent code coverage
- Critical paths should target 100 percent coverage
- Coverage command: `pytest --cov=flaskr --cov-report=html`

### Ruff Findings And Rule Adoption

Treat Ruff findings as code or contract signals, not as requests to make the
configuration quieter. For a finding in new or changed code:

1. Read `ruff rule <CODE>`, the nearest `AGENTS.md`, the implementation, its
   call sites, and the closest tests.
2. Prefer the existing project abstraction or a direct code fix. Add focused
   regression coverage whenever the rewrite can change behavior, error paths,
   serialization, persistence, timing, or a public/internal contract.
3. If a framework or protocol requires the flagged construct, use an inline
   `# noqa: CODE` for that construct and explain the reason in nearby English
   prose. Do not use a blanket `# noqa`.
4. Use `per-file-ignores` only when the purpose of a file or file class
   intrinsically conflicts with the rule, such as a lint fixture or immutable
   migration history. A single ordinary call site belongs inline, not in
   `ruff.toml`.
5. Use a global ignore only when a documented repository-wide contract
   fundamentally conflicts with the rule. Do not weaken `select` or `ignore`
   to make an unrelated PR pass.

For `G004`, keep log message construction lazy: pass a constant message and
its values as positional logging arguments, preserving the message text,
argument order, and log level. Use `%s` for normal or `!s` interpolation,
`%r`/`%a` for the matching conversion, and escape a literal percent as `%%`.
When an f-string field has a format specification that logging interpolation
cannot express exactly, pre-format only that field with `format(value, "spec")`
and keep the rest of the message parameterized. Do not hide an f-string in a
temporary variable merely to silence the rule.

For `D205`, put the complete summary on the first physical docstring line,
then use exactly one blank line before details, sections, or embedded protocol
content. Do not wrap the summary across source lines; line length is formatter
owned. In Flasgger route docstrings, keep the `---` YAML separator after that
blank line and run the Swagger-docstring parser regression test rather than
suppressing the rule or reindenting the specification.

For `D107`, describe what constructing the instance establishes: its payload,
owned state, bound dependency, or non-obvious setup. Keep the constructor
docstring to one line when that is the whole contract, and add details only for
real side effects or invariants. Do not copy the signature or write a generic
"Initialize the object" sentence merely to satisfy the rule. Test doubles
should name the state or collaborator they stand in for.

For `D105`, document the observable protocol contract instead of restating the
magic method name. A `__json__` docstring says whether it returns a scalar,
JSON-compatible data, or a JSON string; mapping methods identify the keys or
payload they proxy; representation and comparison methods describe their
visible result. Keep a one-line contract when sufficient, and make test-double
operators name the fake expression they build. Do not write filler such as
"Implement `__json__`".

For `N806`, distinguish a class declaration or module-level class import from
a value bound inside a function. Keep real class names in CapWords, but bind a
locally loaded model or constructor to a descriptive snake_case name such as
`draft_shifu_model` or `session_factory`, then use that name consistently in
the function. Preserve a deliberate lazy import instead of moving it to module
scope merely for lint, and do not add a per-file exception for ordinary local
bindings. Run the tests that exercise the local loader or factory so the rename
cannot silently point queries or object creation at a different class.

For `D100`, describe why the module exists at its ownership boundary. A
production module names the service responsibility, protocol, or data contract
it owns; a test module names the behavior group it protects; an executable
script states the operation it performs. Do not mechanically restate the file
name or write generic filler such as "module helpers". Remove an unreferenced
empty placeholder instead of inventing a purpose for it. Keep the docstring as
the first Python statement while preserving shebangs, encoding comments, and
file-level tool directives. Because adding it changes `module.__doc__`, search
runtime introspection before a bulk adoption and verify executable AST equality
after removing the new module docstrings.

For `FIX002`, do not make an unresolved task invisible by renaming `TODO`,
adding `noqa`, or turning the same promise into an untracked prose comment.
Complete the work when it is part of the current change. When it genuinely
belongs later, record the actionable task in the owning ExecPlan or issue and
leave only a present-tense invariant or compatibility reason beside the code.
Security gaps and rollout checkpoints require behavior-specific evidence:
implement the missing guard, or prove the compatibility exit condition and
delete the expired branch. A lint-only wording change is not resolution.

`TD003` does not authorize an issue-linked `TODO`: `FIX002` still rejects the
marker. The repository default is to put future work in the owning ExecPlan or
issue and keep code comments limited to present behavior and invariants. If a
future narrow FIX002 exception ever makes a TODO intrinsic to one surface, it
must also carry the real durable issue link that owns the work; never fabricate
a ticket or link merely to satisfy lint.

For `TC002` and `TC003`, move a third-party or standard-library import into an
`if TYPE_CHECKING:` block only after confirming every use is an annotation that
Python does not need to resolve at runtime. Postponed annotations are the
normal proof; a quoted annotation or a local variable annotation that is never
evaluated is also safe. An import's source does not prove that it is safe to
defer: keep imports that provide registration side effects or that a framework,
decorator, function signature without postponed evaluation, or explicit
runtime reflection resolves while importing the module. When one import
statement mixes runtime values with annotation-only types, split the statement
and move only the type-only names.

Pydantic `BaseModel` fields are declared as runtime-evaluated in `ruff.toml`,
so both their standard-library and third-party field types stay imported
normally; do not replace that contract with scattered `noqa` comments. When
another shared runtime-evaluated base class or decorator is introduced, model
it centrally in Ruff and add an import or schema smoke test. Use a narrow
explained suppression only for a one-off runtime consumer that Ruff cannot
model. Search tests for `monkeypatch`, `getattr`, and module-attribute
assertions before moving an import: preserve a real injection seam, but remove
an obsolete patch that never influences the code under test instead of keeping
a fake runtime dependency.

Adopt or remove exceptions one rule unit at a time. A rule unit is normally
one Ruff code; combine codes only when they report the same construct and have
the same fix and exception boundary. Base each rule PR on the preceding rule
branch, and keep unrelated cleanup out of the diff. Track the stack and rule
census in `docs/exec-plans/active/ruff-rule-minimization.md`.

For each rule unit, run the focused check first and then the repository gates:

```bash
ruff check . --select CODE
ruff check .
ruff format --check .
python scripts/check_repo_harness.py
```

Run the nearest behavior tests for every touched runtime surface. Lint passing
does not replace test coverage. Before committing, also run
`python scripts/check_dev_tools.py` and `lefthook run pre-commit --all-files`.

## Development Workflow

### Branch Naming

- Feature: `feat/description-of-feature`
- Bug fix: `fix/description-of-fix`
- Refactor: `refactor/description`
- Documentation: `docs/description`

### Pull Request Checklist

- [ ] Code follows project conventions
- [ ] Pre-commit hooks pass
- [ ] Tests added or updated and passing
- [ ] Database migrations created if needed
- [ ] Documentation updated if needed
- [ ] PR title follows Conventional Commits
- [ ] No hardcoded strings in user-facing surfaces
- [ ] No secrets in code

### Deployment Process

1. Merge to `main`
2. CI/CD runs tests and builds
3. Deploy to staging
4. Run smoke tests
5. Deploy to production

## CI/CD And Release Workflow

### Workflow Inventory

- `backend-tests.yml`: runs backend tests for `src/api/**` changes and on
  direct pushes to `main`.
- `prettier-check.yml`: checks Cook Web formatting for frontend changes.
- `repo-harness.yml`: the `Static Checks` job validates architecture
  boundaries, generated AI and knowledge artifacts, translation parity and
  locale metadata, and the MarkdownFlow release pins on PRs into `main`.
- `runtime-harness.yml`: runs the Docker-backed Playwright smoke harness for
  runtime-affecting backend, frontend, Docker, and script changes.
- `prepare-release.yml`: manually prepares a release draft from a requested
  `vX.Y.Z` version and updates versioned project files.
- `build-latest.yml`: builds the freshest published Docker images from `main`
  and can also be triggered manually.
- `build-on-release.yml`: builds and pushes release-tagged Docker images when
  a GitHub release is published.

### Release Path

1. Start with `prepare-release.yml` and provide a version that starts with
   `v`, such as `v1.5.0`.
2. Verify the generated version updates, release draft content, and tag
   expectations before publishing the GitHub release.
3. The release draft includes repository commits since the previous `vX.Y.Z`
   tag, plus MarkdownFlow dependency updates when the pinned `markdown-flow` or
   `markdown-flow-ui` versions change; dependency notes are generated from the
   corresponding library repository tag range when tags exist. When matching
   tags do not exist, registry publish times are used to limit a GitHub commit
   lookup for the dependency repository.
4. Publishing the release triggers `build-on-release.yml`, which validates the
   tag, skips drafts or prereleases, and builds the release-tagged images.
5. `main` continues to drive `build-latest.yml`, so `:latest` images and
   release-tagged images must remain semantically aligned.
6. After image publication, smoke-check the pinned or latest Docker Compose
   startup path, backend boot, and the primary frontend entry path before
   treating the release as ready.

### Release And Automation Rules

- Keep GitHub Actions secrets and vars responsible for registry credentials,
  push toggles, and release-specific configuration.
- Preserve workflow path filters and trigger intent unless the automation
  surface itself is changing deliberately.
- When changing image names, tags, or release semantics, review the GitHub
  workflows and `docker-compose*.yml` files together in the same task.

## Performance Guidelines

### Database Optimization

- Always index `_bid` and other business-key relationship columns
- Prefer batch operations for large writes
- Use pagination for large result sets
- Avoid N+1 queries
- Cache frequently accessed hot data when appropriate

### API Performance

- Target under 200ms for common reads and under 500ms for common writes
- Default pagination: 20 items, max 100
- Use async patterns when they are truly appropriate for I/O work
- Apply rate limiting where endpoints are abuse-prone
- Use request timeouts for external dependencies

### Frontend Performance

- Lazy-load heavy routes and components
- Use appropriate image formats and sizes
- Keep shared bundles under control
- Cache API responses through the shared data layer
- Debounce user input for search and similar flows

## Environment Configuration

### Configuration Files

- Docker: `docker/.env`
- Local development: component-level `.env` files
- Example Docker file: `docker/.env.example.full`
- Important groups: LLM API keys, database, Redis, auth, storage, app config

### Managing Environment Variables

When adding or modifying environment variables:

1. Update the config definition in `src/api/flaskr/common/config.py`
2. Regenerate examples with `cd src/api && python scripts/generate_env_examples.py`
3. Update fixtures and tests when needed

## Internationalization Rules

- All user-facing strings must use i18n
- Shared translations live under `src/i18n/<locale>`
- Do not add primary translations under `public/locales`
- Backend should reference translation keys via shared helpers
- Frontend user-facing locales must stay aligned with `src/i18n/locales.json`

When adding a new namespace:

- Update every supported locale
- Run `python scripts/generate_languages.py`
- Run `python scripts/check_translations.py`
- Run `python scripts/check_translation_usage.py --fail-on-unused`

## File And Directory Naming Conventions

### Directory Naming

- Use kebab-case for directories
- Preserve Next.js special folder conventions such as `(group)`, `[dynamic]`,
  and `[[...catchAll]]`
- Treat `c-*` directories as legacy-but-active compatibility surfaces

### File Naming

- Component files: PascalCase, for example `UserProfile.tsx`
- Regular TypeScript or JavaScript files: kebab-case
- CSS and SCSS files: kebab-case
- CSS modules: match the component name
- Test files: match the file under test and use `.test.ts` or `.spec.ts`
- Type definition files: kebab-case with `.d.ts`
- Configuration files: lowercase with dots

### Special Cases (Next.js)

- API routes: `route.ts`
- Pages: `page.tsx`
- Layouts: `layout.tsx`
- Loading states: `loading.tsx`
- Error boundaries: `error.tsx`

## Troubleshooting

### Common Issues And Solutions

| Issue | Solution |
|-------|----------|
| Flask app will not start | Check `FLASK_APP=app.py` |
| Database connection fails | Verify MySQL and credentials |
| Migration not detecting changes | Ensure the model is imported |
| Frontend cannot connect to API | Check CORS and API URL config |
| Lefthook checks fail | Run `lefthook install` |
| Hooks never run, or a tool reports "command not found" | Run `python scripts/check_dev_tools.py` and install what it lists |
| Tests fail with import errors | Check `PYTHONPATH` and local env |
| Docker build fails | Ensure required `.env` files exist |
| TypeScript errors in Cook Web | Run `npm run type-check` |
| Redis connection optional | App can still run without Redis in many flows |

### Debug Commands

```bash
# Check Python environment
which python
pip list

# Check Node environment
node --version
npm --version

# Check database connection
mysql -u root -p -e "SHOW DATABASES;"

# Check Flask configuration
flask routes

# Check Docker status
docker ps
docker compose logs [service]

# Check port usage
lsof -i :5000
lsof -i :3000
```

## Additional Resources

- Flask Documentation: <https://flask.palletsprojects.com/>
- SQLAlchemy Documentation: <https://www.sqlalchemy.org/>
- React Documentation: <https://react.dev/>
- Next.js Documentation: <https://nextjs.org/>
- Conventional Commits: <https://www.conventionalcommits.org/>
