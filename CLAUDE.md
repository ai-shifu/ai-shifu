# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

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
  - `service/rag/`: Knowledge base and retrieval functionality
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

## Environment Configuration

Environment variables are managed through `.env` files:

- Docker: `docker/.env`
- Local development: individual `.env` files in component directories
- Key configurations: LLM API keys, database connections, Redis settings

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
const res = await api.getUserInfo({});     // /main - direct data
const userInfo = res.data;                // /c - manual extraction

// After (unified):
const userInfo = await api.getUserInfo({}); // Both routes - direct data
const userInfo = await getUserInfo();       // Both routes - direct data
```

#### Important Files

- `src/cook-web/src/lib/request.ts`: Core Request class and error handling
- `src/cook-web/src/lib/api.ts`: API generation system
- `src/cook-web/src/api/api.ts`: API endpoint definitions for /main
- `src/cook-web/src/c-api/*.ts`: API endpoint definitions for /c
- `src/cook-web/src/c-store/useUserStore.ts`: User authentication state

## Code Quality

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
