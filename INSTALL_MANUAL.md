# INSTALL FROM SOURCE CODE STEP BY STEP

## Prerequisites

### Architecture Overview

AI-Shifu consists of three main components:

```bash
src/
├── api/          # Backend API service (Flask/Python)
├── web/          # User frontend (React)
└── cook-web/     # Script editor frontend (Next.js)
```

- **api**: Backend API service built with Flask
- **web**: User-facing frontend application built with React
- **cook-web**: Script editor for creating and managing courses, built with Next.js

### Required Tools and Services

- **Python 3.11+** for backend API
- **Node.js 18+** for frontend applications
- **MySQL 8.0+** for database storage
- **Redis** for caching and session management
- **Docker & Docker Compose** (recommended for easy deployment)

### Required API Keys

At least one LLM provider must be configured:

- **OpenAI** API Key
- **Baidu ERNIE** API credentials
- **ByteDance Volcengine Ark** API Key
- **SiliconFlow** API Key
- **Zhipu GLM** API Key
- **DeepSeek** API Key
- **Alibaba Qwen** API Key

### Optional Services

- **Alibaba Cloud OSS** for file storage
- **Alibaba Cloud SMS** for phone verification
- **Langfuse** for LLM tracking
- **Email SMTP** for email verification

## Installation Steps

### Step 1: Clone the Repository

```bash
git clone https://github.com/ai-shifu/ai-shifu.git
cd ai-shifu
```

### Step 2: Set Up Environment Variables

Copy the example environment file:

```bash
cp docker/.env.example .env
```

### Step 3: Configure Environment Variables

Edit the `.env` file and configure the required settings:

#### LLM Configuration (Required)

At least one LLM provider must be configured:

```bash
# OpenAI
OPENAI_BASE_URL="https://api.openai.com/v1"
OPENAI_API_KEY="sk-..."

# Or use other providers like:
# ERNIE_API_ID="your-ernie-id"
# ERNIE_API_SECRET="your-ernie-secret"
# ERNIE_API_KEY="your-ernie-key"

# GLM_API_KEY="your-glm-key"
# DEEPSEEK_API_KEY="your-deepseek-key"
# QWEN_API_KEY="your-qwen-key"

# Set default model (must match your configured provider)
DEFAULT_LLM_MODEL="gpt-4o"

# Default LLM temperature
DEFAULT_LLM_TEMPERATURE=0.3
```

#### Database Configuration

```bash
# MySQL (adjust if running locally)
SQLALCHEMY_DATABASE_URI="mysql://root:ai-shifu@ai-shifu-mysql:3306/ai-shifu"

# Redis (adjust if running locally)
REDIS_HOST="ai-shifu-redis"
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=""
```

#### Application Settings

```bash
# Universal verification code for testing
UNIVERSAL_VERIFICATION_CODE="1024"

# Frontend configuration
REACT_APP_BASEURL="http://localhost:5800"
SITE_HOST="http://localhost:8081/"
```

#### Optional Services

```bash
# Alibaba Cloud OSS for file storage
ALIBABA_CLOUD_OSS_ACCESS_KEY_ID=""
ALIBABA_CLOUD_OSS_ACCESS_KEY_SECRET=""
ALIBABA_CLOUD_OSS_ENDPOINT="oss-cn-beijing.aliyuncs.com"
ALIBABA_CLOUD_OSS_BUCKET=""

# Email SMTP for email verification
SMTP_SERVER=""
SMTP_PORT=25
SMTP_USERNAME=""
SMTP_PASSWORD=""
SMTP_SENDER=""

```

### Step 4: Manual Installation (Development)

This section covers manual installation for development purposes or when you need more control over the setup.

#### Step 4.1: Set Up Database Services

Start MySQL and Redis services on your local machine or use Docker:

```bash
# Using Docker for databases only
docker run -d --name mysql -p 3306:3306 -e MYSQL_ROOT_PASSWORD=ai-shifu -e MYSQL_DATABASE=ai-shifu mysql:latest
docker run -d --name redis -p 6379:6379 redis:latest
```

#### Step 4.2: Configure Environment for Local Development

Update your `.env` file for local development:

```bash
# Update database URLs for local services
SQLALCHEMY_DATABASE_URI="mysql://root:ai-shifu@localhost:3306/ai-shifu"
REDIS_HOST="localhost"

# Update API base URL
REACT_APP_BASEURL="http://localhost:5800"
```

#### Step 4.3: Start Backend API

```bash
cd src/api
cp ../../.env .env

# Install Python dependencies
pip install -r requirements.txt

# Initialize database
flask db upgrade

# Start the API server
gunicorn -w 4 -b 0.0.0.0:5800 'app:app' --timeout 300 --log-level debug
```

#### Step 4.4: Start User Frontend

```bash
cd src/web
cp ../../.env .env

# Install Node.js dependencies
npm install  # or use pnpm install

# Start development server
npm run start:dev
```

The user frontend will be available at `http://localhost:3000`.

#### Step 4.5: Start Script Editor Frontend

```bash
cd src/cook-web
cp ../../.env .env

# Install Node.js dependencies
npm install  # or use pnpm install

# Start development server
npm run dev
```

The script editor will be available at `http://localhost:3001`.

## Troubleshooting

### Common Issues

1. **Database Connection Failed**
   - Ensure MySQL is running and accessible
   - Check database credentials in `.env`
   - Run `flask db upgrade` to initialize tables

2. **Redis Connection Failed**
   - Ensure Redis is running and accessible
   - Check Redis configuration in `.env`

3. **LLM API Errors**
   - Verify API keys are correct
   - Check API base URLs
   - Ensure the model name matches your provider

4. **Frontend Build Failures**
   - Ensure Node.js version is 18+
   - Clear node_modules and reinstall: `rm -rf node_modules && npm install`
   - Check for environment variable issues

### Log Files

- API logs: Check gunicorn output or `/var/log/ai-shifu.log`
- Frontend logs: Check browser console or terminal output

## Access the Application

### Manual Installation
- User Interface: `http://localhost:3000` (or configured PORT)
- Script Editor: `http://localhost:3001`
- API: `http://localhost:5800`

### Default Login
- Use any phone number for registration/login
- Default verification code: `1024`
