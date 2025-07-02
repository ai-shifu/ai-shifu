<div align="center">
  <img src="assets/logo_zh.png" width=256></img>
<p><strong>你看到的一切，都是量身定制的</strong></p>

[English](README.md) | 简体中文

</div>

AI 师傅既是老师、主播、说书人，也是向导……作为一名 AI 驱动的讲述者，AI 师傅可以将任何文字内容以全方位个性化的方式呈现给每一位用户，创造前所未有的阅读体验。

<div align="center">
  <img src="assets/architecture.png" alt="系统架构示意图" height="329">
</div>

# 功能特性

1. **个性化输出**：根据用户的身份背景、兴趣偏好等，全方位个性化输出内容，媲美真人一对一的效果。
2. **丰富的媒体**：支持 Markdown、HTML、Mermaid 等多种格式的内容，以及嵌入图片、视频。
3. **内容安全**：通过预设的师傅剧本控制输出，减少大模型幻觉。
4. **追问**：用户可以随时提问，获得上下文相关的智能回答。
5. **互动**：随时向用户提问，基于用户的回答推动后续进程。
6. **剧本编辑器**：方便地编辑剧本，预览效果。

# 开发计划

- [ ] 整体重构
- [ ] 写作智能体，快速生成、维护剧本
- [ ] 知识库
- [ ] 语音输入输出

# 使用 AI 师傅

## 平台

[AI-Shifu.com](https://ai-shifu.com) 是一个由 AI 师傅开源项目驱动的教育平台。可以在上面学习各种 AI 课程。

## 自建站

> 如需从源代码安装，请参考 [安装手册](INSTALL_MANUAL.md)。

请先确认你的机器已经安装好[Docker](https://docs.docker.com/get-docker/)和[Docker Compose](https://docs.docker.com/compose/install/)。

### 使用 Docker Hub 镜像

```bash
git clone https://github.com/ai-shifu/ai-shifu.git
cd ai-shifu/docker
cp .env.example .env
# 修改 .env 文件中的配置。至少要配置好一个大模型的参数，并将 DEFAULT_LLM_MODEL 设置为该模型的名称
docker compose up -d
```

### 从源代码构建

```bash
git clone https://github.com/ai-shifu/ai-shifu.git
cd ai-shifu/docker
cp .env.example .env
# 修改 .env 文件中的配置。至少要配置好一个大模型的参数，并将 DEFAULT_LLM_MODEL 设置为该模型的名称
./dev_in_docker.sh
```

### 访问

Docker 启动后：
1. 用浏览器打开 `http://localhost:8080`，访问用户界面
2. 用浏览器打开 `http://localhost:8081`，访问剧本编辑器
3. 登录时可使用任意手机号，默认万能验证码为 **1024**（仅用于演示/测试，生产环境务必修改或禁用）
