"""
Add this to your handlers/__init__.py or create a new file handlers/middleware.py
"""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from database.database import SessionLocal
from database.models import User

logger = logging.getLogger(__name__)


async def check_user_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Middleware to check if user is banned
    This should run before any other handler
    """
    # Skip for callback queries without message or non-user updates
    if not update.effective_user:
        return

    # Allow admin to bypass
    from config import settings

    if update.effective_user.id == settings.ADMIN_ID:
        return

    # Skip for certain admin commands
    if update.message and update.message.text:
        if update.message.text.startswith("/admin"):
            return

    user_id = update.effective_user.id
    db = SessionLocal()

    try:
        user = db.query(User).filter(User.telegram_id == user_id).first()

        # If user exists and is banned
        if user and user.is_banned:
            ban_message = (
                "🚫 **You are banned from using this bot.**\n\n"
                "If you believe this is a mistake, please contact the administrator."
            )

            if update.message:
                await update.message.reply_text(ban_message, parse_mode="Markdown")
            elif update.callback_query:
                await update.callback_query.answer(
                    "🚫 You are banned from using this bot!", show_alert=True
                )
                # Also try to send a message
                try:
                    await update.callback_query.message.reply_text(
                        ban_message, parse_mode="Markdown"
                    )
                except:
                    pass

            # Stop propagation - don't process any other handlers
            from telegram.ext import ApplicationHandlerStop

            raise ApplicationHandlerStop

    except Exception as e:
        if "ApplicationHandlerStop" in str(type(e)):
            raise  # Re-raise to stop handler chain
        logger.error(f"Error checking user ban status: {e}")
    finally:
        db.close()
