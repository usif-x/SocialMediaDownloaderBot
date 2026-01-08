import logging
import asyncio
from datetime import datetime, timedelta
from typing import List, Union

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Message, MessageOriginChannel
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)
from sqlalchemy import func

from config import settings
from database.database import SessionLocal
from database.models import User, Download, MandatoryChannel, BotSetting
from scripts.cookie_refresher import CookieRefresher

logger = logging.getLogger(__name__)

# Conversation states
SELECTING_ACTION, BROADCAST_MESSAGE, ADD_CHANNEL_ID, ADD_CHANNEL_LINK = range(4)

# Admin Panel Home
async def admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point for admin panel"""
    user_id = update.effective_user.id
    if user_id != settings.ADMIN_ID:
        return

    keyboard = [
        [
            InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast"),
            InlineKeyboardButton("📊 Analytics", callback_data="admin_analytics"),
        ],
        [
            InlineKeyboardButton("📢 Managed Channels", callback_data="admin_channels"),
            InlineKeyboardButton("🔔 Notifications", callback_data="admin_notifications"),
        ],
        [
            InlineKeyboardButton("🍪 Refresh Cookies", callback_data="admin_refresh_cookies"),
        ],
        [
            InlineKeyboardButton("❌ Close", callback_data="admin_close"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    msg_text = "🔒 **Admin Control Panel**\n\nSelect an action:"

    if update.callback_query:
        await update.callback_query.message.edit_text(msg_text, reply_markup=reply_markup, parse_mode="Markdown")
        return SELECTING_ACTION
    else:
        await update.message.reply_text(msg_text, reply_markup=reply_markup, parse_mode="Markdown")
        return SELECTING_ACTION

async def admin_close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Close admin panel"""
    query = update.callback_query
    await query.answer()
    await query.message.delete()
    return ConversationHandler.END

# --- Analytics ---
async def admin_analytics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show bot analytics"""
    query = update.callback_query
    await query.answer()

    db = SessionLocal()
    try:
        total_users = db.query(User).count()
        total_downloads = db.query(Download).count()
        
        # New users today
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        new_users_today = db.query(User).filter(User.created_at >= today).count()
        
        # Active users (last 24h)
        active_24h = db.query(User).filter(User.last_activity >= datetime.utcnow() - timedelta(days=1)).count()
        
        downloads_today = db.query(Download).filter(Download.created_at >= today).count()

        text = (
            "📊 **Bot Analytics**\n\n"
            f"👥 Total Users: `{total_users}`\n"
            f"🆕 New Users (Today): `{new_users_today}`\n"
            f"⚡ Active Users (24h): `{active_24h}`\n\n"
            f"📥 Total Downloads: `{total_downloads}`\n"
            f"📥 Downloads (Today): `{downloads_today}`"
        )
        
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="admin_home")]]
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return SELECTING_ACTION

    finally:
        db.close()

# --- Broadcast ---
async def start_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ask for broadcast message"""
    query = update.callback_query
    await query.answer()
    
    text = (
        "📢 **Create Broadcast**\n\n"
        "Send the message you want to broadcast.\n"
        "You can send text, photo, video, etc.\n\n"
        "Send /cancel to cancel."
    )
    await query.message.edit_text(text, parse_mode="Markdown")
    return BROADCAST_MESSAGE

async def process_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process and send the broadcast"""
    message = update.message
    user_id = update.effective_user.id
    
    if user_id != settings.ADMIN_ID:
        return ConversationHandler.END

    status_msg = await message.reply_text("🚀 Starting broadcast...")
    
    db = SessionLocal()
    users = db.query(User).all()
    count = 0
    blocked = 0
    failed = 0
    
    try:
        for user in users:
            try:
                # Use copy_message to support all media types and captions properly
                await context.bot.copy_message(
                    chat_id=user.telegram_id,
                    from_chat_id=message.chat_id,
                    message_id=message.message_id
                )
                count += 1
            except Exception as e:
                # Very basic error handling
                error_str = str(e).lower()
                if "blocked" in error_str or "user is deactivated" in error_str:
                    blocked += 1
                else:
                    failed += 1
                    logger.warning(f"Failed to broadcast to {user.telegram_id}: {e}")
                
            # Sleep briefly to avoid hitting limits
            if count % 20 == 0:
                await asyncio.sleep(1)
                
    finally:
        db.close()
        
    report = (
        "✅ **Broadcast Completed**\n\n"
        f"📨 Sent: `{count}`\n"
        f"🚫 Blocked: `{blocked}`\n"
        f"❌ Failed: `{failed}`"
    )
    
    await status_msg.edit_text(report, parse_mode="Markdown")
    
    # Return to main menu logic would be tricky here because we sent a new message.
    # We can just send a new menu.
    keyboard = [[InlineKeyboardButton("🔙 Back to Panel", callback_data="admin_home")]]
    await message.reply_text("Admin Panel:", reply_markup=InlineKeyboardMarkup(keyboard))
    
    return SELECTING_ACTION # Ideally revert to state, but since we are in a message handler, we need to guide user back

async def cancel_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel current action"""
    await update.message.reply_text("❌ Action cancelled.")
    return await admin_start(update, context)

