# AGENTS.md

This file provides guidance to all Coding Agents such as Claude Code (claude.ai/code), Codex when working with code in this repository.

## Quick Start

### Most Common Tasks

| Task | Command | Location |
|------|---------|----------|
| Start backend dev server | `flask run` | `cd src/api` |
| Start web frontend | `npm run start:dev` | `cd src/web` |
| Start Cook Web (CMS) | `npm run dev` | `cd src/cook-web` |
| Run backend tests | `pytest` | `cd src/api` |
| Generate DB migration | `FLASK_APP=app.py flask db migrate -m "message"` | `cd src/api` |
| Apply DB migration | `FLASK_APP=app.py flask db upgrade` | `cd src/api` |
| Check code quality | `pre-commit run -a` | Root directory |
| Start all services (Docker) | `docker compose up -d` | `cd docker` |

### Essential Environment Variables

```bash
# Backend (src/api/.env)
FLASK_APP=app.py

# Frontend (src/web/.env)
REACT_APP_API_URL=http://localhost:5000

# Cook Web (src/cook-web/.env.local)
NEXT_PUBLIC_API_URL=http://localhost:5000
```

## Critical Warnings ⚠️

### MUST DO Before Any Commit

1. **Run pre-commit hooks**: `pre-commit run` (MANDATORY)
2. **Generate migration for DB changes**: `flask db migrate -m "description"`
3. **Test your changes**: Run relevant test suites
4. **Use English for all code**: Comments, variables, commit messages
5. **Follow Conventional Commits**: `type: description` (lowercase type, imperative mood)

### Common Pitfalls to Avoid

- **Never edit applied migrations** - Always create new ones
- **Don't hardcode user-facing strings** - Use i18n keys
- **Don't create DB foreign key constraints** - Use indexed business keys only
- **Don't skip pre-commit** - It catches formatting and type issues
- **Don't commit secrets** - Use environment variables
- **Don't use Chinese in code** - English only (except i18n files)

## Project Overview

AI-Shifu is an AI-led chat platform that provides interactive, personalized conversations across education, storytelling, product guides, and surveys. Unlike traditional human-led chatbots, AI-Shifu follows an AI-led conversation flow where users can ask questions and interact, but the AI maintains control of the narrative progression.

## Architecture

The project follows a microservices architecture with 3 main components:

- **Backend API (`src/api/`)**: Flask-based Python API with SQLAlchemy ORM
- **Web Application (`src/web/`)**: React-based user-facing web application
- **Cook Web (`src/cook-web/`)**: Next.js-based content management/authoring interface

### Backend API (`src/api/`)

- Built with Flask, SQLAlchemy, and MySQL
- Plugin-based architecture with hot reload support (`flaskr/framework/plugin/`)
- Service layer organization with separate modules for different domains:
  - `service/shifu/`: Core AI conversation logic and outline management
  - `service/study/`: Learning session management and user interactions
  - `service/user/`: User authentication and profile management
  - `service/order/`: Payment and subscription handling
  - `service/profile/`: User profile and preferences
  - `service/lesson/`: Lesson content management
  - `service/llm/`: LLM integration layer
- Database migrations managed with Alembic (`migrations/`)
- Internationalization support with separate locale files (`i18n/`)

### Web Applications

- **Main Web (`src/web/`)**: React with TypeScript, SCSS modules, Zustand for state management
- **Cook Web (`src/cook-web/`)**: Next.js with TypeScript, Tailwind CSS, includes content authoring tools

## Development Commands

### Backend API

```bash
cd src/api

# Development server
FLASK_APP=app.py flask run

# Database operations
FLASK_APP=app.py flask db migrate -m "descriptive message"  # Create migration
FLASK_APP=app.py flask db upgrade                           # Apply migrations
FLASK_APP=app.py flask db downgrade                        # Rollback migration
FLASK_APP=app.py flask db current                          # Show current migration
FLASK_APP=app.py flask db history                          # Show migration history

# Testing
pytest                                    # Run all tests
pytest tests/service/shifu/              # Run specific module tests
pytest -k "test_function_name"           # Run specific test
pytest --cov=flaskr --cov-report=html   # With coverage report
```

### Web Application

