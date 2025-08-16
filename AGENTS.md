# AGENTS.md

This file provides guidance to all Coding Agents such as Claude Code (claude.ai/code), Codex when working with code in this repository.

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
flask run
# Database migrations
flask db upgrade
# Run tests
pytest
```

### Web Application

```bash
cd src/web
# Development server
npm run start:dev
# Build for production
npm run build
# Run tests
npm test
```

### Cook Web (Content Management)

```bash
cd src/cook-web
# Development server
npm run dev
# Build for production
npm run build
# Lint code
npm run lint
```

### Docker Development

```bash
cd docker
# Start all services
docker compose up -d
# Build from source
./dev_in_docker.sh
```

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

## Testing

### Backend Tests

- Located in `src/api/tests/`
- Use pytest framework
- Include service layer tests, API endpoint tests, and utility tests
- Run with: `pytest`

### Frontend Tests

- Web app uses React Testing Library
- Run with: `npm test`

## Database

- MySQL database with comprehensive migration system
- Key tables include: `ai_course`, `ai_lesson`, `ai_lesson_script`, `user_info`, `user_profile`
- Database schema managed through Alembic migrations in `src/api/migrations/`

### Database Model Design Standards

The project follows strict conventions for database model definitions to ensure consistency and maintainability:

#### File Structure and Location

- **Model Definition Location**: All database models must be placed in `src/api/flaskr/service/[module]/models.py`
- **Module Organization**: Each service module has its own models file for separation of concerns

#### Naming Conventions

- **Table Names**: Use format `[module]_[table_names]` (e.g., `order_orders`)
- **Model Class Names**: Use PascalCase format `[TableName]` (e.g., `Order`)
- **Business Key Names**: Use format `[name]_bid` (e.g., `order_bid`)

#### Required Fields and Structure

**1. Primary Key**

```python
id = Column(BIGINT, primary_key=True, autoincrement=True)
```

**2. Business Identifier**
All tables must include a business identifier and must be indexed:

```python
shifu_bid = Column(String(32),
    nullable=False,
    default="",
    index=True,
    comment="Shifu business identifier")
```

- Type: `String(32)`
- Must be indexed for performance
- Comment format: `[table_name] business identifier`

**3. Soft Delete and Timestamps**
All tables must include these fields at the end:

```python
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
    comment="Creation timestamp"
)
updated_at = Column(
    DateTime,
    nullable=False,
    default=func.now(),
    server_default=func.now(),
    comment="Last update timestamp",
    onupdate=func.now(),
)
```

**4. User Tracking (Cook Tables Only)**
For tables used in Cook interface, add user tracking fields:

```python
created_user_bid = Column(
    String(32),
    nullable=False,
    index=True,
    default="",
    comment="Creator user business identifier",
)
updated_user_bid = Column(
    String(32),
    nullable=False,
    default="",
    comment="Last updater user business identifier",
)
```

#### Status Field Conventions

**Single Status Field**

```python
#olny for example
status = Column(
    SmallInteger,
    nullable=False,
    default=0,
    comment="Status: 5101=default, 5102=disabled, 5103=enabled",
)
```

**Multiple Status Fields**

```python
# only for example
ask_enabled_status = Column(
        SmallInteger,
        nullable=False,
        default=ASK_MODE_DEFAULT,
        comment="Ask agent status: 5101=default, 5102=disabled, 5103=enabled",
    )
```

#### Column Order Standards

Fields must follow this specific order:

1. `id` (primary key)
2. `[table_name]_bid` (business identifier)
3. External business identifiers (foreign keys)
4. Business columns
5. `status` (if applicable)
6. `deleted`
7. `created_at`
8. `created_user_bid` (if applicable)
9. `updated_at`
10. `updated_user_bid` (if applicable)

#### Foreign Key Relationships

**Parent-Child Ordering**: When multiple foreign keys reference the same entity hierarchy, order child before parent:

```python
class ShifuPublishedBlock(db.Model):
    __tablename__ = "shifu_published_blocks"
    id = Column(BIGINT, primary_key=True, autoincrement=True)
    block_bid = Column(
        String(32),
        nullable=False,
        index=True,
        default="",
        comment="Block business identifier",
    )
    outline_item_bid = Column(  # Child entity first
        String(32),
        nullable=False,
        index=True,
        default="",
        comment="Outline item business identifier",
    )
    shifu_bid = Column(  # Parent entity second
        String(32),
        nullable=False,
        index=True,
        default="",
        comment="Shifu business identifier",
    )
```

**Important**: Business foreign keys should be indexed for performance but do NOT create database-level foreign key constraints.

#### Comment Standards

- **Table comments**: should be defined via SQLAlchemy so they are reflected in the DB and migrations:

```python
  class DraftShifu(db.Model):
      __tablename__ = "shifu_draft_shifu"
      __table_args__ = {"comment": "Draft shifu entities"}
