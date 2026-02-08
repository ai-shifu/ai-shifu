<div align="center">
  <img src="assets/logo_en.png" width=256></img>
<p><strong>Write Once, Teach Personally</strong></p>

English | [简体中文](README_ZH-CN.md)

</div>
AI-Shifu is designed for creators, instructors, and training/education teams, offering a scalable one-on-one teaching agent. Provide your expertise and teaching intent once, AI-Shifu will expand it into complete, personalized learning experiences. It adapts in real time to each learner’s profile with tailored explanations, interactive probing, assessments, and a full feedback loop—amplifying both your efficiency and the learner’s experience.

# Core Capabilities

- **Personalized explanation engine** — Generates learning paths and tone based on learner background, goals, and level.
- **Interactive Q&A & probing** — Decomposes questions, asks clarifiers, and suggests next actions during sessions.
- **Rapid course assembly** — Author with high-level frameworks and intent; AI-Shifu elaborates into lessons, activities, and assessments.
- **Reduced production & delivery overhead** — Minimizes repetitive prep and support; every learner gets a dedicated “AI tutor.”
- **Multi-channel integration** — Embeddable in websites, course platforms, and enterprise training portals.

# Use Cases

- **Course creators** — Hand a single lesson framework to AI-Shifu; learners receive personalized explanations and real-time interaction.
- **Enterprise training** — Input training content once; employees get role- and background-specific learning paths.
- **Educators** — Provide a syllabus to generate personalized coaching content plus a Q&A assistant.

# Roadmap

- [ ] Writing AI agent for rapid script generation and maintenance
- [ ] Knowledge base
- [ ] Speech input and output

# Using AI-Shifu

## Platform

[AI-Shifu.com](https://ai-shifu.com) is an education platform powered by AI-Shifu. You can try it and learn the AI-guided courses developed by human experts.

## Self-hosting

> For source code installation, please refer to the [Installation Manual](INSTALL_MANUAL.md)

Make sure your machine has installed [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/).

### Quick Start (Docker, zero config)

```bash
git clone https://github.com/ai-shifu/ai-shifu.git
cd ai-shifu/docker

# Use Docker-ready defaults (matches bundled MySQL service; Redis is optional)
cp .env.example.full .env

# Only required change: edit .env and set at least one LLM API key
# (e.g., OPENAI_API_KEY=sk-..., ERNIE_API_KEY=..., etc.)

# Start all services
docker compose -f docker-compose.latest.yml up -d
```

Notes

- First verified user is automatically promoted to Admin and Creator; the bundled demo course is assigned to this user.
- Default universal verification code for demos is 1024 (change via `UNIVERSAL_VERIFICATION_CODE`).
- `docker-compose.latest.yml` pulls the freshest `:latest` images (or your own locally built `latest` tags). Use `docker-compose.yml` when you need pinned release tags for reproducible environments.

### Using Docker Hub image (customize)

```bash
git clone https://github.com/ai-shifu/ai-shifu.git
cd ai-shifu/docker

# Copy the full template (contains defaults for Docker usage)
cp .env.example.full .env

# Edit .env and customize as needed (only mandatory change is an LLM key):
# - OPENAI_API_KEY / ERNIE_API_KEY / GLM_API_KEY / ...
# - SQLALCHEMY_DATABASE_URI: Defaults to docker MySQL service
# - REDIS_HOST: Optional; set to enable Redis caching/locks (leave empty to disable)
# - SECRET_KEY: Defaults to a demo value; change for production (generate with: python -c "import secrets; print(secrets.token_urlsafe(32))")
# - UNIVERSAL_VERIFICATION_CODE: Test verification code (remove/empty in production)
# - Any other optional integrations

docker compose -f docker-compose.latest.yml up -d  # Use -f docker-compose.yml for pinned versions
```

### Development mode (dev_in_docker.sh)


```bash
git clone https://github.com/ai-shifu/ai-shifu.git
cd ai-shifu/docker

cp .env.example.full .env
# Edit .env and set your preferred LLM API key(s)

./dev_in_docker.sh
```

`dev_in_docker.sh` builds the backend and frontend images from your local source tree and then launches `docker-compose.dev.yml` (hot reload + bind mounts). Use it whenever you need to iterate on code without managing Python/Node runtimes locally.

### Compose files

- `docker-compose.latest.yml`: tracks the `:latest` tags for `aishifu/ai-shifu-api` and `aishifu/ai-shifu-cook-web`. Use this when you want the freshest container build (either from Docker Hub or after running your own `docker build ... -t aishifu/...:latest`).
- `docker-compose.yml`: pins each image to a specific release tag for reproducible deployments (recommended for staging/prod mirrors or CI).

### Access

After Docker starts:

1. Open `http://localhost:8080` in your browser to access Cook Web (learner interface and authoring console)
2. Use any phone number for login; the default universal verification code is **1024** (for demo/testing only — change or disable in production)
3. The first verified user becomes Admin and Creator

## Internationalization (i18n)

- Shared translations live in `src/i18n/<locale>/**/*.json` and are consumed by both Backend and Cook Web.
- See the consolidated guide for conventions, scripts, and CI checks: `docs/i18n.md`.
- Frontend language list only exposes `en-US` and `zh-CN`.

## Text-to-Speech (TTS)

AI-Shifu supports multiple TTS providers. To enable Volcengine HTTP v1/tts, set:

- `VOLCENGINE_TTS_APP_KEY` (AppID)
- `VOLCENGINE_TTS_ACCESS_KEY` (Token used by `Authorization: Bearer;{token}`)
- `VOLCENGINE_TTS_CLUSTER_ID` (Cluster, e.g., `volcano_tts`)

In Shifu settings, select the provider name `volcengine_http` and choose a voice/model.
