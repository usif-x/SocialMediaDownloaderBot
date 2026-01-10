import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Union

from sqlalchemy import func
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    MessageOriginChannel,
    Update,
)
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from config import settings
from database.database import SessionLocal
from database.models import BotSetting, Download, MandatoryChannel, User
from scripts.cookie_refresher import CookieRefresher

logger = logging.getLogger(__name__)

# Conversation states
(
    SELECTING_ACTION,
    BROADCAST_MESSAGE,
    ADD_CHANNEL_ID,
    ADD_CHANNEL_LINK,
    SEARCH_USER_QUOTA,
    UPDATE_USER_QUOTA,
    SET_GLOBAL_QUOTA,
    RESET_USER_QUOTA,
    BAN_USER_INPUT,
    UNBAN_USER_INPUT,
) = range(10)


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
            InlineKeyboardButton("📢 Channels", callback_data="admin_channels"),
            InlineKeyboardButton(
                "🔔 Notifications", callback_data="admin_notifications"
            ),
        ],
        [
            InlineKeyboardButton(
                "🍪 Refresh Cookies", callback_data="admin_refresh_cookies"
            ),
            InlineKeyboardButton("📊 Quotas", callback_data="admin_quotas"),
        ],
        [
            InlineKeyboardButton("🚫 User Control", callback_data="admin_user_control"),
            InlineKeyboardButton("📈 Stats", callback_data="admin_detailed_stats"),
        ],
        [
            InlineKeyboardButton("❌ Close", callback_data="admin_close"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    msg_text = "🔒 **Admin Control Panel**\n\nSelect an action:"

    if update.callback_query:
        await update.callback_query.message.edit_text(
            msg_text, reply_markup=reply_markup, parse_mode="Markdown"
        )
        return SELECTING_ACTION
    else:
        await update.message.reply_text(
            msg_text, reply_markup=reply_markup, parse_mode="Markdown"
        )
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
        active_24h = (
            db.query(User)
            .filter(User.last_activity >= datetime.utcnow() - timedelta(days=1))
            .count()
        )

        downloads_today = (
            db.query(Download).filter(Download.created_at >= today).count()
        )

        text = (
            "📊 **Bot Analytics**\n\n"
            f"👥 Total Users: `{total_users}`\n"
            f"🆕 New Users (Today): `{new_users_today}`\n"
            f"⚡ Active Users (24h): `{active_24h}`\n\n"
            f"📥 Total Downloads: `{total_downloads}`\n"
            f"📥 Downloads (Today): `{downloads_today}`"
        )

        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="admin_home")]]
        await query.message.edit_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
        )
        return SELECTING_ACTION

    finally:
        db.close()


