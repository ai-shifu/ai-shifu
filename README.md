<div align="center">
  <img src="assets/logo_en.png" width=256></img>
  <p><strong>Shifu (master) mode</strong>: Expert-led, AI-delivered, user follows, interaction at any time</p>

English | [简体中文](README_ZH-CN.md)
</div>

AI-Shifu is a guide powered by LLM. Unlike other human-led chatbots, AI-Shifu is AI-led chat flow, and humans just need to follow. Although in the process, humans can ask questions at any time and affect the content of the conversation, it will eventually return to the AI-led storyline. And AI can make personalized output based on user identity, interests, and preferences, making users feel like they are being served one-on-one. In education, storytelling, product guides, surveys, and game NPC scenarios, AI-Shifu can provide a more interactive and immersive experience.

# Features

1. **Controllable Chat Flow**: Use preset prompts to constrain AI's output and control the chat process.
2. **Interactive**: Allow asking questions to the user and obtaining feedback.
3. **Personalized**: Make personalized output based on user input such as identity, interests, and preferences.
4. **Q & A**: Ask questions based on context at any time to get more information.
5. **Script Development Environment**: Use Lark multi-dimensional tables as an editor, combined with a debugger, to easily debug script prompts.

# Roadmap

- [ ] Better script development environment, abandon the dependency on Lark
- [ ] Refactor the user experience of Q & A
- [ ] Support knowledge base
- [ ] Continuous output mode
- [ ] Speech input and output

# Using AI-Shifu

## Platform

[AI-Shifu.com](https://ai-shifu.com) is an education platform powered by AI-Shifu. You can try it and learn the AI-guided courses developed by human experts.

## Self-hosting

Make sure your machine has installed [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/).

### Using Docker Hub image

```bash
git clone https://github.com/ai-shifu/ai-shifu.git
cd ai-shifu/docker
cp .env.example .env
# Modify the configuration in the .env file. At least one LLM access key should be configured, and set DEFAULT_LLM_MODEL to the name of the model
docker compose up -d
```

Then visit `http://localhost:8080`.

### Building from source code
#### Building docker image

```bash
git clone https://github.com/ai-shifu/ai-shifu.git
cd ai-shifu/docker
cp .env.example .env
# Modify the configuration in the .env file. At least one LLM access key should be configured, and set DEFAULT_LLM_MODEL to the name of the model
./dev_in_docker.sh
```

Then visit `http://localhost:8080`.


#### Building and configuring from source code directly
[Install Manual](INSTALL_MANUAL.md)
