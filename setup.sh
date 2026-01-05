#!/bin/bash

# Social Media Downloader Bot - Setup Script

echo "🚀 Setting up Social Media Downloader Bot..."

# Check if .env exists
if [ ! -f .env ]; then
    echo "📝 Creating .env file from template..."
    cp .env.example .env
    echo "⚠️  Please edit .env file with your credentials:"
    echo "   - TELEGRAM_BOT_TOKEN"
    echo "   - DATABASE_URL"
    echo ""
fi

# Check PostgreSQL
echo "🔍 Checking PostgreSQL..."
if command -v psql &> /dev/null; then
    echo "✅ PostgreSQL is installed"
else
    echo "❌ PostgreSQL not found. Please install it:"
    echo "   brew install postgresql@14"
fi

# Check Redis
echo "🔍 Checking Redis..."
if command -v redis-cli &> /dev/null; then
    echo "✅ Redis is installed"
    # Check if Redis is running
    if redis-cli ping &> /dev/null; then
        echo "✅ Redis is running"
    else
        echo "⚠️  Redis is not running. Start it with:"
        echo "   brew services start redis"
    fi
else
    echo "❌ Redis not found. Please install it:"
    echo "   brew install redis"
fi

# Create downloads directory
echo "📁 Creating downloads directory..."
mkdir -p downloads

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Edit .env file with your bot token and database credentials"
echo "2. Make sure PostgreSQL and Redis are running"
echo "3. Run: python bot.py"
echo ""