# --- Detailed Stats ---
async def admin_detailed_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show detailed statistics"""
    query = update.callback_query
    await query.answer()

    db = SessionLocal()
    try:
        # Time periods
        now = datetime.utcnow()
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_ago = now - timedelta(days=7)
        month_ago = now - timedelta(days=30)

        # User stats
        users_week = db.query(User).filter(User.created_at >= week_ago).count()
        users_month = db.query(User).filter(User.created_at >= month_ago).count()

        # Download stats
        downloads_week = (
            db.query(Download).filter(Download.created_at >= week_ago).count()
        )
        downloads_month = (
            db.query(Download).filter(Download.created_at >= month_ago).count()
        )

        # Top users by downloads
        top_users = (
            db.query(
                User.first_name, User.username, func.count(Download.id).label("count")
            )
            .join(Download)
            .group_by(User.id)
            .order_by(func.count(Download.id).desc())
            .limit(5)
            .all()
        )

        top_users_text = (
            "\n".join(
                [
                    f"{i+1}. {u[0] or 'Unknown'} (@{u[1] or 'N/A'}): {u[2]} downloads"
                    for i, u in enumerate(top_users)
                ]
            )
            if top_users
            else "_No data_"
        )

        text = (
            "📈 **Detailed Statistics**\n\n"
            "**User Growth:**\n"
            f"📅 Last 7 days: `{users_week}`\n"
            f"📅 Last 30 days: `{users_month}`\n\n"
            "**Download Activity:**\n"
            f"📅 Last 7 days: `{downloads_week}`\n"
            f"📅 Last 30 days: `{downloads_month}`\n\n"
            f"**Top Users:**\n{top_users_text}"
        )

        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="admin_home")]]
        await query.message.edit_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
        )
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
        "✅ Supports: text, photo, video, documents, buttons\n"
        "📌 You'll be able to choose whether to pin it\n\n"
        "Send /cancel to cancel."
    )
    await query.message.edit_text(text, parse_mode="Markdown")
    return BROADCAST_MESSAGE


async def process_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process and send the broadcast with pin option"""
    message = update.message
    user_id = update.effective_user.id

    if user_id != settings.ADMIN_ID:
        return ConversationHandler.END

    # Store the message for later use
    context.user_data["broadcast_message"] = message

    # Ask if user wants to pin the message
    keyboard = [
        [
            InlineKeyboardButton("📌 Pin Message", callback_data="broadcast_pin_yes"),
            InlineKeyboardButton("📄 No Pin", callback_data="broadcast_pin_no"),
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data="admin_home")],
    ]

    await message.reply_text(
        "📌 Do you want to pin this message for all users?",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return SELECTING_ACTION


async def execute_broadcast(
    update: Update, context: ContextTypes.DEFAULT_TYPE, should_pin: bool = False
):
    """Execute the actual broadcast"""
    query = update.callback_query
    await query.answer()

    message = context.user_data.get("broadcast_message")
    if not message:
        await query.message.edit_text(
            "❌ Broadcast message not found. Please try again."
        )
        return SELECTING_ACTION

    status_msg = await query.message.edit_text("🚀 Starting broadcast...")

    db = SessionLocal()
    users = db.query(User).all()
    count = 0
    blocked = 0
    failed = 0

    try:
        for user in users:
            try:
                # Send message with proper handling of all content types and buttons
                sent_message = None
                reply_markup = message.reply_markup

                if message.text and not (
                    message.photo or message.video or message.document or message.audio
                ):
                    sent_message = await context.bot.send_message(
                        chat_id=user.telegram_id,
                        text=message.text,
                        entities=message.entities,
                        reply_markup=reply_markup,
                        parse_mode=None,  # entities already provided
                    )
                elif message.photo:
                    sent_message = await context.bot.send_photo(
                        chat_id=user.telegram_id,
                        photo=message.photo[-1].file_id,
                        caption=message.caption,
                        caption_entities=message.caption_entities,
                        reply_markup=reply_markup,
                    )
                elif message.video:
                    sent_message = await context.bot.send_video(
                        chat_id=user.telegram_id,
                        video=message.video.file_id,
                        caption=message.caption,
                        caption_entities=message.caption_entities,
                        reply_markup=reply_markup,
                    )
                elif message.audio:
                    sent_message = await context.bot.send_audio(
                        chat_id=user.telegram_id,
                        audio=message.audio.file_id,
                        caption=message.caption,
                        caption_entities=message.caption_entities,
                        reply_markup=reply_markup,
                    )
                elif message.document:
                    sent_message = await context.bot.send_document(
                        chat_id=user.telegram_id,
                        document=message.document.file_id,
                        caption=message.caption,
                        caption_entities=message.caption_entities,
                        reply_markup=reply_markup,
                    )
                elif message.animation:
                    sent_message = await context.bot.send_animation(
                        chat_id=user.telegram_id,
                        animation=message.animation.file_id,
                        caption=message.caption,
                        caption_entities=message.caption_entities,
                        reply_markup=reply_markup,
                    )
                elif message.voice:
                    sent_message = await context.bot.send_voice(
                        chat_id=user.telegram_id,
                        voice=message.voice.file_id,
                        caption=message.caption,
                        caption_entities=message.caption_entities,
                        reply_markup=reply_markup,
                    )

                # Pin the message if requested
                if should_pin and sent_message:
                    try:
                        await context.bot.pin_chat_message(
                            chat_id=user.telegram_id,
                            message_id=sent_message.message_id,
                            disable_notification=True,
                        )
                    except Exception as pin_error:
                        logger.warning(
                            f"Could not pin message for {user.telegram_id}: {pin_error}"
                        )

                count += 1

            except Exception as e:
                error_str = str(e).lower()
                if (
                    "blocked" in error_str
                    or "user is deactivated" in error_str
                    or "chat not found" in error_str
                ):
                    blocked += 1
                else:
                    failed += 1
                    logger.warning(f"Failed to broadcast to {user.telegram_id}: {e}")

            # Rate limiting
            if count % 20 == 0:
                await asyncio.sleep(1)

    finally:
        db.close()

    pin_status = "📌 Pinned" if should_pin else "📄 Not pinned"
    report = (
        "✅ **Broadcast Completed**\n\n"
        f"📨 Sent: `{count}`\n"
        f"🚫 Blocked: `{blocked}`\n"
        f"❌ Failed: `{failed}`\n"
        f"{pin_status}"
    )

    await status_msg.edit_text(report, parse_mode="Markdown")

    # Clean up
    context.user_data.pop("broadcast_message", None)

    keyboard = [[InlineKeyboardButton("🔙 Back to Panel", callback_data="admin_home")]]
    await status_msg.reply_text(
        "Admin Panel:", reply_markup=InlineKeyboardMarkup(keyboard)
    )

    return SELECTING_ACTION


async def broadcast_with_pin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Broadcast with pin"""
    return await execute_broadcast(update, context, should_pin=True)


async def broadcast_without_pin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Broadcast without pin"""
    return await execute_broadcast(update, context, should_pin=False)


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
                keyboard.append(
                    [
                        InlineKeyboardButton(
                            f"🗑️ {ch.channel_name or ch.channel_id}",
                            callback_data=f"del_channel_{ch.id}",
                        )
                    ]
                )

        keyboard.append(
            [InlineKeyboardButton("➕ Add Channel", callback_data="add_channel")]
        )
        keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="admin_home")])

        text = "📢 **Managed Channels**\n\nUsers must subscribe to these channels to use the bot.\nClick to remove."
        if not channels:
            text += "\n\n_(No channels added yet)_"

        await query.message.edit_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
        )
        return SELECTING_ACTION
    finally:
        db.close()


