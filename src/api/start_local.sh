#!/bin/bash

# AI-Shifu Local API Server Startup Script

echo "🚀 Starting AI-Shifu API Server locally..."

# Load environment variables
export FLASK_APP=app.py
export FLASK_ENV=development
export FLASK_DEBUG=True

# Database connection - use Docker MySQL
export SQLALCHEMY_DATABASE_URI="mysql://root:ai-shifu@localhost:3306/ai-shifu?charset=utf8mb4"

# JWT Secret
export SECRET_KEY="xwCuWpG9sD7CYk99Rr27NKU9YQBV_ehQn3DEY0jvuBQ"

# Universal verification code for testing
export UNIVERSAL_VERIFICATION_CODE="1024"

# Redis (optional - use Docker Redis)
export REDIS_URL="redis://localhost:6379"

# Development settings
export NODE_ENV="development"

# Add a dummy LLM API key to satisfy validation (won't be used for basic auth)
export OPENAI_API_KEY="sk-dummy-key-for-development"

echo "📋 Environment variables set"
echo "🗄️  Database: mysql://root:***@localhost:3306/ai-shifu"

# Initialize database
echo "🗄️  Initializing database migrations..."
flask db upgrade || echo "⚠️  Database migration failed or no migrations needed"

# Start the API server
echo "🌟 Starting Flask development server on http://localhost:5001"
flask run --host=0.0.0.0 --port=5001