```bash
cd src/web

# Install dependencies (first time)
npm install

# Development
npm run start:dev                        # Start dev server
npm run build                            # Production build
npm test                                 # Run tests
npm run lint                             # Check linting
```

### Cook Web (Content Management)

```bash
cd src/cook-web

# Install dependencies (first time)
npm install

# Development
npm run dev                              # Start dev server
npm run build                            # Production build
npm run lint                             # Check linting
npm run type-check                       # TypeScript check
```

### Docker Development

```bash
cd docker

# Start all services
docker compose up -d

# Stop all services
docker compose down

# Build from source
./dev_in_docker.sh

# View logs
docker compose logs -f [service_name]

# Access container
docker compose exec [service_name] bash
```

## Database

### Database Model Design Standards

The project follows strict conventions for database model definitions to ensure consistency and maintainability.

#### Complete Model Example

```python
from sqlalchemy import Column, BIGINT, String, SmallInteger, DateTime, func
from flaskr import db

class Order(db.Model):
    """Order model following all conventions"""
    __tablename__ = "order_orders"
    __table_args__ = {"comment": "Order entities"}

    # 1. Primary key (always first)
    id = Column(BIGINT, primary_key=True, autoincrement=True)

    # 2. Business identifier (always second, indexed)
    order_bid = Column(
        String(32),
        nullable=False,
        default="",
        index=True,
        comment="Order business identifier"
    )

    # 3. Foreign keys (child before parent, indexed)
    user_bid = Column(
        String(32),
        nullable=False,
        default="",
        index=True,
        comment="User business identifier"
    )

    # 4. Business columns
    amount = Column(
        BIGINT,
        nullable=False,
        default=0,
        comment="Order amount in cents"
    )

    # 5. Status field (if applicable)
    status = Column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="Status: 0=pending, 1=paid, 2=cancelled"
    )

    # 6. Soft delete flag
    deleted = Column(
        SmallInteger,
        nullable=False,
        default=0,
        index=True,
        comment="Deletion flag: 0=active, 1=deleted"
    )

    # 7. Timestamps
    created_at = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        server_default=func.now(),
        comment="Creation timestamp"
    )

    # 8. User tracking (Cook tables only)
    created_user_bid = Column(
        String(32),
        nullable=False,
        index=True,
        default="",
        comment="Creator user business identifier"
    )

    updated_at = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        server_default=func.now(),
        onupdate=func.now(),
        comment="Last update timestamp"
    )

    updated_user_bid = Column(
        String(32),
        nullable=False,
        default="",
        comment="Last updater user business identifier"
    )
```

#### Database Change Checklist

- [ ] Model changes made in `src/api/flaskr/service/[module]/models.py`
- [ ] Migration generated: `flask db migrate -m "description"`
- [ ] Migration reviewed in `src/api/migrations/versions/`
- [ ] Migration file committed to version control
- [ ] Tests updated/added for new model
- [ ] Documentation updated if needed

#### Migration Troubleshooting

| Problem | Solution |
|---------|----------|
| `flask: command not found` | `export FLASK_APP=flaskr` or `python -m flask db migrate` |
| `Could not locate a Flask application` | `export FLASK_APP=flaskr` |
| `Target database is not up to date` | Check status: `flask db current`, then `flask db upgrade` |
| Database connection errors | `export DATABASE_URL="mysql://user:pass@host/db"` |
| Migration not detecting changes | Check model is imported in `__init__.py` |

## API Endpoint Standards

### Standard Response Format

```json
{
    "code": 0,           // 0 for success, non-zero for errors
    "message": "Success", // Human-readable message
    "data": {}           // Response payload
}
```

### Common Error Codes

| Code | Meaning | Action |
|------|---------|--------|
| 0 | Success | Process data |
| 1001 | Unauthorized | Redirect to login |
| 1004 | Token expired | Refresh token |
| 1005 | Invalid token | Clear token, redirect to login |
| 9002 | No permission | Show permission error |
| 5001+ | Business errors | Show error message |

### Authentication Headers

```javascript
// Required headers for authenticated requests
{
    "Authorization": "Bearer {token}",
    "Token": "{token}",
    "X-Request-ID": "{uuid}"
}
```

## Testing Guidelines

### Test File Structure

