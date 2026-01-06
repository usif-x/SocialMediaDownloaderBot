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
            # Get best quality file size estimate
            best_fmt = formats[0] if formats else None
            best_size_str = "~"
            if best_fmt:
                filesize = best_fmt.get("filesize") or best_fmt.get(
                    "filesize_approx", 0
                )
                if filesize:
                    if filesize > 1024 * 1024 * 1024:  # GB
                        best_size_str = f"{filesize / (1024 * 1024 * 1024):.1f}GB"
                    elif filesize > 1024 * 1024:  # MB
                        best_size_str = f"{filesize / (1024 * 1024):.1f}MB"
                    else:  # KB
                        best_size_str = f"{filesize / 1024:.0f}KB"

            keyboard.append(
                [
                    InlineKeyboardButton(
                        f"⭐ Auto (Recommended)",
                        callback_data=f"quality_{format_type}_best_none_{download_id}",
                    )
                ]
            )

        # Add specific quality options
        for fmt in formats[:8]:  # Limit to 8 options
            # Get file size (already combined filesize and filesize_approx in downloader)
            filesize = fmt.get("filesize", 0)

            # Format file size
            if filesize and filesize > 0:
                if filesize > 1024 * 1024 * 1024:  # GB
                    size_str = f"{filesize / (1024 * 1024 * 1024):.1f}GB"
                elif filesize > 1024 * 1024:  # MB
                    size_str = f"{filesize / (1024 * 1024):.1f}MB"
                else:  # KB
                    size_str = f"{filesize / 1024:.0f}KB"
            else:
                size_str = "~"

            # Check if can send (Telegram bot limit is 50MB)
            send_speed = (
                "🐆"
                if filesize and filesize <= 50 * 1024 * 1024
                else ("🐢" if filesize and filesize > 50 * 1024 * 1024 else "")
            )

            # Build quality text with size and status
            quality_text = f"{fmt['quality']} ({fmt.get('ext', 'jpg').upper()}) {size_str} {send_speed}".strip()

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
        format_name = (
            "Video"
            if format_type == "video"
            else ("Image" if format_type == "image" else "Audio")
        )

        # Update message with format type selection shown
        updated_text = query.message.text or query.message.caption
        if updated_text:
            # Add format type selection info
            updated_text = f"{updated_text}\n\n✅ *Selected Format:* {icon} {format_name}\n\n{icon} *Select Quality:*"
        else:
            updated_text = f"{icon} *Select Quality:*"

        # Try to edit message with photo if it exists
        if query.message.photo:
            try:
                await query.message.edit_caption(
                    caption=updated_text,
                    reply_markup=reply_markup,
                    parse_mode="Markdown",
                )
            except:
                await query.edit_message_text(
                    updated_text,
                    reply_markup=reply_markup,
                    parse_mode="Markdown",
                )
        else:
            await query.edit_message_text(
                updated_text,
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
        format_name = (
            "Video"
            if format_type == "video"
            else ("Image" if format_type == "image" else "Audio")
        )

        # Get current message text
        current_text = query.message.text or query.message.caption or ""

        # Update with selection info
        updated_text = f"{current_text}\n\n✅ *Selected Quality:* {icon} {quality}\n⬇️ *Starting download...*"

        # Try to edit caption if message has photo, otherwise edit text
        if query.message.photo:
            try:
                await query.message.edit_caption(
                    caption=updated_text,
                    parse_mode="Markdown",
                )
            except:
                await query.edit_message_text(
                    updated_text,
                    parse_mode="Markdown",
                )
        else:
            await query.edit_message_text(
                updated_text,
                parse_mode="Markdown",
            )

        # Start download
        await download_and_send_video(
            update,
            context,
            download_id,
            format_type,
            quality,
            format_id,
            user_id,
            query.message,
        )

    # Handle retry button
    elif action == "retry":
        # Get user ID from callback data
        retry_user_id = callback_data[1]

        # Get URL from context
        url = context.user_data.get(f"retry_url_{retry_user_id}")

        if not url:
            await query.answer("❌ Session expired. Please send the link again.")
            await query.edit_message_text(
                "❌ Session expired. Please send the link again."
            )
            return

        await query.answer("🔄 Retrying...")

        # Import download handler
        from handlers.download import handle_url

        # Retry the download by calling handle_url
        await handle_url(update, context, url=url, existing_message=query.message)