```

- **Comment Capitalization**: First letter capitalized (e.g., "Shifu business identifier")
- **Status Comments**: Must include value descriptions using format `Status: [value] = [description]`

### Database Migration Rules

**CRITICAL**: Every database schema change MUST follow this process:

#### Required Steps for Database Changes

1. **Make model changes** in SQLAlchemy model files (`src/api/flaskr/service/*/models.py`)
2. **Generate migration script** using Flask-Migrate:

   ```bash
   cd src/api
   flask db migrate -m "descriptive message about the change"
   ```

3. **Review the generated migration** in `src/api/migrations/versions/`
4. **Commit the migration file** to version control

**Note**: `flask db upgrade` is used for deployment/environment setup, not required during development.

#### Prerequisites for Migration Commands

Before running `flask db migrate`, ensure:

```bash
# 1. Navigate to API directory
cd src/api

# 2. Set environment variables
export FLASK_APP=flaskr
export DATABASE_URL="mysql://user:password@localhost/dbname"

# 3. Generate new migration
flask db migrate -m "describe your changes"
```

#### When to Use Migration Commands

- **Adding new tables or columns**
- **Modifying column types or constraints**
- **Dropping tables or columns**
- **Adding or removing indexes**
- **Any structural database changes**

#### Migration Best Practices

- **Always review** the auto-generated migration before applying
- **Use descriptive messages** that explain the business purpose
- **Test migrations** on a copy of production data
- **Never edit applied migrations** - create new ones instead
- **Include both upgrade() and downgrade()** functions for rollback capability

#### Common Migration Issues & Solutions

**Problem**: `flask: command not found`

```bash
export FLASK_APP=flaskr
# or use: python -m flask db migrate
```

**Problem**: `Could not locate a Flask application`

```bash
export FLASK_APP=flaskr
```

**Problem**: `Target database is not up to date`

```bash
# This usually means database state doesn't match migration history
# Check current migration status: flask db current
# Review migration history: flask db history
```

**Problem**: Database connection errors

```bash
export DATABASE_URL="your_database_connection_string"
```

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

#### Important Configuration Guidelines

1. **Required vs Optional**:
   - `required=True`: Variable MUST be set, no default value allowed
   - `required=False` with default: Optional with fallback value
   - `required=False` without default: Handled by libraries

2. **Secret Values**:
   - Mark sensitive data with `secret=True`
   - Examples: API keys, passwords, tokens
   - These won't show default values in generated examples

3. **Type Conversion**:
   - Supported types: `str`, `int`, `float`, `bool`, `list`
   - List values are comma-separated: `"value1,value2,value3"`

4. **Validation**:
   - Add validators for values with specific requirements
   - Example: Port numbers, email formats, URL patterns

5. **Descriptions**:
   - Be detailed and clear
   - Include examples when helpful
   - Support multi-line for complex configurations

## Cook Web API Request Architecture

### Unified Request System (Updated 2025-07-12)

The Cook Web frontend has been unified to use a single, consistent API request system across all routes (`/main` and `/c`).

#### Architecture Overview

```text
业务代码 → Request 类 → handleBusinessCode() → 返回业务数据
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

#### Authentication

- **Token Source**: `useUserStore.getState().getToken()`
- **Headers Added**: `Authorization: Bearer ${token}`, `Token: ${token}`, `X-Request-ID: ${uuid}`
- **Storage**: Uses localStorage via `tokenTool` for persistent sessions
- **Guest Mode**: Automatic fallback for unauthenticated users

#### Error Handling

- **Network Errors**: Handled in Request class with toast notifications
- **Business Errors**: Handled in `handleBusinessCode` with specific logic per error code
- **Authentication Errors**: Automatic redirect to `/login`
- **Permission Errors**: Toast notification for insufficient permissions
- **SSR Safety**: All browser APIs wrapped in `typeof window !== 'undefined'` checks

#### Route Consistency

Both `/main` and `/c` routes now use identical request infrastructure:

- **Same HTTP Client**: Request class
- **Same Authentication**: useUserStore token management
- **Same Error Handling**: handleBusinessCode logic
- **Same Response Format**: Direct business data (no manual `.data` extraction needed)

#### Migration Notes

Previous architecture had dual systems:

- `/main` used `Request` class with `api.ts` generation
- `/c` used `axiosrequest` with manual response handling

This has been unified so all business code receives clean data directly:

```typescript
// Before (mixed patterns):
const res = await api.getUserInfo({}); // /main - direct data
const userInfo = res.data; // /c - manual extraction

// After (unified):
const userInfo = await api.getUserInfo({}); // Both routes - direct data
const userInfo = await getUserInfo(); // Both routes - direct data
```

#### Important Files

- `src/cook-web/src/lib/request.ts`: Core Request class and error handling
- `src/cook-web/src/lib/api.ts`: API generation system
- `src/cook-web/src/api/api.ts`: API endpoint definitions for /main
- `src/cook-web/src/c-api/*.ts`: API endpoint definitions for /c
- `src/cook-web/src/c-store/useUserStore.ts`: User authentication state

## Code Quality

### Language Requirements

**English-Only Policy for Code**: All code-related content MUST be written in English to ensure consistency, maintainability, and international collaboration.

#### What MUST be in English

- **Code Comments**: All inline comments, block comments, and documentation comments
  - ✅ Correct: `# Calculate user discount based on membership level`
  - ❌ Wrong: `# 根据会员等级计算用户折扣`

- **Variable and Function Names**: All identifiers in the code
  - ✅ Correct: `getUserProfile()`, `isValid`, `maxRetryCount`
  - ❌ Wrong: `获取用户资料()`, `是否有效`, `最大重试次数`

- **Database Elements**: Table names, column names, and database comments
  - ✅ Correct: `user_profile`, `created_at`, comment="User creation timestamp"
  - ❌ Wrong: `用户资料`, `创建时间`, comment="用户创建时间戳"

- **Constants and Enums**: All constant values and enumeration names
  - ✅ Correct: `STATUS_ACTIVE = 1`, `PaymentStatus.PENDING`
  - ❌ Wrong: `状态_激活 = 1`, `支付状态.待处理`

- **Log Messages and Debug Output**: All logging statements and debug information
  - ✅ Correct: `logger.info("User login successful")`
  - ❌ Wrong: `logger.info("用户登录成功")`

- **Error Messages in Code**: Internal error messages and exception messages
  - ✅ Correct: `raise ValueError("Invalid email format")`
  - ❌ Wrong: `raise ValueError("无效的邮箱格式")`

- **Configuration Keys**: All configuration file keys and environment variable names
  - ✅ Correct: `DATABASE_URL`, `max_connections`
  - ❌ Wrong: `数据库地址`, `最大连接数`

- **Git Commit Messages**: All commit messages and PR descriptions
  - ✅ Correct: `fix: resolve database connection timeout issue`
  - ❌ Wrong: `修复：解决数据库连接超时问题`

- **Code Documentation**: README files, API documentation, code architecture docs
  - ✅ Correct: Technical documentation in English
  - ❌ Wrong: Technical documentation in other languages

#### Exceptions (Where Other Languages ARE Allowed)

- **User-Facing Strings**: All text displayed to end users should use i18n
  - These should be translation keys, not hardcoded strings
  - Actual translations in locale files (`zh-CN.json`, `en-US.json`, etc.)

- **Test Data**: Sample user data or content used for testing may be in any language if testing internationalization

- **Business Logic Comments**: When documenting specific regional business requirements, a brief explanation in the local language may be added AFTER the English comment for clarity
  - Example: `# Check if user has valid ID card (检查身份证有效性)`

#### Rationale

- Ensures codebase is accessible to international developers
- Facilitates easier debugging and maintenance
- Improves consistency across the entire project
- Enables better collaboration with global teams
- Makes code review more effective

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

- **Component files**: Use PascalCase (e.g., `UserProfile.tsx`, `NavBar.tsx`, `AuthForm.tsx`)
- **Regular TypeScript/JavaScript files**: Use kebab-case (e.g., `api-utils.ts`, `auth-helper.ts`, `date-formatter.ts`)
- **CSS/SCSS files**: Use kebab-case (e.g., `global-styles.css`, `theme-variables.scss`)
- **CSS Modules**: Match component name but with `.module.css` or `.module.scss` (e.g., `UserProfile.module.scss`)
- **Test files**: Match the file being tested with `.test.ts` or `.spec.ts` suffix
- **Type definition files**: Use kebab-case with `.d.ts` extension (e.g., `api-types.d.ts`)
- **Configuration files**: Use lowercase with dots (e.g., `.eslintrc.json`, `.prettierrc`, `next.config.ts`)

#### Special Cases

- **MDX files**: Can use either PascalCase or kebab-case depending on usage
- **API route files in Next.js**: Always `route.ts` or `route.js`
- **Page files in Next.js**: Always `page.tsx` or `page.js`
- **Layout files in Next.js**: Always `layout.tsx` or `layout.js`
- **Loading files in Next.js**: Always `loading.tsx` or `loading.js`
- **Error files in Next.js**: Always `error.tsx` or `error.js`

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
