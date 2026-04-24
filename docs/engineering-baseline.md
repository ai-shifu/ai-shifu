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
| Check code quality | `pre-commit run -a` | Root directory |
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

## Critical Requirements

### Must Do Before Any Commit

1. Run pre-commit hooks: `pre-commit run`
2. Generate a migration for DB changes: `flask db migrate -m "description"`
3. Test the relevant change surface
4. Use English for code-facing text
5. Follow Conventional Commits: `type: description`

### Common Pitfalls To Avoid

- Never edit applied migrations. Always create a new one.
- Do not hardcode user-facing strings. Use i18n keys.
- Do not create DB foreign key constraints for business-key relationships.
- Do not skip pre-commit.
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
  `user`, `order`, `profile`, `lesson`, `llm`, and `gen_mdf`
- Database migrations managed with Alembic under `migrations/`
- Shared localization data managed under `src/i18n/`

#### LLM Integration

- All server-side LLM calls are routed through LiteLLM inside
  `src/api/flaskr/api/llm/__init__.py`
- Provider credentials continue to live in `.env` via the existing API-key
  variables
- Prefer OpenAI-compatible providers so the shared LiteLLM wrapper can own the
  integration

#### MDF Conversion Service

- Backend endpoint: `POST /api/gen_mdf/convert`
- Configuration: set `GEN_MDF_API_URL` in backend `.env`
- Frontend must call the backend proxy via `api.genMdfConvert()`
- Keep the upstream MDF URL hidden from the browser
- Preserve validation for text length, language, and timeout boundaries

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
- `contract-tests.yml`: runs contract tests for backend-facing changes.
- `prettier-check.yml`: checks Cook Web formatting for frontend changes.
- `translations-check.yml`: validates translation parity, key usage, and
  locale metadata on PRs, selected branches, and a schedule.
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
3. Publishing the release triggers `build-on-release.yml`, which validates the
   tag, skips drafts or prereleases, and builds the release-tagged images.
4. `main` continues to drive `build-latest.yml`, so `:latest` images and
   release-tagged images must remain semantically aligned.
5. After image publication, smoke-check the pinned or latest Docker compose
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
- Frontend language surface currently stays limited to `en-US` and `zh-CN`

When adding a new namespace:

- Update both languages
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
| Pre-commit fails | Run `pre-commit install` |
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