async def delete_channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Delete a channel"""
    query = update.callback_query
    channel_db_id = int(query.data.split("_")[-1])

    db = SessionLocal()
    try:
        channel = (
            db.query(MandatoryChannel)
            .filter(MandatoryChannel.id == channel_db_id)
            .first()
        )
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

    if update.message.forward_origin and isinstance(
        update.message.forward_origin, MessageOriginChannel
    ):
        channel_id = update.message.forward_origin.chat.id
        channel_title = update.message.forward_origin.chat.title
        username = update.message.forward_origin.chat.username
    else:
        try:
            channel_id = int(update.message.text.strip())
            channel_title = f"Channel {channel_id}"
            username = None
        except ValueError:
            await update.message.reply_text(
                "❌ Invalid ID. Please forward a message or send a valid numeric ID."
            )
            return ADD_CHANNEL_ID

    # Verify bot access
    try:
        chat = await context.bot.get_chat(channel_id)
        channel_title = chat.title

        # Save temp data
        context.user_data["new_channel_id"] = channel_id
        context.user_data["new_channel_title"] = channel_title
        context.user_data["new_channel_username"] = chat.username

        await update.message.reply_text(
            f"✅ Found channel: **{channel_title}**\n\n"
            "Now send the Invite Link for this channel (users will use this to join).\n"
            "Send 'auto' to use the public username link (if public).",
            parse_mode="Markdown",
        )
        return ADD_CHANNEL_LINK

    except Exception as e:
        await update.message.reply_text(
            f"❌ Error accessing channel: {e}\n\nMake sure I am a member/admin there!"
        )
        return ADD_CHANNEL_ID


async def process_channel_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Save the channel with link"""
    link = update.message.text.strip()

    if link.lower() == "auto":
        username = context.user_data.get("new_channel_username")
        if username:
            link = f"https://t.me/{username}"
        else:
            await update.message.reply_text(
                "❌ Channel is private and no link provided. Please send an invite link."
            )
            return ADD_CHANNEL_LINK

    # Save to DB
    db = SessionLocal()
    try:
        # Check duplicate
        exists = (
            db.query(MandatoryChannel)
            .filter(MandatoryChannel.channel_id == context.user_data["new_channel_id"])
            .first()
        )
        if exists:
            await update.message.reply_text("⚠️ This channel is already in the list.")
            return ConversationHandler.END

        new_ch = MandatoryChannel(
            channel_id=context.user_data["new_channel_id"],
            channel_name=context.user_data["new_channel_title"],
            channel_link=link,
        )
        db.add(new_ch)
        db.commit()

        await update.message.reply_text("✅ Channel added successfully!")

        keyboard = [
            [InlineKeyboardButton("🔙 Back to Panel", callback_data="admin_home")]
        ]
        await update.message.reply_text(
            "Admin Panel:", reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return SELECTING_ACTION

    finally:
        db.close()


# --- Cookies ---
async def admin_refresh_cookies_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """Callback wrapper for cookie refresher"""
    query = update.callback_query
    await query.answer("🍪 Refreshing cookies...")

    await query.message.edit_text("🍪 Refreshing cookies... Please wait.")

    try:
        refresher = CookieRefresher()
        success = await refresher.refresh()

        text = (
            "✅ Cookies refreshed successfully!"
            if success
            else "❌ Failed to refresh cookies."
        )

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
        setting = (
            db.query(BotSetting).filter(BotSetting.key == "notify_new_user").first()
        )
        is_enabled = setting.value == "true" if setting else False

        status_text = "✅ Enabled" if is_enabled else "❌ Disabled"
        toggle_data = "disable_notify" if is_enabled else "enable_notify"

        text = (
            "🔔 **Notification Settings**\n\n"
            f"**Notify New User:** {status_text}\n\n"
            "When enabled, you will receive a message whenever a new user starts the bot."
        )

        keyboard = [
            [
                InlineKeyboardButton(
                    f"Turn {'Off' if is_enabled else 'On'}",
                    callback_data=f"notify_toggle_{toggle_data}",
                )
            ],
            [InlineKeyboardButton("🔙 Back", callback_data="admin_home")],
        ]

        await query.message.edit_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
        )
        return SELECTING_ACTION
    finally:
        db.close()