# --- Channels Management ---
async def list_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List managed channels"""
    query = update.callback_query
    await query.answer()
    
    db = SessionLocal()
    try:
        channels = db.query(MandatoryChannel).all()
        
        keyboard = []
        if channels:
            for ch in channels:
                keyboard.append([
                    InlineKeyboardButton(f"🗑️ {ch.channel_name or ch.channel_id}", callback_data=f"del_channel_{ch.id}")
                ])
        
        keyboard.append([InlineKeyboardButton("➕ Add Channel", callback_data="add_channel")])
        keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="admin_home")])
        
        text = "📢 **Managed Channels**\n\nUsers must subscribe to these channels to use the bot.\nClick to remove."
        if not channels:
            text += "\n\n_(No channels added yet)_"
            
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return SELECTING_ACTION
    finally:
        db.close()

async def delete_channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Delete a channel"""
    query = update.callback_query
    # data format: del_channel_{id}
    channel_db_id = int(query.data.split("_")[-1])
    
    db = SessionLocal()
    try:
        channel = db.query(MandatoryChannel).filter(MandatoryChannel.id == channel_db_id).first()
        if channel:
            db.delete(channel)
            db.commit()
            await query.answer("✅ Channel removed!", show_alert=True)
        else:
            await query.answer("❌ Channel not found!", show_alert=True)
            
        return await list_channels(update, context)
    finally:
        db.close()

async def add_channel_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ask for channel ID"""
    query = update.callback_query
    await query.answer()
    
    text = (
        "➕ **Add Mandatory Channel**\n\n"
        "Please forward a message from the channel OR send the Channel ID (e.g. -100123456789).\n"
        "Make sure I am an ADMIN in that channel first!"
    )
    
    await query.message.edit_text(text, parse_mode="Markdown")
    return ADD_CHANNEL_ID

async def process_channel_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process channel ID input"""
    user_id = update.effective_user.id
    if user_id != settings.ADMIN_ID:
        return ConversationHandler.END

    if update.message.forward_origin and isinstance(update.message.forward_origin, MessageOriginChannel):
        channel_id = update.message.forward_origin.chat.id
        channel_title = update.message.forward_origin.chat.title
        username = update.message.forward_origin.chat.username
    else:
        try:
            channel_id = int(update.message.text.strip())
            channel_title = f"Channel {channel_id}"
            username = None
        except ValueError:
            await update.message.reply_text("❌ Invalid ID. Please forward a message or send a valid numeric ID.")
            return ADD_CHANNEL_ID

    # Verify bot access
    try:
        chat = await context.bot.get_chat(channel_id)
        channel_title = chat.title
        
        # Save temp data
        context.user_data['new_channel_id'] = channel_id
        context.user_data['new_channel_title'] = channel_title
        context.user_data['new_channel_username'] = chat.username
        
        await update.message.reply_text(
            f"✅ Found channel: **{channel_title}**\n\n"
            "Now send the Invite Link for this channel (users will use this to join).\n"
            "Send 'auto' to use the public username link (if public).",
            parse_mode="Markdown"
        )
        return ADD_CHANNEL_LINK
        
    except Exception as e:
        await update.message.reply_text(f"❌ Error accessing channel: {e}\n\nMake sure I am a member/admin there!")
        return ADD_CHANNEL_ID