```text
src/api/tests/
├── conftest.py                 # Shared fixtures
├── service/
│   ├── shifu/
│   │   ├── test_models.py     # Model tests
│   │   ├── test_service.py    # Service logic tests
│   │   └── test_api.py        # API endpoint tests
│   └── ...
└── common/
    └── fixtures/
        └── test_data.py        # Test data fixtures
```

### Test Patterns

```python
# Test file naming: test_[module].py
# Test function naming: test_[function]_[scenario]

import pytest
from unittest.mock import patch, MagicMock

class TestShifuService:
    """Group related tests in classes"""

    @pytest.fixture
    def mock_shifu(self):
        """Provide test fixtures"""
        return {"shifu_bid": "test123", "name": "Test Shifu"}

    def test_create_shifu_success(self, mock_shifu):
        """Test successful shifu creation"""
        # Arrange
        expected = mock_shifu

        # Act
        result = create_shifu(mock_shifu)

        # Assert
        assert result["shifu_bid"] == expected["shifu_bid"]

    @patch('flaskr.service.shifu.service.db.session')
    def test_create_shifu_db_error(self, mock_session):
        """Test database error handling"""
        # Arrange
        mock_session.commit.side_effect = Exception("DB Error")

        # Act & Assert
        with pytest.raises(Exception):
            create_shifu({})
```

### Coverage Requirements

- Aim for >80% code coverage
- Critical paths must have 100% coverage
- Run coverage: `pytest --cov=flaskr --cov-report=html`

## Development Workflow

### Branch Naming

- Feature: `feat/description-of-feature`
- Bug fix: `fix/description-of-fix`
- Refactor: `refactor/description`
- Documentation: `docs/description`

### Pull Request Checklist

- [ ] Code follows project conventions
- [ ] Pre-commit hooks pass
- [ ] Tests added/updated and passing
- [ ] Database migrations created if needed
- [ ] Documentation updated if needed
- [ ] PR title follows Conventional Commits
- [ ] No hardcoded strings (use i18n)
- [ ] No secrets in code

### Deployment Process

1. Merge to main branch
2. CI/CD runs tests and builds
3. Deploy to staging environment
4. Run smoke tests
5. Deploy to production

## Performance Guidelines

### Database Optimization

- **Always index foreign keys**: Add `index=True` to all `_bid` columns
- **Use batch operations**: Prefer bulk inserts/updates
- **Limit query results**: Use pagination for large datasets
- **Avoid N+1 queries**: Use joins or eager loading
- **Cache frequently accessed data**: Use Redis for hot data

### API Performance

- **Response time targets**: <200ms for reads, <500ms for writes
- **Pagination**: Default 20 items, max 100 items per page
- **Use async where appropriate**: For I/O bound operations
- **Implement rate limiting**: Protect against abuse
- **Add request timeouts**: Default 30s timeout

### Frontend Performance

- **Code splitting**: Lazy load routes and heavy components
- **Image optimization**: Use appropriate formats and sizes
- **Bundle size**: Keep main bundle <500KB
- **Cache API responses**: Use React Query or SWR
- **Debounce user input**: For search and filters

## Environment Configuration

### Configuration Files

Environment variables are managed through `.env` files:

- Docker: `docker/.env`
- Local development: individual `.env` files in component directories
- Key configurations: LLM API keys, database connections, Redis settings
- Example files: `docker/.env.example.minimal` (required only) and `docker/.env.example.full` (all variables)

### Managing Environment Variables

#### Adding or Modifying Environment Variables

When you need to add or modify environment variables:

1. **Update the configuration definition** in `src/api/flaskr/common/config.py`:

   ```python
   "NEW_VARIABLE": EnvVar(
       name="NEW_VARIABLE",
       required=False,  # True if this variable MUST be set
       default="default_value",  # Default value (None if required=True)
       type=str,  # Type: str, int, float, bool, list
       description="""Detailed description of the variable
       Can be multi-line for complex explanations""",
       secret=False,  # True for sensitive values like API keys
       group="app",  # Group: app, database, redis, auth, llm, etc.
       validator=lambda x: validator_function(x),  # Optional validation
   ),
   ```

2. **Regenerate example files**:

   ```bash
   cd src/api
   python scripts/generate_env_examples.py
   ```

   This will update:
   - `docker/.env.example.minimal` - Only required variables
   - `docker/.env.example.full` - All available variables

