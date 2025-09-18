#!/bin/bash

# AI-Shifu Local API Server Startup Script

echo "🚀 Starting AI-Shifu API Server locally..."

# Load environment variables from .env.local if it exists
if [ -f ".env.local" ]; then
    echo "📁 Loading environment variables from .env.local"
    # Source the file safely to avoid security issues with special characters
    set -a  # automatically export all variables
    source .env.local
    set +a  # turn off automatic export
else
    echo "⚠️  No .env.local file found. Please create one from .env.example"
fi

# Set default Flask configuration
export FLASK_APP=app.py
export FLASK_ENV=development
export FLASK_DEBUG=True

# Database connection - use environment variable or fail-fast
if [ -z "$SQLALCHEMY_DATABASE_URI" ]; then
    echo "❌ Error: SQLALCHEMY_DATABASE_URI environment variable is not set"
    echo "Please set it in your .env file or environment"
    echo "Example: export SQLALCHEMY_DATABASE_URI='mysql://username:password@localhost:3306/ai-shifu?charset=utf8mb4'"
    exit 1
fi

# JWT Secret - Use environment variable or fail-fast
if [ -z "$SECRET_KEY" ]; then
    echo "❌ Error: SECRET_KEY environment variable is not set"
    echo "Please set it in your .env file or environment"
    echo "Example: export SECRET_KEY='your-secret-key-here'"
    exit 1
fi

# Universal verification code - use environment variable only (no default for security)
if [ -z "$UNIVERSAL_VERIFICATION_CODE" ]; then
    echo "⚠️  Warning: UNIVERSAL_VERIFICATION_CODE environment variable is not set"
    echo "Set it in your .env file for development testing if needed."
    echo "Example: export UNIVERSAL_VERIFICATION_CODE='your-dev-code-here'"
fi

# Redis (optional - use Docker Redis)
export REDIS_URL="redis://localhost:6379"

# Development settings
export NODE_ENV="development"

# LLM API Key - use environment variable or warn if missing
if [ -z "$OPENAI_API_KEY" ]; then
    echo "⚠️  Warning: OPENAI_API_KEY environment variable is not set"
    echo "LLM features may not work properly. Set it in your .env file if needed."
    echo "Example: export OPENAI_API_KEY='sk-your-openai-key-here'"
fi

echo "📋 Environment variables set"
echo "🗄️  Database: ${SQLALCHEMY_DATABASE_URI%:*}:***@${SQLALCHEMY_DATABASE_URI#*@}"

# Initialize database
echo "🗄️  Initializing database migrations..."
flask db upgrade || echo "⚠️  Database migration failed or no migrations needed"

# Start the API server
echo "🌟 Starting Flask development server on http://localhost:5001"
flask run --host=0.0.0.0 --port=5001
