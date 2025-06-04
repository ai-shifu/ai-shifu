<div align="center">
  <img src="assets/logo_zh.png" width=256></img>
<p><strong>师傅模式</strong>：专家主导，AI 交付，用户跟从，随时互动</p>

[English](README.md) | 简体中文
</div>

AI 师傅是一个由大语言模型驱动的向导。与其他由人类主导的聊天机器人不同，AI 师傅是 AI 主导对话流，人类只需要跟随引导。虽然在过程中，人类随时可以提问，影响对话内容，但最终还是会回到 AI 主导的故事线。并且，AI 可以根据用户的身份背景、兴趣偏好等进行个性化输出，让用户体验到一对一的服务。在教育培训、小说故事、产品指南、调查问卷和游戏 NPC 等场景，AI 师傅都能提供更具互动性和沉浸感的体验。

# 功能特性

1. **可控对话流**：用预设的提示词剧本约束 AI 的输出，控制对话过程。
2. **互动**：对话中可以向用户提出问题，获得用户的输入反馈。
3. **个性化**：根据用户输入的身份背景、兴趣偏好等信息进行个性化输出。
4. **追问**：随时基于上下文提问，获得更多信息。
5. **剧本开发环境**：用飞书多维表格做编辑器，配合调试器，可以便捷地调试剧本提示词。

# 开发计划

- [ ] 更好的剧本开发环境，抛弃对飞书的依赖
- [ ] 重构追问的用户体验
- [ ] 支持知识库
- [ ] 连续输出模式
- [ ] 语音输入输出

# 使用 AI 师傅

## 平台

[AI-Shifu.com](https://ai-shifu.com) 是一个由 AI 师傅驱动的教育平台。你可以在上面尝试学习由专家开发、AI 主导的课程。

## 自建站

请先确认你的机器已经安装好[Docker](https://docs.docker.com/get-docker/)和[Docker Compose](https://docs.docker.com/compose/install/)。

### 使用 Docker Hub 镜像

```bash
git clone https://github.com/ai-shifu/ai-shifu.git
cd ai-shifu/docker
cp .env.example .env
# 修改 .env 文件中的配置。至少要配置好一个大模型的参数，并将 DEFAULT_LLM_MODEL 设置为该模型的名称
docker compose up -d
```

然后访问 `http://localhost:8080`。

### 从源代码构建

```bash
git clone https://github.com/ai-shifu/ai-shifu.git
cd ai-shifu/docker
cp .env.example .env
# 修改 .env 文件中的配置。至少要配置好一个大模型的参数，并将 DEFAULT_LLM_MODEL 设置为该模型的名称
./dev_in_docker.sh
```

然后访问 `http://localhost:8080`。