3. **Update tests if needed**:
   - Add to test fixtures in `src/api/tests/common/fixtures/config_data.py`
   - Update relevant test cases

## Cook Web API Request Architecture

### Unified Request System (Updated 2025-07-12)

The Cook Web frontend has been unified to use a single, consistent API request system across all routes (`/main` and `/c`).

#### Architecture Overview

```text
Business Code → Request Class → handleBusinessCode() → Return Business Data
```

#### Key Components

**1. Request Class (`src/cook-web/src/lib/request.ts`)**

- Unified HTTP client based on `fetch` API
- Automatic authentication header injection
- Centralized error handling and business logic processing
- Support for streaming requests (SSE)
- SSR-compatible with proper browser environment checks

**2. API Generation System (`src/cook-web/src/lib/api.ts`)**

- Generates type-safe API functions from endpoint definitions
- Supports dynamic URL parameters `{param}` style
- Automatically maps HTTP methods (GET, POST, PUT, DELETE)
- Handles query parameters for GET requests
- Supports streaming methods (STREAM, STREAMLINE)

**3. Business Code Handling (`handleBusinessCode` function)**

- Centrally processes all API responses
- Checks `response.code` for business logic errors
- Handles authentication errors (codes 1001, 1004, 1005) with automatic redirects
- Manages permission errors (code 9002)
- Returns `response.data` directly to business code
- Consistent error handling with toast notifications

#### Request Flow

1. **Business Layer**: Calls API function (e.g., `api.getUserInfo({})` or `getUserInfo()`)
2. **API Layer**: Constructs URL, handles parameters, calls Request class
3. **Request Class**:
   - Adds authentication headers (`useUserStore.getToken()`)
   - Makes fetch request to backend
   - Receives JSON response
4. **Business Code Handler**:
   - Checks `response.code !== 0` for errors
   - Handles authentication/permission errors
   - Returns `response.data` for success
5. **Business Layer**: Receives clean business data directly

## Key Concepts

### Shifu System

The core AI conversation system is built around "Shifu" (master/teacher) concepts:

- **Outlines**: Structured conversation templates with blocks and units
- **Blocks**: Individual conversation segments with different types (AI responses, user inputs, etc.)
- **Study Sessions**: User interaction sessions that follow outline progressions
- **Profiles**: User personality and preference data for personalization

### Plugin Architecture

The backend uses a flexible plugin system (`flaskr/framework/plugin/`) that supports:

- Hot reloading of plugins during development
- Dependency injection for services
- Modular feature development

### Content Management

Cook Web provides tools for:

- Creating and editing conversation outlines
- Managing AI profiles and personalities
- Debugging conversation flows
- Content localization

## Code Quality

### Language Requirements

**English-Only Policy for Code**: All code-related content MUST be written in English to ensure consistency, maintainability, and international collaboration.

#### What MUST be in English

- **Code Comments**: All inline comments, block comments, and documentation comments
- **Variable and Function Names**: All identifiers in the code
- **Database Elements**: Table names, column names, and database comments
- **Constants and Enums**: All constant values and enumeration names
- **Log Messages and Debug Output**: All logging statements and debug information
- **Error Messages in Code**: Internal error messages and exception messages
- **Configuration Keys**: All configuration file keys and environment variable names
- **Git Commit Messages and PR Titles**: MUST use Conventional Commits format
- **Code Documentation**: README files, API documentation, code architecture docs

#### Conventional Commits Format

**Required Format**: `<type>: <description>` (e.g., `fix: resolve database connection timeout issue`)

**Common Types**:

- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation
- `refactor:` - Code refactoring
- `test:` - Tests
- `chore:` - Maintenance
- `build:` - Build system or dependencies
- `ci:` - CI configuration
- `perf:` - Performance improvements
- `style:` - Formatting (no code change)
- `revert:` - Revert a previous commit

**Style Rules**:

- Type must be lowercase
- Use imperative mood ("add", not "added")
- Keep subject line ≤72 characters
- No trailing period
- English only

### Pre-commit Hooks

- **ALWAYS run pre-commit before committing code**: This ensures code quality and consistency
- For modified files only: `pre-commit run`
- For all files: `pre-commit run --all-files`
- If pre-commit is not installed, install it with: `pip install pre-commit && pre-commit install`
- Pre-commit will automatically check:
  - Code formatting
  - Linting issues
  - Type errors
  - Other code quality checks

