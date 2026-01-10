#!/usr/bin/env python3
"""
Social Media Downloader Telegram Bot
A scalable bot for downloading videos from various social media platforms
"""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    TypeHandler,
    filters,
)

from config import settings
from database import init_db
from handlers import (
    check_subscription,
    format_callback,
    format_command,
    get_admin_handler,
    handle_quality_selection,
    handle_url,
    help_command,
    history_command,
    history_pagination_callback,
    restore_command,
    start_command,
    subscription_callback_handler,
)

# Import the ban check middleware
from handlers.middleware import check_user_ban
from scripts.cookie_refresher import CookieRefresher

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

    # Initialize scheduler only if AUTO_REFRESH_COOKIES is enabled
    if settings.AUTO_REFRESH_COOKIES:
        scheduler = AsyncIOScheduler()
        refresher = CookieRefresher()

        # Schedule refreshing every minute
        scheduler.add_job(refresher.refresh, "interval", minutes=1)
        scheduler.start()
        logger.info(
            "Scheduler started for cookie refreshing (AUTO_REFRESH_COOKIES=true)"
        )
    else:
        logger.info(
            "Automatic cookie refreshing is disabled (AUTO_REFRESH_COOKIES=false). Use /refresh to refresh manually."
        )


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

    # Add middleware handlers (HIGHEST PRIORITY - group -2 and -1)
    # Ban check runs FIRST (group -2)
    application.add_handler(TypeHandler(Update, check_user_ban), group=-2)

    # Subscription check runs SECOND (group -1)
    application.add_handler(TypeHandler(Update, check_subscription), group=-1)

    # Add command handlers (group 0 - default)
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("history", history_command))
    application.add_handler(CommandHandler("restore", restore_command))
    application.add_handler(CommandHandler("format", format_command))

    # Admin Handler
    application.add_handler(get_admin_handler())

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
    application.add_handler(
        CallbackQueryHandler(handle_quality_selection, pattern="^back_to_type_")
    )
    application.add_handler(
        CallbackQueryHandler(handle_quality_selection, pattern="^convert_audio_")
    )
    application.add_handler(
        CallbackQueryHandler(handle_quality_selection, pattern="^retry_")
    )

    # Add callback query handler for history pagination
    application.add_handler(
        CallbackQueryHandler(history_pagination_callback, pattern="^history_page_")
    )

    application.add_handler(
        CallbackQueryHandler(handle_quality_selection, pattern="^cancel_processing_")
    )

    # Add callback query handler for subscription check
    application.add_handler(
        CallbackQueryHandler(
            subscription_callback_handler, pattern="^check_subscription$"
        )
    )
    application.add_handler(
        CallbackQueryHandler(format_callback, pattern="^set_format_")
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
