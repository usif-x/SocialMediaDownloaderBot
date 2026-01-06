import logging
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from telegram.helpers import escape_markdown

from database import Download, User, get_db


async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /history command - show user's download history"""
    logger = logging.getLogger(__name__)
    user = update.effective_user

    db = get_db()
    try:
        # Get user from database
        db_user = db.query(User).filter(User.telegram_id == user.id).first()

        if not db_user:
            await update.message.reply_text(
                "❌ User not found. Please use /start first."
            )
            return

        # Get user's completed downloads (last 20)
        downloads = (
            db.query(Download)
            .filter(Download.user_id == db_user.id, Download.status == "completed")
            .order_by(Download.completed_at.desc())
            .limit(20)
            .all()
        )

        if not downloads:
            await update.message.reply_text(
                "📭 No download history found.\n\nSend me a video link to start downloading!"
            )
            return

        # Build history message
        history_text = "📜 *Your Download History*\n\n"

        for i, dl in enumerate(downloads, 1):
            # Format date
            date_str = (
                dl.completed_at.strftime("%Y-%m-%d %H:%M")
                if dl.completed_at
                else "Unknown"
            )

            # Format file size
            if dl.file_size:
                if dl.file_size >= 1024 * 1024:
                    size_str = f"{dl.file_size / (1024 * 1024):.1f}MB"
                else:
                    size_str = f"{dl.file_size / 1024:.1f}KB"
            else:
                size_str = "Unknown"

            # Format type icon
            type_icon = "🎬"
            if dl.format_type == "audio":
                type_icon = "🎵"
            elif dl.format_type == "image":
                type_icon = "🖼"

            # Truncate title if too long
            title = (
                dl.title[:40] + "..."
                if dl.title and len(dl.title) > 40
                else (dl.title or "Unknown")
            )

            # Escape markdown special characters properly using telegram helper
            title_escaped = escape_markdown(title, version=2)
            date_escaped = escape_markdown(date_str, version=2)
            size_escaped = escape_markdown(size_str, version=2)

            history_text += (
                f"{i}\\. {type_icon} *{title_escaped}*\n"
                f"   📅 {date_escaped} \\| 💾 {size_escaped}\n"
                f"   🔗 /restore\\_{dl.id}\n\n"
            )

        history_text += "💡 _Use /restore\\_ID to get the file again_"

        await update.message.reply_text(history_text, parse_mode="MarkdownV2")

    except Exception as e:
        logger.error(f"Error in history_command: {e}", exc_info=True)
        await update.message.reply_text(
            "❌ An error occurred while fetching history. Please try again."
        )
    finally:
        try:
            db.close()
        except:
            pass


async def restore_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /restore_ID command - resend a previously downloaded file"""
    logger = logging.getLogger(__name__)
    user = update.effective_user

    # Parse download ID from command
    message_text = update.message.text

    # Handle both /restore_123 and /restore 123 formats
    try:
        if "_" in message_text:
            download_id = int(message_text.split("_")[1])
        elif context.args:
            download_id = int(context.args[0])
        else:
            await update.message.reply_text(
                "❌ Please provide a download ID.\n\n"
                "Usage: /restore_ID or /restore ID\n"
                "Example: /restore_123\n\n"
                "Use /history to see your downloads."
            )
            return
    except (ValueError, IndexError):
        await update.message.reply_text(
            "❌ Invalid download ID.\n\n"
            "Usage: /restore_ID\n"
            "Example: /restore_123\n\n"
            "Use /history to see your downloads."
        )
        return

    db = get_db()
    try:
        # Get user from database
        db_user = db.query(User).filter(User.telegram_id == user.id).first()

        if not db_user:
            await update.message.reply_text(
                "❌ User not found. Please use /start first."
            )
            return

        # Get the download record
        download = (
            db.query(Download)
            .filter(
                Download.id == download_id,
                Download.user_id == db_user.id,
                Download.status == "completed",
            )
            .first()
        )

        if not download:
            await update.message.reply_text(
                "❌ Download not found or not accessible.\n\n"
                "Use /history to see your available downloads."
            )
            return

        # Check if we have file_id to resend
        if not download.file_id:
            await update.message.reply_text(
                "❌ Sorry, this file can’t be restored.\n"
                "The file exceeds the 50 MB limit and cannot be restored.\n\n"
                f"🔗 Original URL: {download.url}\n"
                "You can send this URL again to download."
            )
            return

        # Send the file using file_id (instant, no re-download needed)
        processing_msg = await update.message.reply_text("🔄 Restoring file...")

        caption = f"🎬 {download.title or 'Media'}\n\n💾 Quality: {download.quality or 'Unknown'}"

        try:
            if download.format_type == "audio":
                await context.bot.send_audio(
                    chat_id=user.id,
                    audio=download.file_id,
                    caption=caption,
                )
            elif download.format_type == "image":
                await context.bot.send_photo(
                    chat_id=user.id,
                    photo=download.file_id,
                    caption=f"🖼 {download.title or 'Image'}",
                )
            else:
                await context.bot.send_video(
                    chat_id=user.id,
                    video=download.file_id,
                    caption=caption,
                    supports_streaming=True,
                )

            await processing_msg.delete()

        except Exception as send_error:
            logger.error(f"Error sending restored file: {send_error}")
            await processing_msg.edit_text(
                "❌ Failed to restore file. The file may have expired.\n\n"
                f"🔗 Original URL: {download.url}\n"
                "You can send this URL again to download."
            )

    except Exception as e:
        logger.error(f"Error in restore_command: {e}", exc_info=True)
        await update.message.reply_text("❌ An error occurred. Please try again.")
    finally:
        try:
            db.close()
        except:
            pass
