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
