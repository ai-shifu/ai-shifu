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

Choose and copy the appropriate environment template:

```bash
# For minimal setup (only required variables):
cp docker/.env.example.minimal docker/.env

# OR for full configuration with all options:
cp docker/.env.example.full docker/.env
```

### Step 3: Configure Environment Variables

Edit the `.env` file and configure the required settings.

#### Required Variables (MUST be configured)

These variables are essential for the application to run:

1. **Database Connection**
   - `SQLALCHEMY_DATABASE_URI`: MySQL connection string
   - Example: `mysql://root:password@localhost:3306/ai-shifu?charset=utf8mb4`

2. **Security**
   - `SECRET_KEY`: JWT signing key for authentication
   - Generate secure key: `python -c "import secrets; print(secrets.token_urlsafe(32))"`
   - **Important**: Use different keys for dev/test/prod environments

3. **LLM Provider** (at least one required)
   - Choose from: OpenAI, ERNIE, ARK, SiliconFlow, GLM, DeepSeek, Qwen
   - See `.env.example.full` for specific provider configurations

#### Configuration Reference

- **Minimal Configuration**: See `docker/.env.example.minimal`
  - Contains only the 3 required variables plus LLM configuration
  - Best for quick setup and testing

- **Full Configuration**: See `docker/.env.example.full`
  - Contains all 106+ available configuration options
  - Includes detailed descriptions and examples
  - Organized by categories: Database, Redis, Auth, LLM, etc.

#### Important Notes

- All sensitive values (API keys, passwords) should be kept secure
- Never commit `.env` files to version control
- For production deployments, use environment-specific configurations
- Refer to the example files for detailed explanations of each variable

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

# Update API base URL
REACT_APP_BASEURL="http://localhost:5800"
```

#### Step 4.3: Start Backend API

```bash
cd src/api
# Copy the environment configuration from docker directory
cp ../../docker/.env .env

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
# Copy the environment configuration from docker directory
cp ../../docker/.env .env

# Install Node.js dependencies
npm install  # or use pnpm install

# Start development server
npm run start:dev
```

The user frontend will be available at `http://localhost:3000`.

#### Step 4.5: Start Script Editor Frontend

```bash
cd src/cook-web
# Copy the environment configuration from docker directory
cp ../../docker/.env .env

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
