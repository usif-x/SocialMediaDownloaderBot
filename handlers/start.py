from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes

from database import User, get_db
from utils import VideoDownloader


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user = update.effective_user

    # Save or update user in database
    db = get_db()
    try:
        db_user = db.query(User).filter(User.telegram_id == user.id).first()

        if not db_user:
            db_user = User(
                telegram_id=user.id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name,
                language_code=user.language_code,
            )
            db.add(db_user)
        else:
            db_user.username = user.username
            db_user.first_name = user.first_name
            db_user.last_name = user.last_name
            db_user.last_activity = datetime.utcnow()

        db.commit()
    except Exception as e:
        import logging

        logging.getLogger(__name__).error(f"Database error in start_command: {e}")
    finally:
        try:
            db.close()
        except:
            pass

    welcome_message = (
        f"👋 Welcome {user.first_name}!\n\n"
        f"🎥 I'm a YouTube Downloader Bot. I can help you download videos and audio from YouTube.\n\n"
        f"🎯 *How to use:*\n"
        f"1️⃣ Send me a YouTube video link\n"
        f"2️⃣ I'll fetch the video information\n"
        f"3️⃣ Choose format type (Video/Audio)\n"
        f"4️⃣ Select your preferred quality\n"
        f"5️⃣ Get your media!\n\n"
        f"🔍 *Need to search for videos?*\n"
        f"Type `@vid [search terms]` in any chat to search for videos\n"
        f"Example: `@vid python tutorial`\n"
        f"Then send me the video link to download!\n\n"
        f"📋 *Available Commands:*\n"
        f"/help - View all commands and help\n"
        f"/history - View your download history\n"
        f"/restore\\_ID - Restore previous downloads\n\n"
        f"Just send me a YouTube link! 🚀\n"
    )

    await update.message.reply_text(welcome_message, parse_mode="Markdown")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    help_message = (
        "🆘 *Help & Commands*\n\n"
        "*Available Commands:*\n"
        "/start - Start the bot\n"
        "/help - Show this help message\n"
        "/history - View your download history\n"
        "/restore\\_ID - Restore a previous download\n\n"
        "*How to download:*\n"
        "1️⃣ Send me a YouTube video URL\n"
        "2️⃣ Wait while I fetch video information\n"
        "3️⃣ Choose format type (Video/Audio)\n"
        "4️⃣ Select quality and download starts!\n\n"
        "*How to search for videos:*\n"
        "🔍 Type `@vid [search terms]` in any chat\n"
        "Example: `@vid python programming tutorial`\n"
        "📱 Tap on a result, then send me that video link\n\n"
        "*Supported Platform:*\n"
        "✅ YouTube (videos, shorts, playlists)\n\n"
        "*Tips:*\n"
        "💡 Use @vid in any chat to search for videos\n"
        "💡 Send direct YouTube links to download\n"
        "💡 Use /history to see and restore past downloads\n\n"
        "Need more help? Just try sending a YouTube link!"
    )

    await update.message.reply_text(help_message, parse_mode="Markdown")
