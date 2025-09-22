<div align="center">
  <img src="assets/logo_en.png" width=256></img>
<p><strong>Create Once,Teach Personally.</strong></p>

English | [简体中文](README_ZH-CN.md)

</div>
AI-Shifu is designed for creators, instructors, and training/education teams, offering a scalable one-on-one teaching agent. Provide your expertise and teaching intent once，AI-Shifu will expand it into complete, personalized learning experiences. It adapts in real time to each learner’s profile with tailored explanations, interactive probing, assessments, and a full feedback loop—amplifying both your efficiency and the learner’s experience.

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

### Using Docker Hub image

```bash
git clone https://github.com/ai-shifu/ai-shifu.git
cd ai-shifu/docker

# For minimal setup (only required variables):
cp .env.example.minimal .env

# Or for full configuration options:
cp .env.example.full .env

# Edit .env and configure the required variables:
# - SQLALCHEMY_DATABASE_URI: Database connection
# - SECRET_KEY: JWT signing key (generate with: python -c "import secrets; print(secrets.token_urlsafe(32))")
# - UNIVERSAL_VERIFICATION_CODE: Test verification code
# - At least one LLM API key (OPENAI_API_KEY, ERNIE_API_KEY, etc.)

docker compose up -d
```

### Building from source code

```bash
git clone https://github.com/ai-shifu/ai-shifu.git
cd ai-shifu/docker

# Choose configuration template:
cp .env.example.minimal .env  # For minimal setup
# OR
cp .env.example.full .env      # For full configuration

# Configure the required variables in .env file
# See .env.example.minimal for required variables
# See .env.example.full for all available options

./dev_in_docker.sh
```

### Access

After Docker starts:
1. Open `http://localhost:8080` in your browser to access the user interface
2. Open `http://localhost:8081` in your browser to access the script editor
3. Use any phone number for login; the default universal verification code is **1024** (for demo/testing only — change or disable in production)
