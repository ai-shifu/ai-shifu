![cover-v5-optimized](assets/logo_en.png)

AI Shifu is an open-source conversational AI powered by LLM, designed to lead and control dialogues. Unlike other chatbots, AI Shifu guides the conversation, while users can ask questions that influence the content, the dialogue always returns to the AI's main storyline. With human-designed prompt scripts, AI Shifu avoids hallucinations and minimizes user interference, offering a dynamic and autonomous conversational experience ideal for education, storytelling, product demos, surveys, interviews, and game NPCs.

[![GitHub stars](https://img.shields.io/github/stars/ai-shifu/ai-shifu?style=social)](https://github.com/ai-shifu/ai-shifu/stargazers)
[![GitHub followers](https://img.shields.io/github/followers/ai-shifu?style=social)](https://github.com/ai-shifu?tab=followers)

# Features

To be filled

# Using AI Shifu

- **Platform**
[AI-Shifu.com](https://ai-shifu.com) is an education platform powered by AI Shifu. You can try it and learn the AI-driven courses developed by experts.

- **Self-hosting**
Quickly get AI Shifu running in your environment with this [starter guide](#quick-start).

# Quick Start

Make sure that [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/) are installed on your machine. Then run the following command to start AI Shifu:

```bash
git clone git@github.com:ai-shifu/ai-shifu.git
cd ai-shifu/docker
cp .env.example .env
# Edit .env file to fill your configure
./dev_in_docker.sh
```

# Contributors

Code contributions should be checked with pre-commit hooks.

1. install pre-commit
```bash
pip install pre-commit
pre-commit install
```



To be updated.
