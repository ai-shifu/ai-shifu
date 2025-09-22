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

### 使用 Docker Hub 镜像

```bash
git clone https://github.com/ai-shifu/ai-shifu.git
cd ai-shifu/docker

# 最小化配置（仅必需变量）：
cp .env.example.minimal .env

# 或选择完整配置选项：
cp .env.example.full .env

# 编辑 .env 文件并配置必需的变量：
# - SQLALCHEMY_DATABASE_URI: 数据库连接
# - SECRET_KEY: JWT签名密钥（生成方法: python -c "import secrets; print(secrets.token_urlsafe(32))"）
# - UNIVERSAL_VERIFICATION_CODE: 测试验证码
# - 至少一个大模型 API key（OPENAI_API_KEY、ERNIE_API_KEY 等）

docker compose up -d
```

### 从源代码构建

```bash
git clone https://github.com/ai-shifu/ai-shifu.git
cd ai-shifu/docker

# 选择配置模板：
cp .env.example.minimal .env  # 最小化配置
# 或
cp .env.example.full .env      # 完整配置

# 在 .env 文件中配置必需的变量
# 参考 .env.example.minimal 了解必需变量
# 参考 .env.example.full 了解所有可用选项

./dev_in_docker.sh
```

### 访问

Docker 启动后：
1. 用浏览器打开 `http://localhost:8080`，访问用户界面
2. 用浏览器打开 `http://localhost:8081`，访问剧本编辑器
3. 登录时可使用任意手机号，默认万能验证码为 **1024**（仅用于演示/测试，生产环境务必修改或禁用）
