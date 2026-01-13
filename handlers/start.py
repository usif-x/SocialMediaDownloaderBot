from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes

from config import settings
from database import BotSetting, User, get_db
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
            db.commit()  # Commit to save user and get count correctly

            # Check for notification setting
            setting = (
                db.query(BotSetting).filter(BotSetting.key == "notify_new_user").first()
            )
            if setting and setting.value == "true":
                total_users = db.query(User).count()

                # Send notification to admin
                try:
                    admin_msg = (
                        "🆕 **New User Joined!**\n\n"
                        f"👤 **Name:** {user.full_name}\n"
                        f"📧 **Username:** @{user.username if user.username else 'N/A'}\n"
                        f"🆔 **ID:** `{user.id}`\n\n"
                        f"📊 **Total Users:** `{total_users}`"
                    )
                    await context.bot.send_message(
                        chat_id=settings.ADMIN_ID, text=admin_msg, parse_mode="Markdown"
                    )
                except Exception as notify_error:
                    import logging

                    logging.getLogger(__name__).error(
                        f"Failed to send new user notification: {notify_error}"
                    )

        else:
            db_user.username = user.username
            db_user.first_name = user.first_name
            db_user.last_name = user.last_name
            db_user.last_activity = datetime.utcnow()

            # Handle Quota Reset (Daily)
            now = datetime.utcnow()
            if db_user.daily_quota is None:
                db_user.daily_quota = 10
            if db_user.used_quota is None:
                db_user.used_quota = 0
            if db_user.last_quota_reset is None:
                db_user.last_quota_reset = now
            elif db_user.last_quota_reset.date() < now.date():
                db_user.used_quota = 0
                db_user.last_quota_reset = now

            db.commit()

        # Get values for message
        used_quota = db_user.used_quota
        total_quota = db_user.daily_quota

    except Exception as e:
        import logging

        logging.getLogger(__name__).error(f"Database error in start_command: {e}")
        used_quota = 0
        total_quota = 10
    finally:
        try:
            db.close()
        except:
            pass

    welcome_message = (
        f"👋 Welcome {user.first_name}!\n\n"
        f"🎥 I'm a SocialMedia Downloader Bot.\n\n"
        f"🔍 Type `@A6KllBot [search terms]` to search for YouTube videos\n"
        f"OR\n"
        f"🔗 Send me content link to get started 🚀\n\n"
        f"ℹ️ For help, use /help\n\n"
        f"📊 **Your Daily Quota:** `{used_quota}/{total_quota}`\n\n"
        f"👨‍💻 Developer: @YousseifMuhammed"
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
        "/restore\\_ID - Restore a previous download\n"
        "/format - Set your preferred download format\n\n"
        "*How to download:*\n"
        "1️⃣ Send me a YouTube, Instagram, TikTok or Facebook video link\n"
        "2️⃣ Wait while I fetch content information\n"
        "3️⃣ Choose format type (Video/Audio) if available\n"
        "4️⃣ Select quality (if available) and download starts!\n\n"
        "*How to search for videos on YouTube:*\n"
        "🔍 Type `@A6KllBot [search terms]` in chat\n"
        "Example: `@A6KllBot Amr Diab`\n"
        "📱 Tap on any result and result link will send automatically\n\n"
        "*Supported Platforms:*\n"
        "✅ YouTube (Videos, Shorts)\n"
        "✅ Instagram (Videos Only)\n"
        "✅ TikTok (Videos Only)\n"
        "✅ Facebook (Videos Only)\n"
        "✅ Soundcloud\n\n"
        "Need more help? Just try sending a link!"
    )

    await update.message.reply_text(help_message, parse_mode="Markdown")
