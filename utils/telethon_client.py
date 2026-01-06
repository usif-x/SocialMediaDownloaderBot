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
        Upload a file to Telegram using Telethon and return file_id for bot to use

        Args:
            chat_id: Telegram user/chat ID (used to send to "me" to get file_id)
            file_path: Path to file to upload
            caption: File caption
            progress_callback: Optional callback for upload progress

        Returns:
            Tuple of (file_id, error_message) - file_id if successful, None and error if failed
        """
        if not self.is_initialized:
            await self.initialize()

        if not self.is_initialized or not self.client:
            logger.error("Telethon client not initialized")
            return None, "Telethon not initialized"

        try:
            # Get file size
            file_size = os.path.getsize(file_path)
            logger.info(
                f"Uploading file via Telethon to get file_id: {file_size / (1024*1024):.1f}MB"
            )

            # Progress callback wrapper
            async def progress(current, total):
                if progress_callback:
                    percentage = (current / total) * 100 if total > 0 else 0
                    await progress_callback(percentage, current, total)

            # Send file to "me" (Saved Messages) to get file_id
            # This uploads the file without sending to the user
            sent_message = await self.client.send_file(
                "me",  # Send to ourselves (Saved Messages)
                file_path,
                caption=caption,
                progress_callback=progress if progress_callback else None,
            )

            # Extract file_id from the sent message
            file_id = None
            if sent_message and sent_message.media:
                # Get the document (for videos/files)
                if hasattr(sent_message.media, "document"):
                    # We need to get the file_id that Bot API can use
                    # Telethon uses different file references than Bot API
                    # We'll return the message so bot can forward it
                    logger.info(
                        f"File uploaded successfully via Telethon, message_id: {sent_message.id}"
                    )
                    return sent_message, None

            logger.error("Could not extract file info from uploaded message")
            return None, "Failed to get file info"

        except Exception as e:
            logger.error(f"Failed to upload file via Telethon: {e}", exc_info=True)
            return None, str(e)

    async def forward_to_user(self, message, chat_id: int) -> bool:
        """
        Forward the uploaded message to user

        Args:
            message: The message object from upload_file
            chat_id: Target user chat ID

        Returns:
            True if successful, False otherwise
        """
        try:
            # Get user entity
            entity = await self.client.get_entity(chat_id)

            # Forward the message
            await self.client.forward_messages(entity, message)

            logger.info(f"Message forwarded to user {chat_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to forward message: {e}", exc_info=True)
            return False

    async def disconnect(self):
        """Disconnect Telethon client"""
        if self.client and self.is_initialized:
            await self.client.disconnect()
            self.is_initialized = False


# Global instance
telethon_uploader = TelethonUploader()
