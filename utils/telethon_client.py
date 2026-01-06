import asyncio
import logging
import os
from typing import Optional

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

from config.settings import settings

logger = logging.getLogger(__name__)


class TelethonUploader:
    """Telethon client for uploading large files (up to 2GB)"""

    def __init__(self):
        self.client: Optional[TelegramClient] = None
        self.is_initialized = False

    async def initialize(self):
        """Initialize Telethon client"""
        if self.is_initialized:
            return True

        # Check if credentials are configured
        if not settings.TELEGRAM_API_ID or not settings.TELEGRAM_API_HASH:
            logger.warning(
                "Telethon credentials not configured. Large file uploads (>50MB) will not work."
            )
            return False

        try:
            # Create session file in downloads directory
            session_path = os.path.join(settings.TEMP_DOWNLOAD_PATH, "telethon_session")

            self.client = TelegramClient(
                session_path,
                settings.TELEGRAM_API_ID,
                settings.TELEGRAM_API_HASH,
            )

            await self.client.start(phone=settings.TELEGRAM_PHONE)

            if not await self.client.is_user_authorized():
                logger.error(
                    "Telethon client is not authorized. Please run setup script."
                )
                return False

            self.is_initialized = True
            logger.info("Telethon client initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize Telethon client: {e}", exc_info=True)
            return False

    async def upload_file(
        self,
        chat_id: int,
        file_path: str,
        caption: str = "",
        progress_callback=None,
    ) -> bool:
        """
        Upload a file to Telegram using Telethon (supports up to 2GB)

        Args:
            chat_id: Telegram user/chat ID
            file_path: Path to file to upload
            caption: File caption
            progress_callback: Optional callback for upload progress

        Returns:
            True if upload successful, False otherwise
        """
        if not self.is_initialized:
            await self.initialize()

        if not self.is_initialized or not self.client:
            logger.error("Telethon client not initialized")
            return False

        try:
            # Get file size
            file_size = os.path.getsize(file_path)
            logger.info(f"Uploading file via Telethon: {file_size / (1024*1024):.1f}MB")

            # Progress callback wrapper
            async def progress(current, total):
                if progress_callback:
                    percentage = (current / total) * 100 if total > 0 else 0
                    await progress_callback(percentage, current, total)

            # Send the file
            await self.client.send_file(
                chat_id,
                file_path,
                caption=caption,
                progress_callback=progress if progress_callback else None,
            )

            logger.info(f"File uploaded successfully via Telethon to {chat_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to upload file via Telethon: {e}", exc_info=True)
            return False

    async def disconnect(self):
        """Disconnect Telethon client"""
        if self.client and self.is_initialized:
            await self.client.disconnect()
            self.is_initialized = False


# Global instance
telethon_uploader = TelethonUploader()
