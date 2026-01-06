#!/usr/bin/env python3
"""
Social Media Downloader Telegram Bot
A scalable bot for downloading videos from various social media platforms
"""

import logging

from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from config import settings
from database import init_db
from handlers import (
    handle_quality_selection,
    handle_url,
    help_command,
    history_command,
    history_pagination_callback,
    restore_command,
    start_command,
)

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


async def post_init(application: Application):
    """Initialize database after bot is ready"""
    logger.info("Initializing database...")
    init_db()
    logger.info("Database initialized successfully")


async def error_handler(update: object, context: object):
    """Handle errors"""
    logger.error(msg="Exception while handling an update:", exc_info=context.error)

    if update and hasattr(update, "effective_message"):
        await update.effective_message.reply_text(
            "❌ An error occurred while processing your request. Please try again later."
        )


def main():
    """Start the bot"""
    # Validate bot token
    if not settings.TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not found in environment variables")
        return

    # Create application with increased timeouts for large file uploads
    from telegram.request import HTTPXRequest

    request = HTTPXRequest(
        connection_pool_size=8,
        read_timeout=120.0,
        write_timeout=120.0,
        connect_timeout=30.0,
    )

    application = (
        Application.builder()
        .token(settings.TELEGRAM_BOT_TOKEN)
        .request(request)
        .concurrent_updates(True)
        .post_init(post_init)
        .build()
    )

    # Add command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("history", history_command))
    application.add_handler(CommandHandler("restore", restore_command))

    # Handle /restore_ID pattern - must come before URL handler
    from telegram.ext import MessageHandler
    from telegram.ext import filters as tg_filters

    application.add_handler(
        MessageHandler(tg_filters.Regex(r"^/restore_\d+$"), restore_command)
    )
    application.add_handler(
        MessageHandler(tg_filters.Regex(r"^/restore\d+$"), restore_command)
    )

    # Add callback query handlers for format type and quality selection
    application.add_handler(
        CallbackQueryHandler(handle_quality_selection, pattern="^type_")
    )
    application.add_handler(
        CallbackQueryHandler(handle_quality_selection, pattern="^quality_")
    )

    # Add callback query handler for history pagination
    application.add_handler(
        CallbackQueryHandler(history_pagination_callback, pattern="^history_page_")
    )

    # Add message handler for URLs - MUST be last
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))

    # Add error handler
    application.add_error_handler(error_handler)

    # Start bot
    logger.info("Bot is starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
