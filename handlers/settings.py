import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from database import User, get_db

logger = logging.getLogger(__name__)

async def format_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /format command"""
    user = update.effective_user
    db = get_db()
    try:
        db_user = db.query(User).filter(User.telegram_id == user.id).first()
        if not db_user:
            await update.message.reply_text("❌ Please use /start first.")
            return

        current_format = db_user.preferred_format or "video"
        
        message = (
            "⚙️ *Download Settings*\n\n"
            f"Current preference: *{current_format.capitalize()}*\n\n"
            "Select your preferred format for downloads when specific formats can't be fetched:"
        )

        keyboard = [
            [
                InlineKeyboardButton(
                    "🎬 Video" + (" ✅" if current_format == "video" else ""),
                    callback_data="set_format_video"
                ),
                InlineKeyboardButton(
                    "🎵 Audio" + (" ✅" if current_format == "audio" else ""),
                    callback_data="set_format_audio"
                )
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(message, reply_markup=reply_markup, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error in format_command: {e}")
        await update.message.reply_text("❌ An error occurred. Please try again.")
    finally:
        db.close()

async def format_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle format selection callback"""
    query = update.callback_query
    user = update.effective_user
    data = query.data
    
    # Extract format from callback data
    new_format = data.split("_")[-1]  # video or audio
    
    db = get_db()
    try:
        db_user = db.query(User).filter(User.telegram_id == user.id).first()
        if not db_user:
            await query.answer("❌ User not found.")
            return

        db_user.preferred_format = new_format
        db.commit()

        await query.answer(f"✅ Preference updated to {new_format.capitalize()}")
        
        # Update message with new selection
        message = (
            "⚙️ *Download Settings*\n\n"
            f"Current preference: *{new_format.capitalize()}*\n\n"
            "Select your preferred format for downloads when specific formats can't be fetched:"
        )

        keyboard = [
            [
                InlineKeyboardButton(
                    "🎬 Video" + (" ✅" if new_format == "video" else ""),
                    callback_data="set_format_video"
                ),
                InlineKeyboardButton(
                    "🎵 Audio" + (" ✅" if new_format == "audio" else ""),
                    callback_data="set_format_audio"
                )
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error in format_callback: {e}")
        await query.answer("❌ Failed to update preference.")
    finally:
        db.close()
