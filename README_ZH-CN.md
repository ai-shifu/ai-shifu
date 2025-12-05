<div align="center">
  <img src="assets/logo_zh.png" width=256></img>
<p><strong>低成本、可规模化的‘一对一’教师智能体。</strong></p>

[English](README.md) | 简体中文

</div>

AI师傅面向创作者、讲师、培训与教育团队，提供“可扩展的一对一教学代理”。你将一次性输入专业知识与教学意图，AI师傅负责按学习者画像实时个性化讲解、互动追问、测评与反馈闭环，把你的人效与体验同时放大。

# 核心能力

- 个性化讲解引擎：基于学习者画像（背景/目标/水平）动态生成讲解路径与用词风格。
- 互动式答疑与追问：在学习会话中自动拆解问题、反问澄清、给出下一步行动。
- 快速搭建课程：创作者通过 MarkdownFlow 创作，即可生成完整的课程内容。
- 降低交付成本：大幅减少重复讲解与答疑，每个学习者都能获得“专属 AI 家教”体验。
- 多端集成：支持在网站、课程平台、企业内训门户等场景嵌入。

# 使用场景

- 知识付费讲师：把一份教案交给 AI-Shifu，学员可得到个性化讲解和实时互动。
- 企业培训：一次性录入培训内容，员工根据岗位和背景获取差异化学习路径。
- 教育工作者：将教学大纲交给 AI-Shifu，生成个性化辅导内容、答疑助手。

# 开发计划

- [ ] 写作智能体，快速生成、维护剧本
- [ ] 知识库
- [ ] 语音输入输出

# 使用 AI 师傅

## 平台

[AI-Shifu.com](https://ai-shifu.com) 是一个由 AI 师傅开源项目驱动的教育平台。可以在上面学习各种 AI 课程。

## 自建站

> 如需从源代码安装，请参考 [安装手册](INSTALL_MANUAL.md)。

请先确认你的机器已经安装好[Docker](https://docs.docker.com/get-docker/)和[Docker Compose](https://docs.docker.com/compose/install/)。

### 一键快速启动（Docker，无需修改）

```bash
git clone https://github.com/ai-shifu/ai-shifu.git
cd ai-shifu/docker

# 直接使用 Docker 模板配置
cp .env.example.full .env

# 唯一需要改动的内容：在 .env 中填写至少一个大模型 API Key
# 例如：OPENAI_API_KEY=sk-xxx 或 ERNIE_API_KEY=xxx

# 启动全部服务
docker compose -f docker-compose.latest.yml up -d
```

说明

- 第一个完成验证登录的用户会自动成为管理员和创作者；并获得内置 Demo 课程的所有权。
- 默认通用验证码为 1024（仅用于演示/测试，生产环境请修改或禁用）。
- `docker-compose.latest.yml` 使用 `:latest` 镜像标签，适合希望获取最新构建的场景（或在本地构建 `:latest` 镜像后启动）; 如需固定版本，可使用 `docker-compose.yml`。

### 使用 Docker Hub 镜像（需定制时）

```bash
git clone https://github.com/ai-shifu/ai-shifu.git
cd ai-shifu/docker

# 复制完整模板（已包含 Docker 默认值）
cp .env.example.full .env

# 按需修改 .env（快速启动仅需填写 LLM Key）：
# - OPENAI_API_KEY / ERNIE_API_KEY / GLM_API_KEY / ...
# - SQLALCHEMY_DATABASE_URI：默认指向 docker 中的 MySQL 服务
# - REDIS_HOST：默认指向 docker 中的 Redis 服务
# - SECRET_KEY：示例值，仅用于演示；生产环境请替换（生成：python -c "import secrets; print(secrets.token_urlsafe(32))"）
# - UNIVERSAL_VERIFICATION_CODE：测试验证码（生产环境请清空/禁用）

docker compose -f docker-compose.latest.yml up -d  # 若需固定版本可改用 docker-compose.yml
```


### 开发模式（dev_in_docker.sh）


```bash
git clone https://github.com/ai-shifu/ai-shifu.git
cd ai-shifu/docker

cp .env.example.full .env
# 在 .env 中填入至少一个大模型 API Key

./dev_in_docker.sh
```

`dev_in_docker.sh` 会从本地源码构建后端与前端镜像，并启动 `docker-compose.dev.yml`（包含热更新和挂载代码目录），适合日常开发迭代。

### Compose 文件的区别

- `docker-compose.latest.yml`：跟随 `:latest` 镜像标签，获取最新构建（或你本地打的 `latest` 镜像），适合快速验证。
- `docker-compose.yml`：固定到具体版本号，便于构建可复现的预发布/生产环境。

### 访问

Docker 启动后：

1. 用浏览器打开 `http://localhost:8080`，访问 Cook Web（学习端与内容管理界面）
2. 登录时可使用任意手机号，默认万能验证码为 **1024**（仅用于演示/测试，生产环境务必修改或禁用）
3. 第一个验证通过的用户会成为管理员与创作者

## 国际化（i18n）

- 共享翻译位于 `src/i18n/<locale>/**/*.json`，后端与 Cook Web 共用。
- 统一指南（规范、脚本、CI 校验）：`docs/i18n.md`。
- 前端语言列表只展示 `en-US` 与 `zh-CN`。