## UI Development Guidelines

### Internationalization (i18n)

- **ALL user-facing strings MUST use i18n**: Never hardcode any text that will be displayed to users
- Use translation keys instead of hardcoded strings
- Examples:
  - ✅ Correct: `t('errors.no-permission')`
  - ❌ Wrong: `'您当前没有权限访问此内容'`
  - ✅ Correct: `t('common.retry', 'Retry')` (with fallback)
  - ❌ Wrong: `'重试'`
- Translation files are located in:
  - Web app: `src/web/public/locales/`
  - Cook web: `src/cook-web/public/locales/`
- Always add translations for both Chinese (`zh-CN.json`) and English (`en-US.json`)

### File and Directory Naming Conventions

#### Directory Naming

- **Use kebab-case (lowercase with hyphens)** for all directories
- Examples:
  - ✅ Correct: `user-profile/`, `auth-components/`, `api-utils/`
  - ❌ Wrong: `userProfile/`, `AuthComponents/`, `apiUtils/`
- Exception: Next.js App Router special conventions like `(group)`, `[dynamic]`, `[[...catchAll]]`
- Note: The `c-*` prefixed directories (e.g., `c-api/`, `c-components/`) are legacy code kept for compatibility and will be refactored later

#### File Naming

- **Component files**: Use PascalCase (e.g., `UserProfile.tsx`, `NavBar.tsx`)
- **Regular TypeScript/JavaScript files**: Use kebab-case (e.g., `api-utils.ts`, `auth-helper.ts`)
- **CSS/SCSS files**: Use kebab-case (e.g., `global-styles.css`)
- **CSS Modules**: Match component name (e.g., `UserProfile.module.scss`)
- **Test files**: Match the file being tested with `.test.ts` or `.spec.ts` suffix
- **Type definition files**: Use kebab-case with `.d.ts` extension
- **Configuration files**: Use lowercase with dots (e.g., `.eslintrc.json`)

#### Special Cases (Next.js)

- **API route files**: Always `route.ts`
- **Page files**: Always `page.tsx`
- **Layout files**: Always `layout.tsx`
- **Loading files**: Always `loading.tsx`
- **Error files**: Always `error.tsx`

#### Examples of Proper Structure

```text
src/
├── components/
│   ├── ui/                    # kebab-case directory
│   │   ├── Button.tsx         # PascalCase component
│   │   └── Button.module.css  # PascalCase CSS module
│   ├── auth/                  # kebab-case directory
│   │   ├── LoginForm.tsx      # PascalCase component
│   │   └── auth-utils.ts      # kebab-case utility file
│   └── user-profile/          # kebab-case directory
│       └── UserAvatar.tsx     # PascalCase component
├── utils/
│   ├── date-helpers.ts        # kebab-case utility
│   └── api-client.ts          # kebab-case utility
├── hooks/
│   ├── use-auth.ts            # kebab-case hook
│   └── use-user-data.ts       # kebab-case hook
└── types/
    ├── api-types.d.ts         # kebab-case type definition
    └── user-types.d.ts        # kebab-case type definition
```

## Troubleshooting

### Common Issues and Solutions

| Issue | Solution |
|-------|----------|
| Flask app won't start | Check `FLASK_APP=app.py` is set |
| Database connection fails | Verify MySQL is running and credentials in DATABASE_URL |
| Migration not detecting changes | Ensure model is imported in module's `__init__.py` |
| Frontend can't connect to API | Check CORS settings and API_URL configuration |
| Pre-commit fails | Run `pre-commit install` to set up hooks |
| Tests fail with import errors | Check PYTHONPATH includes project root |
| Docker build fails | Ensure all .env files are present |
| TypeScript errors in Cook Web | Run `npm run type-check` to see detailed errors |
| Redis connection optional | Redis is optional, app works without it |

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
lsof -i :5000  # Backend
lsof -i :3000  # Frontend
```

## Additional Resources

- Flask Documentation: <https://flask.palletsprojects.com/>
- SQLAlchemy Documentation: <https://www.sqlalchemy.org/>
- React Documentation: <https://reactjs.org/>
- Next.js Documentation: <https://nextjs.org/>
- Conventional Commits: <https://www.conventionalcommits.org/>
