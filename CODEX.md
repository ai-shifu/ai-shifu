# CODEX.md

This file provides guidance to codex when working with code in this repository.

## Key Practices

- Always run `pre-commit run --files <file>` on changed files before committing.
- Keep commits focused and small.
- Prefer descriptive commit messages written in English.
- Update or create tests and documentation when making code changes.
- Follow the existing project architecture and naming conventions.

## Development Commands

### Backend API

```bash
cd src/api
flask run
flask db upgrade
pytest
```

### Web Application

```bash
cd src/web
npm run start:dev
npm run build
npm test
```

### Cook Web

```bash
cd src/cook-web
npm run dev
npm run build
npm run lint
```

### Docker Development

```bash
cd docker
docker compose up -d
./dev_in_docker.sh
```
