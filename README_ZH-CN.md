<div align="center">
  <img src="assets/logo_zh.png" width=256></img>
<p><strong>低成本、可规模化的‘一对一’教师智能体。</strong></p>

[English](README.md) | 简体中文

</div>

AI师傅面向老师、讲师、培训与教育团队，提供“可扩展的一对一教学代理”。你将一次性输入专业知识与教学意图，AI师傅负责按学习者画像实时个性化讲解、互动追问、测评与反馈闭环，把你的人效与体验同时放大。

开发者为 AI 师傅团队和哈尔滨工业大学智能软件工程研究中心。

# 核心能力

- 个性化讲解引擎：基于学习者画像（背景/目标/水平）动态生成讲解路径与用词风格。
- 互动式答疑与追问：在学习会话中自动拆解问题、反问澄清、给出下一步行动。
- 快速搭建课程：老师通过 MarkdownFlow 创作，即可生成完整的课程内容。
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
配置安装程序还需要在 Linux、macOS 或 WSL 中运行 Python 3.10 及以上版本。

### 快速启动（Docker）

```bash
git clone https://github.com/ai-shifu/ai-shifu.git
cd ai-shifu/docker

# 直接使用 Docker 模板配置
python3 ../scripts/prepare_env.py

# 编辑 .env：填写模型服务商 API Key，并将 LLM_MODEL_1_ID
# 设置为该服务商已配置的文本模型 ID（必填，没有默认值）。
# LLM_MODEL_1_NAME 可选；未填写或留空时直接显示模型 ID。
# 首位管理员使用手机号或邮箱加本地密码，无需配置短信或 SMTP。

# 启动全部服务
docker compose -f docker-compose.latest.yml up -d
```

说明

