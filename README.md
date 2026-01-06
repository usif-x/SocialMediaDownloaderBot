# Social Media Downloader Bot

A scalable Telegram bot for downloading videos from various social media platforms using yt-dlp.

## Features

✨ **Multi-platform Support**: Download videos from YouTube, Instagram, Facebook, Twitter/X, TikTok, and 1000+ more sites
🎯 **Quality Selection**: Choose your preferred video/audio quality
🎵 **Audio Extraction**: Download audio-only with embedded thumbnails
📊 **Progress Tracking**: Real-time download progress in Telegram
💾 **Database Tracking**: PostgreSQL with SQLAlchemy for tracking users and downloads
⚡ **Redis Caching**: Fast state management and caching
👥 **Multi-user Support**: Handle multiple concurrent users
� **Large File Support**: Upload files up to 2GB using Telethon (optional)
�🐳 **Docker Ready**: Easy deployment with Docker and Coolify

## Project Structure

```
SocialMediaDownloader/
├── config/
│   ├── __init__.py
│   └── settings.py          # Configuration settings
├── database/
│   ├── __init__.py
│   ├── models.py            # SQLAlchemy models
│   └── database.py          # Database connection
├── handlers/
│   ├── __init__.py
│   ├── start.py             # Start command handler
│   ├── download.py          # Download handlers
│   └── callbacks.py         # Callback query handlers
├── utils/
│   ├── __init__.py
│   ├── downloader.py        # yt-dlp wrapper
│   ├── redis_client.py      # Redis operations
│   └── helpers.py           # Helper functions
├── bot.py                   # Main bot file
├── requirements.txt         # Dependencies
├── .env.example            # Environment variables example
└── README.md               # This file
```

## Installation

### Prerequisites

- Python 3.9+
- PostgreSQL
- Redis

### Setup

1. **Clone the repository**

   ```bash
   cd /Users/home/WorkSpace/TelegramBot/SocialMediaDownloader
   ```

2. **Create virtual environment**

   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

4. **Set up PostgreSQL**

   ```bash
   createdb telegram_bot
   ```

5. **Set up Redis**
   Make sure Redis is running:

   ```bash
   redis-server
   ```

6. **Configure environment variables**

   ```bash
   cp .env.example .env
   ```

   Edit `.env` with your credentials:

   ```
   TELEGRAM_BOT_TOKEN=your_bot_token_here
   DATABASE_URL=postgresql://user:password@localhost:5432/telegram_bot
   REDIS_HOST=localhost
   REDIS_PORT=6379
   ```

## Usage

### Running the Bot

```bash
python bot.py
```

### Large File Support (Optional)

For uploading files larger than 50MB (up to 2GB), set up Telethon:

```bash
# See detailed setup instructions
cat docs/TELETHON_SETUP.md

# Quick setup
python scripts/setup_telethon.py
```

Without Telethon: Files limited to 50MB  
With Telethon: Files up to 2GB supported!

### Using the Bot

1. Start a chat with your bot on Telegram
2. Send `/start` to initialize
3. Send any video URL
4. Select your preferred quality
5. Download starts automatically!

### Commands

- `/start` - Start the bot and register
- `/help` - Show help message

## Supported Platforms

The bot supports 1000+ websites including:

- YouTube
- Instagram
- Facebook
- Twitter/X
- TikTok
- Reddit
- Vimeo
- Dailymotion
- SoundCloud
- And many more!

## Configuration

### Environment Variables

| Variable                   | Description                      | Default                               |
| -------------------------- | -------------------------------- | ------------------------------------- |
| `TELEGRAM_BOT_TOKEN`       | Your Telegram Bot Token          | Required                              |
| `TELEGRAM_API_ID`          | Telegram API ID (for Telethon)   | Optional (for files >50MB)            |
| `TELEGRAM_API_HASH`        | Telegram API Hash (for Telethon) | Optional (for files >50MB)            |
| `TELEGRAM_PHONE`           | Phone number (for Telethon)      | Optional (for files >50MB)            |
| `DATABASE_URL`             | PostgreSQL connection URL        | `postgresql://localhost/telegram_bot` |
| `REDIS_HOST`               | Redis server host                | `localhost`                           |
| `REDIS_PORT`               | Redis server port                | `6379`                                |
| `MAX_CONCURRENT_DOWNLOADS` | Max simultaneous downloads       | `5`                                   |
| `DOWNLOAD_TIMEOUT`         | Download timeout in seconds      | `300`                                 |

## Database Schema

### Users Table

- Stores user information
- Tracks user activity
- Links to download history

### Downloads Table

- Tracks all download requests
- Stores video metadata
- Records download status and errors

## Architecture

The bot is designed with scalability in mind:

- **Concurrent Processing**: Handles multiple users simultaneously
- **Database Persistence**: PostgreSQL for reliable data storage
- **Caching Layer**: Redis for fast state management
- **Modular Design**: Separated concerns for easy maintenance
- **Error Handling**: Comprehensive error tracking and user feedback

## Development

### Adding New Features

1. **New Handlers**: Add to `handlers/` directory
2. **Database Models**: Update `database/models.py`
3. **Utilities**: Add helper functions to `utils/`
4. **Configuration**: Update `config/settings.py`

### Testing

Make sure PostgreSQL and Redis are running before testing:

```bash
# Test database connection
python -c "from database import init_db; init_db(); print('Database OK')"

# Test Redis connection
python -c "from utils import redis_client; print('Redis OK' if redis_client.is_healthy() else 'Redis Failed')"
```

## Docker Deployment

### Local Docker

```bash
# Build and run with docker-compose
docker-compose up -d

# View logs
docker-compose logs -f bot

# Stop
docker-compose down
```

### Deploy on Coolify

1. **Push to Git Repository** (GitHub, GitLab, etc.)

2. **In Coolify Dashboard:**

   - Create new project → Add Resource → Docker Compose
   - Connect your Git repository
   - Set the branch (e.g., `main`)

3. **Configure Environment Variables in Coolify:**

   ```
   TELEGRAM_BOT_TOKEN=your_bot_token_here
   ```

   The database and Redis are included in docker-compose, so you don't need external services.

4. **Deploy!**

### Environment Variables for Coolify

| Variable                   | Description                        | Default               |
| -------------------------- | ---------------------------------- | --------------------- |
| `TELEGRAM_BOT_TOKEN`       | Your Telegram bot token (required) | -                     |
| `DATABASE_URL`             | PostgreSQL connection string       | Set in docker-compose |
| `REDIS_HOST`               | Redis host                         | `redis`               |
| `REDIS_PORT`               | Redis port                         | `6379`                |
| `MAX_CONCURRENT_DOWNLOADS` | Max parallel downloads             | `5`                   |
| `DOWNLOAD_TIMEOUT`         | Download timeout in seconds        | `300`                 |

## Troubleshooting

### Common Issues

1. **Bot Token Error**: Make sure `TELEGRAM_BOT_TOKEN` is set correctly in `.env`
2. **Database Connection**: Verify PostgreSQL is running and credentials are correct
3. **Redis Connection**: Ensure Redis server is running
4. **Download Failures**: Some platforms may have restrictions or require authentication

## License

This project is for educational purposes.

## Credits

- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot)
- [yt-dlp](https://github.com/yt-dlp/yt-dlp)
- [SQLAlchemy](https://www.sqlalchemy.org/)
- [Redis](https://redis.io/)

## Support

For issues and questions, please check the documentation or create an issue.

---

**Happy Downloading! 🚀**
