# AI-Shifu-TTS 部署指南

## 架构

```
浏览器 :80 → Nginx → /api/*      → Flask (gunicorn) :5800
                       → /_next/static/ → 直接读磁盘（缓存 30 天）
                       → 其余所有      → Next.js (standalone) :5000
```

需要 **3 个进程**：Nginx + gunicorn + Next.js standalone。Nginx 只代理静态资源从磁盘直接读取。

## 依赖

| 依赖 | 版本 |
|------|------|
| Node.js | 22.x |
| Python | 3.11+ |
| MySQL | 8.x |
| Redis | 7.x |
| uv | 最新（Python 包管理） |
| Nginx | 最新 |

## 步骤

### 1. 克隆项目

```bash
# Linux 服务器
git clone <repo> /home/ai-shifu-TTS
cd /home/ai-shifu-TTS

# Mac 本地
git clone <repo> /home/benben/ai-shifu-TTS
cd /home/benben/ai-shifu-TTS
```

### 2. 启动 MySQL 和 Redis

```bash
# Linux
sudo systemctl enable --now mysql redis

# Mac
brew services start mysql redis
```

### 3. 创建数据库

```bash
mysql -u root -e "CREATE DATABASE IF NOT EXISTS \`ai-shifu\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
```

### 4. 配置环境变量

```bash
cp docker/.env.example.full src/api/.env
cp docker/.env.example.full src/cook-web/.env
```

编辑 `src/api/.env`（`src/cook-web/.env` 内容相同），**必须修改**：

| 变量 | 改什么 |
|------|--------|
| `SECRET_KEY` | 生成随机值：`python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `SQLALCHEMY_DATABASE_URI` | 设 MySQL 密码，Docker 环境把 `ai-shifu-mysql` 改为 `127.0.0.1` |
| LLM key | 至少一个，如 `OPENAI_API_KEY="sk-..."` |
| `REDIS_HOST` | Docker 环境把 `ai-shifu-redis` 改为 `127.0.0.1` |
| `LOCAL_STORAGE_ROOT` | Linux 改为 `/home/ai-shifu-TTS/storage` |
| `I18N_ROOT` | 指向 i18n 目录，解决 standalone 模式下 `/api/i18n` 返回 500 |
| `SHARED_I18N_ROOT` | 同上，构建时需要 |

**⚠️ 注意**：`I18N_ROOT` 不能只写在 `.env` 文件里。因为 `server.js` 内部会执行 `process.chdir()` 把 CWD 改成 `.next/standalone/`，导致 `.env` 无法被加载。必须通过命令行或 systemd 传递：

```bash
# macOS/Linux
I18N_ROOT="$(cd src/cook-web && pwd)/../i18n" node .next/standalone/server.js
```

或者在 systemd 服务文件中使用 `Environment=I18N_ROOT=...`。

### 5. 后端

```bash
cd src/api

# 安装 Python 依赖
uv venv .venv
uv pip sync requirements.txt

# 数据库迁移
export FLASK_APP=app.py
.venv/bin/flask db upgrade
```

### 6. 前端

```bash
cd src/cook-web

npm install
npm run build

# 修复 standalone 模式下 CSS 等静态资源 404
cp -r .next/static .next/standalone/.next/static
```

> 这是 Next.js standalone 构建的已知限制——`npm run build` 不会把 `.next/static/` 自动复制到 standalone 输出目录。每次重新构建后都需要执行一次。

### 7. 创建存储目录

```bash
mkdir -p storage
```

### 8. 启动应用

```bash
# 终端 1 - 后端（gunicorn）
cd src/api
.venv/bin/gunicorn -w 4 -b 127.0.0.1:5800 --timeout 300 'app:app'

# 终端 2 - 前端（Next.js standalone server）
cd src/cook-web

# server.js 内部会改变工作目录，.env 无法被加载，所以先 export 环境变量
export I18N_ROOT="$(pwd)/../i18n"
node .next/standalone/server.js
```

Windows PowerShell：

```powershell
cd src/cook-web
$env:I18N_ROOT="$PWD\..\i18n"
node .next\standalone\server.js
```

验证：
- 后端：`curl http://127.0.0.1:5800/api/health`
- 前端：`curl http://127.0.0.1:5000`

### 9. 配置 Nginx

```bash
# Linux
sudo cp deploy/nginx/ai-shifu.conf /etc/nginx/conf.d/ai-shifu.conf

# Mac (Homebrew)
sudo cp deploy/nginx/ai-shifu.conf /opt/homebrew/etc/nginx/servers/ai-shifu.conf
```

**修改 nginx 配置中的两处路径**（`deploy/nginx/ai-shifu.conf`）：

```nginx
# 第 25 行：server_name（域名或保持 _）
server_name _ benben.local;    # Mac 局域网
server_name your-domain.com;   # Linux 云服务器

# 第 30 行：alias 路径（指向你的实际项目路径）
alias /home/ai-shifu-TTS/src/cook-web/.next/standalone/.next/static/;
```

Mac 局域网用 `benben.local` 访问，需在 `/etc/hosts` 确认：

```
127.0.0.1  benben.local
```

验证并启动：

```bash
nginx -t && sudo nginx -s reload
```

## 端口说明

| 端口 | 服务 | 访问方式 |
|------|------|----------|
| 80 | Nginx | 浏览器直接访问 `http://IP` 或域名 |
| 5800 | Flask | 仅本机，Nginx 代理 |
| 5000 | Next.js | 仅本机，Nginx 代理 |
| 3306 | MySQL | 仅本机 |
| 6379 | Redis | 仅本机 |

## Nginx 路由规则

| 请求路径 | 处理方式 |
|----------|----------|
| `/_next/static/*` | Nginx 直接从磁盘读取，不经过 Node |
| `/api/i18n` | 代理到 Next.js :5000 |
| `/api/config` | 代理到 Next.js :5000 |
| `/api/*` | 代理到 Flask :5800（SSE 流式，3600s 超时） |
| 其余所有 | 代理到 Next.js :5000 |

## 更新代码

```bash
cd /home/ai-shifu-TTS   # Mac: /home/benben/ai-shifu-TTS
git pull

# 后端
cd src/api && uv pip sync requirements.txt && cd ../..

# 前端
cd src/cook-web && npm install && npm run build && cp -r .next/static .next/standalone/.next/static && cd ../..

# 重启应用进程（kill 旧的再启动，或 systemd restart）
```

## 生产部署（systemd 托管）

Linux 服务器上建议用 systemd 托管应用进程。参考示例：

```ini
# /etc/systemd/system/ai-shifu-api.service
[Unit]
Description=AI-Shifu Flask API
After=network.target mysql.service redis.service

[Service]
Type=notify
User=www-data
WorkingDirectory=/home/ai-shifu-TTS/src/api
EnvironmentFile=/home/ai-shifu-TTS/src/api/.env
ExecStart=/home/ai-shifu-TTS/src/api/.venv/bin/gunicorn \
    -w 4 -b 127.0.0.1:5800 --timeout 300 'app:app'
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```ini
# /etc/systemd/system/ai-shifu-frontend.service
[Unit]
Description=AI-Shifu Frontend
After=network.target ai-shifu-api.service

[Service]
Type=simple
User=www-data
WorkingDirectory=/home/ai-shifu-TTS/src/cook-web
Environment=I18N_ROOT=/home/ai-shifu-TTS/src/i18n
ExecStart=/usr/bin/node /home/ai-shifu-TTS/src/cook-web/.next/standalone/server.js
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Celery worker/beat 如有需要同理添加。
