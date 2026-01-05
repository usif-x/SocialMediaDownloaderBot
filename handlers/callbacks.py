import ast

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from handlers.download import download_and_send_video
from utils import redis_client


async def handle_quality_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle format type and quality selection from inline keyboard"""
    query = update.callback_query
    await query.answer()

    # Parse callback data
    callback_data = query.data.split("_")

    action = callback_data[0]  # 'type' or 'quality'

    # Handle format type selection (video/audio)
    if action == "type":
        if len(callback_data) < 3:
            await query.edit_message_text("❌ Invalid selection. Please try again.")
            return

        format_type = callback_data[1]  # 'video', 'audio', or 'image'
        download_id = int(callback_data[2])
        user_id = update.effective_user.id

        # Get video info from cache
        video_info_str = redis_client.get_video_info(user_id)
        if video_info_str:
            video_info = ast.literal_eval(video_info_str)
        elif f"video_info_{download_id}" in context.user_data:
            video_info = context.user_data[f"video_info_{download_id}"]
        else:
            await query.edit_message_text(
                "❌ Session expired. Please send the link again."
            )
            return

        # Show quality selection for chosen format type
        formats = video_info.get(f"{format_type}_formats", [])

        if not formats:
            await query.edit_message_text("❌ No formats available for this type.")
            return

        # Create quality selection keyboard
        keyboard = []

        # Add "Best" option (not for images with only one option)
        if format_type != "image" or len(formats) > 1:
            keyboard.append(
                [
                    InlineKeyboardButton(
                        "⭐ Best Quality",
                        callback_data=f"quality_{format_type}_best_none_{download_id}",
                    )
                ]
            )

        # Add specific quality options
        for fmt in formats[:8]:  # Limit to 8 options
            quality_text = f"{fmt['quality']} ({fmt.get('ext', 'jpg').upper()})"
            format_id = fmt.get(
                "format_id", fmt.get("url", "none")[:50]
            )  # Use URL for images
            callback_data_str = (
                f"quality_{format_type}_{fmt['quality']}_{format_id}_{download_id}"
            )
            # For images, store the URL index instead of format_id
            if format_type == "image":
                idx = formats.index(fmt)
                callback_data_str = (
                    f"quality_{format_type}_{fmt['quality']}_{idx}_{download_id}"
                )
            keyboard.append(
                [InlineKeyboardButton(quality_text, callback_data=callback_data_str)]
            )

        reply_markup = InlineKeyboardMarkup(keyboard)
        icon = (
            "🎬"
            if format_type == "video"
            else ("🖼" if format_type == "image" else "🎵")
        )
        await query.edit_message_text(
            f"{query.message.text}\n\n{icon} *Select Quality:*",
            reply_markup=reply_markup,
            parse_mode="Markdown",
        )

    # Handle quality selection
    elif action == "quality":
        if len(callback_data) < 5:
            await query.edit_message_text("❌ Invalid selection. Please try again.")
            return

        format_type = callback_data[1]  # 'video', 'audio', or 'image'
        quality = callback_data[2]
        format_id = callback_data[3] if callback_data[3] != "none" else None
        download_id = int(callback_data[4])
        user_id = update.effective_user.id

        # Update message to show selection
        icon = (
            "🎬"
            if format_type == "video"
            else ("🖼" if format_type == "image" else "🎵")
        )
        await query.edit_message_text(
            f"{query.message.text_markdown}\n\n✅ Selected: {icon} {quality}\n⬇️ Starting download...",
            parse_mode="Markdown",
        )

        # Start download
        await download_and_send_video(
            update, context, download_id, format_type, quality, format_id, user_id
        )
    else:
        await query.edit_message_text("❌ Invalid action. Please try again.")
