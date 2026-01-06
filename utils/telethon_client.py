import asyncio
import logging
import os
from typing import Optional

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

from config.settings import settings

logger = logging.getLogger(__name__)


class TelethonUploader:
    """Telethon client for uploading large files (up to 2GB) using user account"""

    def __init__(self):
        self.client: Optional[TelegramClient] = None
        self.is_initialized = False

    async def initialize(self):
        """Initialize Telethon client with user credentials (required for 2GB limit)"""
        if self.is_initialized:
            return True

        # Check if user credentials are configured
        # We NEED user account (not bot) to get 2GB limit
        if not settings.TELEGRAM_API_ID or not settings.TELEGRAM_API_HASH:
            logger.warning(
                "Telethon user credentials not configured. "
                "Large file uploads (>50MB) will not work. "
                "Get credentials from https://my.telegram.org/apps"
            )
            return False

        try:
            # Create session file in downloads directory
            session_path = os.path.join(settings.TEMP_DOWNLOAD_PATH, "telethon_session")
            os.makedirs(settings.TEMP_DOWNLOAD_PATH, exist_ok=True)

            self.client = TelegramClient(
                session_path,
                settings.TELEGRAM_API_ID,
                settings.TELEGRAM_API_HASH,
            )

            # Start with user phone number (required for 2GB limit)
            await self.client.start(phone=settings.TELEGRAM_PHONE)

            if not await self.client.is_user_authorized():
                logger.error(
                    "Telethon client is not authorized. Please run setup script: "
                    "python scripts/setup_telethon.py"
                )
                return False

            self.is_initialized = True
            logger.info("Telethon client initialized successfully with user account")
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
    ):
        """
        Upload a file to storage channel and return channel/message ID for bot to copy

        Args:
            chat_id: Not used anymore, kept for compatibility
            file_path: Path to file to upload
            caption: File caption
            progress_callback: Optional callback for upload progress

        Returns:
            Tuple of (channel_id, message_id) if successful, (None, error_msg) if failed
        """
        if not self.is_initialized:
            await self.initialize()

        if not self.is_initialized or not self.client:
            logger.error("Telethon client not initialized")
            return None, "Telethon not initialized"

        if not settings.STORAGE_CHANNEL_ID:
            logger.error("Storage channel not configured")
            return (
                None,
                "Storage channel not configured. Set STORAGE_CHANNEL_ID in .env",
            )

        try:
            # Get file size
            file_size = os.path.getsize(file_path)
            logger.info(
                f"Uploading file via Telethon to storage channel: {file_size / (1024*1024):.1f}MB"
            )

            # Progress callback wrapper
            async def progress(current, total):
                if progress_callback:
                    percentage = (current / total) * 100 if total > 0 else 0
                    await progress_callback(percentage, current, total)

            # Get channel entity
            try:
                channel = await self.client.get_entity(settings.STORAGE_CHANNEL_ID)
                logger.info(f"Resolved storage channel: {channel.id}")
            except Exception as e:
                logger.error(f"Failed to get storage channel: {e}")
                return None, f"Failed to access storage channel: {str(e)}"

            # Upload file to the storage channel
            sent_message = await self.client.send_file(
                channel,
                file_path,
                caption=caption,
                progress_callback=progress if progress_callback else None,
            )

            if sent_message:
                logger.info(
                    f"File uploaded to channel {settings.STORAGE_CHANNEL_ID}, "
                    f"message_id: {sent_message.id}"
                )
                # Return channel_id and message_id for bot to copy
                return settings.STORAGE_CHANNEL_ID, sent_message.id

            logger.error("Upload failed - no message returned")
            return None, "Upload failed"

        except Exception as e:
            logger.error(f"Failed to upload file via Telethon: {e}", exc_info=True)
            return None, str(e)

    async def disconnect(self):
        """Disconnect Telethon client"""
        if self.client and self.is_initialized:
            await self.client.disconnect()
            self.is_initialized = False


# Global instance
telethon_uploader = TelethonUploader()