async def process_channel_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Save the channel with link"""
    link = update.message.text.strip()
    
    if link.lower() == 'auto':
        username = context.user_data.get('new_channel_username')
        if username:
            link = f"https://t.me/{username}"
        else:
            await update.message.reply_text("❌ Channel is private and no link provided. Please send an invite link.")
            return ADD_CHANNEL_LINK
            
    # Save to DB
    db = SessionLocal()
    try:
        # Check duplicate
        exists = db.query(MandatoryChannel).filter(MandatoryChannel.channel_id == context.user_data['new_channel_id']).first()
        if exists:
            await update.message.reply_text("⚠️ This channel is already in the list.")
            return ConversationHandler.END # Or back to menu
            
        new_ch = MandatoryChannel(
            channel_id=context.user_data['new_channel_id'],
            channel_name=context.user_data['new_channel_title'],
            channel_link=link
        )
        db.add(new_ch)
        db.commit()
        
        await update.message.reply_text("✅ Channel added successfully!")
        
        # Show menu again
        keyboard = [[InlineKeyboardButton("🔙 Back to Panel", callback_data="admin_home")]]
        await update.message.reply_text("Admin Panel:", reply_markup=InlineKeyboardMarkup(keyboard))
        return SELECTING_ACTION
        
    finally:
        db.close()


# --- Cookies ---
async def admin_refresh_cookies_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback wrapper for cookie refresher"""
    query = update.callback_query
    await query.answer("🍪 Refreshing cookies...")
    
    # We can reuse the logic from previous handlers/admin.py or just call the script logic
    await query.message.edit_text("🍪 Refreshing cookies... Please wait.")
    
    try:
        refresher = CookieRefresher()
        success = await refresher.refresh()
        
        text = "✅ Cookies refreshed successfully!" if success else "❌ Failed to refresh cookies."
        
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="admin_home")]]
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        
    except Exception as e:
        logger.error(f"Error refreshing cookies: {e}")
        text = f"❌ Error: {str(e)}"
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="admin_home")]]
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    
    return SELECTING_ACTION


# --- Notification Settings ---
async def admin_notifications(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show notification settings"""
    query = update.callback_query
    await query.answer()

    db = SessionLocal()
    try:
        # Get current setting
        setting = db.query(BotSetting).filter(BotSetting.key == "notify_new_user").first()
        is_enabled = setting.value == "true" if setting else False
        
        status_text = "✅ Enabled" if is_enabled else "❌ Disabled"
        toggle_data = "disable_notify" if is_enabled else "enable_notify"
        
        text = (
            "🔔 **Notification Settings**\n\n"
            f"**Notify New User:** {status_text}\n\n"
            "When enabled, you will receive a message whenever a new user starts the bot."
        )
        
        keyboard = [
            [InlineKeyboardButton(f"Turn {'Off' if is_enabled else 'On'}", callback_data=f"notify_toggle_{toggle_data}")],
            [InlineKeyboardButton("🔙 Back", callback_data="admin_home")]
        ]
        
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return SELECTING_ACTION
    finally:
        db.close()

async def toggle_notify_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle notification setting"""
    query = update.callback_query
    # data format: notify_toggle_enable_notify or notify_toggle_disable_notify
    action = query.data.split("_")[-2] # enable or disable
    
    db = SessionLocal()
    try:
        setting = db.query(BotSetting).filter(BotSetting.key == "notify_new_user").first()
        if not setting:
            setting = BotSetting(key="notify_new_user", value="false")
            db.add(setting)
        
        if action == "enable":
            setting.value = "true"
            msg = "✅ Notification Enabled!"
        else:
            setting.value = "false"
            msg = "❌ Notification Disabled!"
            
        db.commit()
        await query.answer(msg, show_alert=True)
        return await admin_notifications(update, context)
        
    finally:
        db.close()


# --- Setup Handler ---
def get_admin_handler() -> ConversationHandler:
    """Return the admin conversation handler"""
    return ConversationHandler(
        entry_points=[CommandHandler("admin", admin_start)],
        states={
            SELECTING_ACTION: [
                CallbackQueryHandler(start_broadcast, pattern="^admin_broadcast$"),
                CallbackQueryHandler(admin_analytics, pattern="^admin_analytics$"),
                CallbackQueryHandler(list_channels, pattern="^admin_channels$"),
                CallbackQueryHandler(admin_refresh_cookies_callback, pattern="^admin_refresh_cookies$"),
                CallbackQueryHandler(admin_notifications, pattern="^admin_notifications$"),
                CallbackQueryHandler(toggle_notify_callback, pattern="^notify_toggle_"),
                CallbackQueryHandler(delete_channel_callback, pattern="^del_channel_"),
                CallbackQueryHandler(add_channel_start, pattern="^add_channel$"),
                CallbackQueryHandler(admin_start, pattern="^admin_home$"),
                CallbackQueryHandler(admin_close, pattern="^admin_close$"),
            ],
            BROADCAST_MESSAGE: [
                MessageHandler(filters.ALL & ~filters.COMMAND, process_broadcast),
            ],
            ADD_CHANNEL_ID: [
                MessageHandler(filters.ALL & ~filters.COMMAND, process_channel_id)
            ],
            ADD_CHANNEL_LINK: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_channel_link)
            ]
        },
        fallbacks=[
            CommandHandler("cancel", cancel_action),
            CommandHandler("admin", admin_start), # restart if they type /admin
            CallbackQueryHandler(admin_start, pattern="^admin_home$"),
        ],
    )