async def toggle_notify_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle notification setting"""
    query = update.callback_query
    action = query.data.split("_")[-2]

    db = SessionLocal()
    try:
        setting = (
            db.query(BotSetting).filter(BotSetting.key == "notify_new_user").first()
        )
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


# --- User Control ---
async def admin_user_control(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User control menu"""
    query = update.callback_query
    await query.answer()

    text = "🚫 **User Control**\n\nSelect an action:"
    keyboard = [
        [InlineKeyboardButton("🚫 Ban User", callback_data="admin_ban_user")],
        [InlineKeyboardButton("✅ Unban User", callback_data="admin_unban_user")],
        [InlineKeyboardButton("📋 Banned Users", callback_data="admin_list_banned")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_home")],
    ]
    await query.message.edit_text(
        text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
    )
    return SELECTING_ACTION


async def admin_ban_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start ban user process"""
    query = update.callback_query
    await query.answer()

    text = "🚫 **Ban User**\n\nSend the Telegram User ID to ban:"
    await query.message.edit_text(text, parse_mode="Markdown")
    return BAN_USER_INPUT


async def process_ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ban a user"""
    user_id_text = update.message.text.strip()

    if not user_id_text.isdigit():
        await update.message.reply_text("❌ Please send a valid numeric Telegram ID.")
        return BAN_USER_INPUT

    tg_id = int(user_id_text)
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == tg_id).first()
        if not user:
            await update.message.reply_text(
                f"❌ User with ID `{tg_id}` not found in database.",
                parse_mode="Markdown",
            )
            return BAN_USER_INPUT

        user.is_banned = True
        db.commit()

        await update.message.reply_text(
            f"✅ User `{tg_id}` has been banned!",
            parse_mode="Markdown",
        )

        keyboard = [
            [InlineKeyboardButton("🔙 Back to Panel", callback_data="admin_home")]
        ]
        await update.message.reply_text(
            "Admin Panel:", reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return SELECTING_ACTION
    finally:
        db.close()


async def admin_unban_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start unban user process"""
    query = update.callback_query
    await query.answer()

    text = "✅ **Unban User**\n\nSend the Telegram User ID to unban:"
    await query.message.edit_text(text, parse_mode="Markdown")
    return UNBAN_USER_INPUT


async def process_unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unban a user"""
    user_id_text = update.message.text.strip()

    if not user_id_text.isdigit():
        await update.message.reply_text("❌ Please send a valid numeric Telegram ID.")
        return UNBAN_USER_INPUT

    tg_id = int(user_id_text)
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == tg_id).first()
        if not user:
            await update.message.reply_text(
                f"❌ User with ID `{tg_id}` not found in database.",
                parse_mode="Markdown",
            )
            return UNBAN_USER_INPUT

        user.is_banned = False
        db.commit()

        await update.message.reply_text(
            f"✅ User `{tg_id}` has been unbanned!",
            parse_mode="Markdown",
        )

        keyboard = [
            [InlineKeyboardButton("🔙 Back to Panel", callback_data="admin_home")]
        ]
        await update.message.reply_text(
            "Admin Panel:", reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return SELECTING_ACTION
    finally:
        db.close()


async def admin_list_banned(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all banned users"""
    query = update.callback_query
    await query.answer()

    db = SessionLocal()
    try:
        banned_users = db.query(User).filter(User.is_banned == True).all()

        if not banned_users:
            text = "📋 **Banned Users**\n\n_No banned users_"
        else:
            text = "📋 **Banned Users**\n\n"
            for user in banned_users[:20]:  # Limit to 20
                name = (
                    f"{user.first_name or ''} {user.last_name or ''}".strip()
                    or "Unknown"
                )
                text += (
                    f"• {name} (@{user.username or 'N/A'}) - ID: `{user.telegram_id}`\n"
                )

            if len(banned_users) > 20:
                text += f"\n_...and {len(banned_users) - 20} more_"

        keyboard = [
            [InlineKeyboardButton("🔙 Back", callback_data="admin_user_control")]
        ]
        await query.message.edit_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
        )
        return SELECTING_ACTION
    finally:
        db.close()


# --- Quota Management ---
async def admin_quotas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Quota management menu"""
    query = update.callback_query
    await query.answer()

    text = "📊 **Quota Management**\n\nSelect an action:"
    keyboard = [
        [InlineKeyboardButton("🔍 Search User", callback_data="admin_quota_search")],
        [
            InlineKeyboardButton(
                "🌎 Set Global Quota", callback_data="admin_global_quota"
            )
        ],
        [
            InlineKeyboardButton(
                "🔄 Reset All Quotas", callback_data="admin_reset_all_quotas"
            )
        ],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_home")],
    ]
    await query.message.edit_text(
        text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
    )
    return SELECTING_ACTION


async def admin_quota_search_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ask for user ID to manage quota"""
    query = update.callback_query
    await query.answer()

    text = (
        "🔍 **Search User Quota**\n\n"
        "Send the Telegram User ID of the user you want to manage."
    )
    await query.message.edit_text(text, parse_mode="Markdown")
    return SEARCH_USER_QUOTA


async def admin_global_quota_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ask for new global quota"""
    query = update.callback_query
    await query.answer()

    text = (
        "🌎 **Set Global Quota**\n\n"
        "Send the **new daily quota** number for ALL users."
    )
    await query.message.edit_text(text, parse_mode="Markdown")
    return SET_GLOBAL_QUOTA


async def admin_reset_all_quotas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reset all users' used quota to 0"""
    query = update.callback_query
    await query.answer()

    db = SessionLocal()
    try:
        updated_count = db.query(User).update({User.used_quota: 0})
        db.commit()

        await query.answer(f"✅ Reset {updated_count} users' quotas!", show_alert=True)
        return await admin_quotas(update, context)
    except Exception as e:
        logger.error(f"Error resetting quotas: {e}")
        await query.answer(f"❌ Failed to reset quotas", show_alert=True)
        return await admin_quotas(update, context)
    finally:
        db.close()


async def process_global_quota_update(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """Update quota for all users"""
    new_quota_text = update.message.text.strip()

    if not new_quota_text.isdigit():
        await update.message.reply_text("❌ Please send a valid number.")
        return SET_GLOBAL_QUOTA

    new_quota = int(new_quota_text)
    db = SessionLocal()
    try:
        updated_count = db.query(User).update({User.daily_quota: new_quota})
        db.commit()

        await update.message.reply_text(
            f"✅ Global quota updated successfully!\n\n"
            f"📈 New Daily Quota: `{new_quota}`\n"
            f"👥 Users Updated: `{updated_count}`",
            parse_mode="Markdown",
        )

        keyboard = [
            [InlineKeyboardButton("🔙 Back to Panel", callback_data="admin_home")]
        ]
        await update.message.reply_text(
            "Admin Panel:", reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return SELECTING_ACTION
    except Exception as e:
        logger.error(f"Error updating global quota: {e}")
        await update.message.reply_text(f"❌ Failed to update global quota: {e}")
        return ConversationHandler.END
    finally:
        db.close()


async def process_user_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Search for user by ID"""
    user_id_text = update.message.text.strip()

    if not user_id_text.isdigit():
        await update.message.reply_text("❌ Please send a valid numeric Telegram ID.")
        return SEARCH_USER_QUOTA

    tg_id = int(user_id_text)
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == tg_id).first()
        if not user:
            await update.message.reply_text(
                f"❌ User with ID `{tg_id}` not found in database.",
                parse_mode="Markdown",
            )
            return SEARCH_USER_QUOTA

        context.user_data["manage_quota_user_id"] = user.id

        text = (
            f"👤 **User Found:** {user.first_name or ''} {user.last_name or ''} (@{user.username or 'N/A'})\n"
            f"🆔 ID: `{user.telegram_id}`\n\n"
            f"📈 **Current Quota:** `{user.used_quota}/{user.daily_quota}`\n\n"
            "Send the **new daily quota** number for this user."
        )
        await update.message.reply_text(text, parse_mode="Markdown")
        return UPDATE_USER_QUOTA
    finally:
        db.close()


async def process_quota_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Update user quota"""
    new_quota_text = update.message.text.strip()

    if not new_quota_text.isdigit():
        await update.message.reply_text("❌ Please send a valid number.")
        return UPDATE_USER_QUOTA

    new_quota = int(new_quota_text)
    user_db_id = context.user_data.get("manage_quota_user_id")

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_db_id).first()
        if user:
            old_quota = user.daily_quota
            user.daily_quota = new_quota
            db.commit()

            await update.message.reply_text(
                f"✅ Quota updated for user `{user.telegram_id}`!\n"
                f"Previous: `{old_quota}`\n"
                f"New: `{new_quota}`",
                parse_mode="Markdown",
            )

            keyboard = [
                [InlineKeyboardButton("🔙 Back to Panel", callback_data="admin_home")]
            ]
            await update.message.reply_text(
                "Admin Panel:", reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return SELECTING_ACTION
        else:
            await update.message.reply_text("❌ Error: User record lost.")
            return ConversationHandler.END
    finally:
        db.close()


def get_admin_handler() -> ConversationHandler:
    """Return the admin conversation handler"""
    return ConversationHandler(
        entry_points=[CommandHandler("admin", admin_start)],
        states={
            SELECTING_ACTION: [
                CallbackQueryHandler(start_broadcast, pattern="^admin_broadcast$"),
                CallbackQueryHandler(admin_analytics, pattern="^admin_analytics$"),
                CallbackQueryHandler(
                    admin_detailed_stats, pattern="^admin_detailed_stats$"
                ),
                CallbackQueryHandler(list_channels, pattern="^admin_channels$"),
                CallbackQueryHandler(
                    admin_refresh_cookies_callback, pattern="^admin_refresh_cookies$"
                ),
                CallbackQueryHandler(
                    admin_notifications, pattern="^admin_notifications$"
                ),
                CallbackQueryHandler(admin_quotas, pattern="^admin_quotas$"),
                CallbackQueryHandler(
                    admin_quota_search_start, pattern="^admin_quota_search$"
                ),
                CallbackQueryHandler(
                    admin_global_quota_start, pattern="^admin_global_quota$"
                ),
                CallbackQueryHandler(
                    admin_reset_all_quotas, pattern="^admin_reset_all_quotas$"
                ),
                CallbackQueryHandler(
                    admin_user_control, pattern="^admin_user_control$"
                ),
                CallbackQueryHandler(admin_ban_user_start, pattern="^admin_ban_user$"),
                CallbackQueryHandler(
                    admin_unban_user_start, pattern="^admin_unban_user$"
                ),
                CallbackQueryHandler(admin_list_banned, pattern="^admin_list_banned$"),
                CallbackQueryHandler(toggle_notify_callback, pattern="^notify_toggle_"),
                CallbackQueryHandler(delete_channel_callback, pattern="^del_channel_"),
                CallbackQueryHandler(add_channel_start, pattern="^add_channel$"),
                CallbackQueryHandler(broadcast_with_pin, pattern="^broadcast_pin_yes$"),
                CallbackQueryHandler(
                    broadcast_without_pin, pattern="^broadcast_pin_no$"
                ),
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
            ],
            SEARCH_USER_QUOTA: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_user_search)
            ],
            UPDATE_USER_QUOTA: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_quota_update)
            ],
            SET_GLOBAL_QUOTA: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND, process_global_quota_update
                )
            ],
            BAN_USER_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_ban_user)
            ],
            UNBAN_USER_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_unban_user)
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_action),
            CommandHandler("admin", admin_start),
            CallbackQueryHandler(admin_start, pattern="^admin_home$"),
        ],
    )
