import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    """Application settings"""

    # Telegram
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")

    # Telegram User Client (for large file uploads)
    TELEGRAM_API_ID: int = int(os.getenv("TELEGRAM_API_ID") or 0)
    TELEGRAM_API_HASH: str = os.getenv("TELEGRAM_API_HASH") or ""
    TELEGRAM_PHONE: str = os.getenv("TELEGRAM_PHONE") or ""

    # Storage Channel for large files
    STORAGE_CHANNEL_ID: int = int(os.getenv("STORAGE_CHANNEL_ID") or 0)

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://localhost/telegram_bot")

    # Redis
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", 6379))
    REDIS_DB: int = int(os.getenv("REDIS_DB", 0))
    REDIS_PASSWORD: str = os.getenv("REDIS_PASSWORD", "")

    # Application
    MAX_CONCURRENT_DOWNLOADS: int = int(os.getenv("MAX_CONCURRENT_DOWNLOADS", 5))
    DOWNLOAD_TIMEOUT: int = int(os.getenv("DOWNLOAD_TIMEOUT", 300))
    TEMP_DOWNLOAD_PATH: str = os.getenv("TEMP_DOWNLOAD_PATH", "./downloads")

    # Supported sites info
    SUPPORTED_SITES = ["YouTube"]


settings = Settings()
