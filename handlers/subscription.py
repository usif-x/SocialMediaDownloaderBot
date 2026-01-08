import logging
from typing import List, Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember
from telegram.ext import ContextTypes, ApplicationHandlerStop
from telegram.error import BadRequest

from config import settings
from database.database import SessionLocal
from database.models import MandatoryChannel, User

logger = logging.getLogger(__name__)

async def check_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Middleware to check if user is subscribed to mandatory channels.
    Stops handling if verification fails.
    """
    # Skip check for admins
    user_id = update.effective_user.id
    if user_id == settings.ADMIN_ID:
        return

    # Skip updates that don't have a user (like channel posts)
    if not update.effective_user:
        return

    # Get mandatory channels from DB
    db = SessionLocal()
    try:
        channels = db.query(MandatoryChannel).all()
        if not channels:
            return

        missing_channels = []
        for channel in channels:
            try:
                member_status = await context.bot.get_chat_member(
                    chat_id=channel.channel_id, 
                    user_id=user_id
                )
                
                # Check if user is member, creator, or administrator
                if member_status.status not in [
                    ChatMember.MEMBER, 
                    ChatMember.OWNER, 
                    ChatMember.ADMINISTRATOR
                ]:
                    missing_channels.append(channel)
            except BadRequest as e:
                logger.error(f"Error checking subscription for channel {channel.id}: {e}")
                # If bot cannot check (e.g. not admin in channel), skip this channel to avoid blocking users unfairly
                continue
            except Exception as e:
                logger.error(f"Unexpected error checking subscription: {e}")
                continue

        if missing_channels:
            # Build keyboard with join links
            keyboard = []
            for channel in missing_channels:
                btn_text = channel.channel_name or "Join Channel"
                link = channel.channel_link or f"https://t.me/c/{str(channel.channel_id).replace('-100', '')}/1"
                keyboard.append([InlineKeyboardButton(btn_text, url=link)])
            
            # Add "Check Subscription" button
            keyboard.append([InlineKeyboardButton("✅ Check Subscription", callback_data="check_subscription")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            message_text = (
                "⚠️ **Subscription Required**\n\n"
                "To use this bot, you must be subscribed to our sponsor channels.\n"
                "Please join the channels below and click 'Check Subscription'."
            )
            
            if update.callback_query:
                # If it's a callback query (e.g. they clicked "Check Subscription" again)
                if update.callback_query.data == "check_subscription":
                    await update.callback_query.answer("❌ You are still not fully subscribed!", show_alert=True)
                    # We don't edit the message to avoid spamming edits if they spam click
                else:
                    await update.callback_query.answer("⚠️ Please subscribe to channels first!", show_alert=True)
                    await update.callback_query.message.reply_text(message_text, reply_markup=reply_markup, parse_mode="Markdown")
            elif update.message:
                await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode="Markdown")
            
            # Stop further processing
            raise ApplicationHandlerStop

    finally:
        db.close()

async def subscription_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the 'Check Subscription' button click"""
    query = update.callback_query
    
    # This handler is only reached if check_subscription passed (meaning user IS subscribed)
    # OR if check_subscription raised Stop, this handler won't be reached in the normal flow.
    # HOWEVER, we need a specific handler to give positive feedback if they ARE now subscribed.
    
    # Actually, if check_subscription is a global TypeHandler/MessageHandler with high priority,
    # it raises Stop if NOT subscribed.
    # So if we reach here, and the data is "check_subscription", it means the user IS subscribed.
    
    if query.data == "check_subscription":
        await query.answer("✅ Thank you! You can now use the bot.")
        await query.message.edit_text("✅ **Subscription Verified!**\n\nYou can now use the bot. Send /start !", parse_mode="Markdown")