- `LLM_MODEL_1_ID` 必填且没有默认值；2–9 号模型 ID 可选，支持跳号。所有编号的 `NAME` 均可选，未填写或留空时直接显示该编号配置的模型 ID；只有名称、没有模型 ID 的编号不会展示。历史课程中的无效选择自动使用 1 号，无需数据清洗。
- 已有安装升级前，请按照[编号模型升级说明](INSTALL_MANUAL.md#upgrading-to-numbered-models)完成新编号配置，再启动新镜像；latest、固定版本和开发模式均适用。
- 新安装通过服务器控制台获取一次性初始化码，创建本地管理员和老师账号，并自动获得内置 Demo 课程的所有权。短信、SMTP 和 OAuth 可在需要学员登录或通知时再配置，详见[首位管理员初始化](INSTALL_MANUAL.md#first-administrator-setup)。
- 默认不配置通用验证码。普通部署需要使用已配置的短信或邮件服务商实际签发的验证码。隔离的开发或测试环境可按[显式开发登录说明](INSTALL_MANUAL.md#local-demo-login)启用测试旁路。
- 已有部署必须[升级 API 代码或镜像并移除旧旁路配置](INSTALL_MANUAL.md#upgrading-existing-verification-code-deployments)；仅修改环境示例文件不会修复旧镜像。
- `docker-compose.latest.yml` 使用 `:latest` 镜像标签，适合希望获取最新构建的场景（或在本地构建 `:latest` 镜像后启动）；全新安装固定版本时，需同时使用下方的 `docker-compose.yml` 与 `docker-compose.secret-key.yml`。
- 安装程序首次创建 `.env` 时会生成独立随机的 `SECRET_KEY`，文件权限为仅当前用户可读写。重启、升级以及所有后端容器和 worker 都复用该文件；请安全备份。已有文件只校验、不覆盖，修改前请阅读[密钥保留与恢复说明](INSTALL_MANUAL.md#secret-key-preservation-and-recovery)。

### 使用 Docker Hub 镜像（需定制时）

```bash
git clone https://github.com/ai-shifu/ai-shifu.git
cd ai-shifu/docker

# 创建私有配置，并自动生成 SECRET_KEY
python3 ../scripts/prepare_env.py

# 编辑 .env，必须同时配置服务商密钥和 1 号模型 ID：
# - OPENAI_API_KEY / ERNIE_API_KEY / BIGMODEL_API_KEY / ...
# - LLM_MODEL_1_NAME：可选的显示名称；留空时显示该编号配置的模型 ID
# - LLM_MODEL_1_ID：已配置的文本模型 ID，没有默认值
# - SQLALCHEMY_DATABASE_URI：默认指向 docker 中的 MySQL 服务
# - REDIS_HOST：可选；如需 Redis 缓存/锁可配置外部 Redis（留空则禁用）
# - SECRET_KEY：已由安装程序生成并保存，请保留该值
# - 短信或邮件发送：学员验证时按需配置；首位管理员初始化不需要
# - UNIVERSAL_VERIFICATION_CODE：保持为空；仅显式启用的隔离开发或测试应用可使用

docker compose -f docker-compose.latest.yml up -d

# 全新安装固定版本时，可改用以下命令（需要 Compose 2.24.4+）：
docker compose -f docker-compose.yml -f docker-compose.secret-key.yml up -d
```


### 开发模式（dev_in_docker.sh）


```bash
git clone https://github.com/ai-shifu/ai-shifu.git
cd ai-shifu/docker

python3 ../scripts/prepare_env.py
# 在 .env 中填入模型 API Key，并将 LLM_MODEL_1_ID
# 设置为该服务商已配置的文本模型 ID。
# LLM_MODEL_1_NAME 可选；留空时显示该编号配置的模型 ID。

./dev_in_docker.sh
```

`dev_in_docker.sh` 会从本地源码构建后端与前端镜像，并启动 `docker-compose.dev.yml`（包含热更新和挂载代码目录），适合日常开发迭代。

如果 `.env` 缺失，开发脚本会在构建前停止。全新安装请先执行上方配置安装命令；已有实例应从备份恢复原配置，避免丢失密钥后误生成新值。

此 Compose 模式显式选择 `app:create_development_app()`，并设置
`ENV=development`，但仍不提供通用验证码。管理员请使用[首位管理员初始化](INSTALL_MANUAL.md#first-administrator-setup)；学员验证码登录需配置真实发送服务。只有在隔离的本地测试中，才可主动设置非空的
`UNIVERSAL_VERIFICATION_CODE`。普通 `app:app` / `create_app()` 入口即使配置了该值或
`ENV=development`，也不会启用测试旁路。手动启动方式参见[本地演示登录说明](INSTALL_MANUAL.md#local-demo-login)。

脚本会在构建 Web 镜像前记录当前检出的提交，让用户菜单显示对应的源码版本。
不含 Git 元数据的源码压缩包只显示软件包版本号。

如果直接用 Compose 启动开发环境，请在 `docker/` 目录运行：

```bash
git rev-parse HEAD > ../src/web/.app-build-sha 2>/dev/null || rm -f ../src/web/.app-build-sha
docker compose -f docker-compose.dev.yml up --build -d
```

切换到其他提交后，再次启动时需重新生成标记并构建，避免已有开发镜像保留旧的提交号。

### Compose 文件的区别

- `docker-compose.latest.yml`：跟随 `:latest` 镜像标签，获取最新构建（或你本地打的 `latest` 镜像），适合快速验证。
- `docker-compose.yml`：固定到具体版本号。全新安装时，每次 Compose 命令都需加上 `-f docker-compose.secret-key.yml` 以使用自动生成的密钥。已有部署继续保留原命令和实际生效的密钥，迁移方式见安装手册。

### 访问

Docker 启动后：

1. 打开 `http://localhost:8080/admin`；新安装会进入初始化页面。
2. 在服务器控制台运行 `docker compose -f docker-compose.latest.yml exec ai-shifu-api flask console setup-code --origin http://localhost:8080`，获取一次性初始化码。
3. 输入初始化码、手机号或邮箱，并设置密码；手机号或邮箱仅作为尚未验证的本地登录账号，无需配置短信或邮件发送服务。以后通过 `/admin-login` 使用相同账号和密码登录，学员登录方式另行按需配置。

请使用包含此功能的 API/Web 镜像。已有实例升级不会重新开放网页初始化，原有账号继续可用；初始化和恢复命令详见[安装手册](INSTALL_MANUAL.md#first-administrator-setup)。

## 国际化（i18n）

- 共享翻译位于 `src/i18n/<locale>/**/*.json`，后端与 Cook Web 共用。
- [统一 i18n 指南](docs/references/i18n.md)包含产品语言交付清单、规范、脚本与 CI 校验。
- 前端支持的语言以 `src/i18n/locales.json` 为准。
