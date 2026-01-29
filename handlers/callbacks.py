import ast
import asyncio
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from database import Download, User, get_db
from handlers.download import download_and_send_video, safe_edit_message
from utils import VideoDownloader, redis_client


def escape_markdown(text: str) -> str:
    """Escape special Markdown characters"""
    if not text:
        return text
    # Escape characters that have special meaning in Markdown
    escape_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in escape_chars:
        text = text.replace(char, f'\\{char}')
    return text


def safe_markdown_text(text: str, parse_mode: str = "Markdown") -> str:
    """Safely prepare text for Markdown parsing"""
    if parse_mode not in ["Markdown", "MarkdownV2"]:
        return text
    
    # For Markdown, we need to ensure entities are properly closed
    # Simple approach: remove any unclosed Markdown entities
    import re
    
    # Remove any standalone asterisks, underscores, etc. that might cause issues
    # This is a simplified approach - in production you'd want more robust parsing
    text = re.sub(r'(?<!\\)\*(?!\*)', '\\*', text)  # Escape single asterisks
    text = re.sub(r'(?<!\\)_(?!_)', '\\_', text)    # Escape single underscores
    text = re.sub(r'(?<!\\)`(?!`)', '\\`', text)    # Escape single backticks
    
    # Ensure Markdown entities are balanced
    # Count opening and closing markers
    asterisk_pairs = min(text.count('*') // 2, text.count('*') % 2)
    if asterisk_pairs * 2 < text.count('*'):
        # Unbalanced asterisks, escape all of them
        text = text.replace('*', '\\*')
    
    underscore_pairs = min(text.count('_') // 2, text.count('_') % 2)
    if underscore_pairs * 2 < text.count('_'):
        # Unbalanced underscores, escape all of them
        text = text.replace('_', '\\_')
    
    return text


async def handle_quality_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle format type and quality selection from inline keyboard"""
    logger = logging.getLogger(__name__)
    query = update.callback_query
    await query.answer()

    # Parse callback data
    callback_data = query.data.split("_")

    action = callback_data[0]  # 'type' or 'quality'

    # Handle format type selection (video/audio)
    if action == "type":
        if len(callback_data) < 3:
            await safe_edit_message(
                query.message, "❌ Invalid selection. Please try again."
            )
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
            await safe_edit_message(
                query.message, "❌ Session expired. Please send the link again."
            )
            return

        # Show quality selection for chosen format type
        formats = video_info.get(f"{format_type}_formats", [])

        if not formats:
            await safe_edit_message(
                query.message, "❌ No formats available for this type."
            )
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

        # Add Back button to return to type selection
        keyboard.append(
            [
                InlineKeyboardButton(
                    "⬅️ Back", callback_data=f"back_to_type_{download_id}"
                )
            ]
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
        original_text = query.message.text or query.message.caption or ""
        
        # Clean the original text to fix any Markdown issues
        if original_text:
            # First 100 chars for debugging
            logger.info(f"Original text preview: {original_text[:100]}...")
            # Clean Markdown
            original_text = safe_markdown_text(original_text, "Markdown")
        
        if original_text:
            # Add format type selection info
            updated_text = f"{original_text}\n\n✅ *Selected Format:* {icon} {format_name}\n\n{icon} *Select Quality:*"
        else:
            updated_text = f"{icon} *Select Quality:*"
        
        # Log for debugging
        logger.info(f"Format type selection: format_type={format_type}, format_name={format_name}, updated_text_length={len(updated_text)}")

        # Try to edit message with photo if it exists
        try:
            if query.message.photo:
                try:
                    # Try without Markdown first to avoid parsing errors
                    await query.message.edit_caption(
                        caption=updated_text,
                        reply_markup=reply_markup,
                        parse_mode=None,  # Disable Markdown to avoid parsing errors
                    )
                except Exception as e:
                    logger.warning(f"Failed to edit caption: {e}")
                    await safe_edit_message(
                        query.message,
                        updated_text,
                        reply_markup=reply_markup,
                        parse_mode=None,
                    )
            else:
                try:
                    await safe_edit_message(
                        query.message,
                        updated_text,
                        reply_markup=reply_markup,
                        parse_mode=None,  # Disable Markdown to avoid parsing errors
                    )
                except Exception as e:
                    logger.warning(f"Failed to edit message: {e}")
                    await safe_edit_message(
                        query.message,
                        updated_text,
                        reply_markup=reply_markup,
                        parse_mode=None,
                    )
        except Exception as e:
            logger.error(f"Failed to edit message completely: {e}")
            # As last resort, send a new message
            try:
                await context.bot.send_message(
                    chat_id=update.effective_user.id,
                    text=updated_text,
                    reply_markup=reply_markup,
                    parse_mode=None,
                )
            except Exception as final_e:
                logger.error(f"Failed to send new message: {final_e}")

    # Handle quality selection
    elif action == "quality":
        if len(callback_data) < 5:
            logger.error(f"Invalid callback data length: {callback_data}")
            await safe_edit_message(
                query.message, "❌ Invalid selection. Please try again."
            )
            return

        # Parse more robustly: download_id is last part, format_id is second-last,
        # quality may contain underscores so join the middle parts
        format_type = callback_data[1]  # 'video', 'audio', or 'image'
        if len(callback_data) < 4:
            logger.error(f"Invalid callback data for quality selection: {callback_data}")
            await safe_edit_message(
                query.message, "❌ Invalid selection. Please try again."
            )
            return

        try:
            download_id = int(callback_data[-1])
            format_id_raw = callback_data[-2]
            format_id = format_id_raw if format_id_raw != "none" else None
            # quality is everything between index 2 and -2
            quality = (
                "_".join(callback_data[2:-2])
                if len(callback_data) > 4
                else callback_data[2]
            )
            user_id = update.effective_user.id
            
            logger.info(f"Quality selection parsed: format_type={format_type}, quality={quality}, format_id={format_id}, download_id={download_id}")
        except Exception as e:
            logger.error(f"Failed to parse callback data {callback_data}: {e}")
            await safe_edit_message(
                query.message, "❌ Invalid selection data. Please try again."
            )
            return

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
        
        # Log for debugging
        logger = logging.getLogger(__name__)
        logger.info(f"Quality selection: format_type={format_type}, quality={quality}, current_text_length={len(current_text)}")

        # Update with selection info - escape any Markdown special characters in quality
        # Escape underscores, asterisks, brackets, etc. that might be in quality string
        escaped_quality = quality.replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace(']', '\\]').replace('(', '\\(').replace(')', '\\)')
        updated_text = f"{current_text}\n\n✅ *Selected Quality:* {icon} {escaped_quality}\n⬇️ *Starting download...*"
        
        # Check if message is too long (Telegram limit is 4096 characters)
        if len(updated_text) > 4000:
            logger.warning(f"Message too long ({len(updated_text)} chars), truncating...")
            # Keep only the last part if too long
            updated_text = f"✅ *Selected Quality:* {icon} {escaped_quality}\n⬇️ *Starting download...*"

        # Try to edit caption if message has photo, otherwise edit text
        try:
            # First check if we can access the message
            if not query.message:
                logger.error("Query message is None, cannot edit")
                raise Exception("Message is None")
                
            if query.message.photo:
                try:
                    await query.message.edit_caption(
                        caption=updated_text,
                        parse_mode=None,  # Disable Markdown to avoid parsing errors
                    )
                except Exception as e:
                    logger.warning(f"Failed to edit caption: {e}")
                    await safe_edit_message(
                        query.message,
                        updated_text,
                        parse_mode=None,
                    )
            else:
                await safe_edit_message(
                    query.message,
                    updated_text,
                    parse_mode=None,  # Disable Markdown to avoid parsing errors
                )
        except Exception as e:
            logger.error(f"Failed to update selection message: {e}")
            # As last resort, send a new message
            try:
                await context.bot.send_message(
                    chat_id=update.effective_user.id,
                    text=updated_text,
                    parse_mode=None,
                )
            except Exception as final_e:
                logger.error(f"Failed to send new selection message: {final_e}")

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
        retry_type = callback_data[1] if len(callback_data) > 1 else None

        # Handle retry_yt_{video_id} - YouTube video ID in callback
        if retry_type == "yt" and len(callback_data) >= 3:
            video_id = callback_data[2]
            url = f"https://www.youtube.com/watch?v={video_id}"
        # Handle retry_ig_{video_id} - Instagram reel/post ID in callback
        elif retry_type == "ig" and len(callback_data) >= 3:
            video_id = callback_data[2]
            url = f"https://www.instagram.com/reel/{video_id}"
        # Handle retry_ctx_{user_id} - fallback to context storage
        elif retry_type == "ctx" and len(callback_data) >= 3:
            retry_user_id = int(callback_data[2])
            url = context.user_data.get(f"retry_url_{retry_user_id}")
        else:
            # Legacy format: retry_{user_id}
            retry_user_id = query.from_user.id
            url = context.user_data.get(f"retry_url_{retry_user_id}")

        if not url:
            await query.answer("❌ Session expired. Please send the link again.")
            await safe_edit_message(
                query.message, "❌ Session expired. Please send the link again."
            )
            return

        await query.answer("🔄 Retrying...")

        # Import download handler
        from handlers.download import handle_url

        # Retry the download by calling handle_url
        await handle_url(update, context, url=url, existing_message=query.message)

    # Handle cancel download
    elif action in ("cancel_processing", "cancel"):
        # Support callback_data formats:
        # - "cancel_processing_{download_id}" -> split -> ['cancel', 'processing', '{id}']
        # - "cancel_processing_{id}" (legacy) -> ['cancel_processing', '{id}']
        if action == "cancel_processing":
            # legacy format: ['cancel_processing', '{id}']
            if len(callback_data) < 2:
                await query.answer("❌ Invalid request")
                return
            id_part = callback_data[1]
        else:
            # new format: ['cancel', 'processing', '{id}']
            if len(callback_data) < 3:
                await query.answer("❌ Invalid request")
                return
            id_part = callback_data[2]

        try:
            download_id = int(id_part)
        except Exception:
            await query.answer("❌ Invalid download id")
            return

        db = get_db()
        try:
            download = db.query(Download).filter(Download.id == download_id).first()
            if not download:
                await query.answer("❌ Download not found")
                await safe_edit_message(query.message, "❌ Download not found.")
                return

            if download.status != "processing":
                await query.answer("❌ Not processing")
                await safe_edit_message(
                    query.message, "❌ This download is not processing."
                )
                return

            # Mark download as cancelled/failed and clear user's downloading flag
            download.status = "failed"
            download.error_message = "Cancelled by user"
            user_obj = db.query(User).filter(User.id == download.user_id).first()
            if user_obj:
                user_obj.is_downloading = False
            db.commit()

            await query.answer("✅ Download cancelled")
            await safe_edit_message(
                query.message,
                "✅ Download has been cancelled. You can send a new link.",
            )

        except Exception as e:
            logging.getLogger(__name__).error(
                f"Error cancelling download: {e}", exc_info=True
            )
            await query.answer("❌ Failed to cancel")
            await safe_edit_message(query.message, "❌ Failed to cancel the download.")
        finally:
            db.close()

    # Handle back to type selection
    elif action == "back":
        if (
            len(callback_data) < 4
            or callback_data[1] != "to"
            or callback_data[2] != "type"
        ):
            await query.answer("❌ Invalid action.")
            return

        download_id = int(callback_data[3])
        user_id = update.effective_user.id

        # Get video info from cache
        video_info_str = redis_client.get_video_info(user_id)
        if video_info_str:
            video_info = ast.literal_eval(video_info_str)
        elif f"video_info_{download_id}" in context.user_data:
            video_info = context.user_data[f"video_info_{download_id}"]
        else:
            await safe_edit_message(
                query.message, "❌ Session expired. Please send the link again."
            )
            return

        # Rebuild type selection keyboard
        keyboard = []

        if video_info.get("video_formats"):
            keyboard.append(
                [
                    InlineKeyboardButton(
                        "🎬 Video", callback_data=f"type_video_{download_id}"
                    )
                ]
            )

        if video_info.get("audio_formats"):
            keyboard.append(
                [
                    InlineKeyboardButton(
                        "🎵 Audio", callback_data=f"type_audio_{download_id}"
                    )
                ]
            )

        if video_info.get("image_formats"):
            keyboard.append(
                [
                    InlineKeyboardButton(
                        "🖼 Image", callback_data=f"type_image_{download_id}"
                    )
                ]
            )

        reply_markup = InlineKeyboardMarkup(keyboard)

        # Rebuild original message
        has_video = video_info.get("has_video", False)
        has_image = video_info.get("has_image", False)

        from utils import format_duration, format_views

        if has_image and not has_video:
            info_message = (
                f"🖼 *Image Information*\n\n"
                f"📝 *Title:* {video_info['title']}\n"
                f"👤 *Uploader:* {video_info['uploader']}\n"
                f"🌐 *Platform:* {video_info['platform']}\n"
                f"👁 *Views:* {format_views(video_info['views'])}\n\n"
                f"🎯 *Select Format:*"
            )
        else:
            info_message = (
                f"📹 *Video Information*\n\n"
                f"📝 *Title:* {video_info['title']}\n"
                f"👤 *Uploader:* {video_info['uploader']}\n"
                f"🌐 *Platform:* {video_info['platform']}\n"
                f"🕔 *Duration:* {format_duration(video_info['duration'])}\n"
                f"👁 *Views:* {format_views(video_info['views'])}\n\n"
                f"🎯 *Select Format Type:*"
            )

        # Edit message back to type selection
        if query.message.photo:
            try:
                await query.message.edit_caption(
                    caption=info_message,
                    reply_markup=reply_markup,
                    parse_mode="Markdown",
                )
            except:
                await safe_edit_message(
                    query.message,
                    info_message,
                    reply_markup=reply_markup,
                    parse_mode="Markdown",
                )
        else:
            await safe_edit_message(
                query.message,
                info_message,
                reply_markup=reply_markup,
                parse_mode="Markdown",
            )

    # Handle convert to audio
    elif (
        action == "convert"
    ):  # convert_audio_{download_id} -> split -> ['convert', 'audio', '{id}']
        if len(callback_data) < 3 or callback_data[1] != "audio":
            await query.answer("❌ Invalid request")
            return

        download_id = int(callback_data[2])
        user_id = update.effective_user.id

        await query.answer("🎵 Converting to audio...")

        # Send a new message for the conversion process
        processing_msg = await context.bot.send_message(
            chat_id=user_id, text="🔄 Fetching video info for conversion..."
        )

        db = get_db()
        try:
            download = db.query(Download).filter(Download.id == download_id).first()
            if not download:
                await processing_msg.edit_text("❌ Download record not found.")
                return

            url = download.url

            # Re-fetch info
            downloader = VideoDownloader()
            loop = asyncio.get_event_loop()
            video_info = await loop.run_in_executor(
                None, lambda: downloader.get_video_info(url)
            )

            if not video_info:
                await processing_msg.edit_text("❌ Failed to fetch video info.")
                return

            # Update cache
            redis_client.set_video_info(user_id, video_info)
            context.user_data[f"video_info_{download_id}"] = video_info

            # Update info in DB if changed
            download.title = video_info["title"]
            db.commit()

            # Start download process for audio
            # We pass processing_msg so it updates that message
            await download_and_send_video(
                update,
                context,
                download_id,
                "audio",
                "Best",
                "bestaudio",
                user_id,
                processing_msg,
            )

        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"Error in convert to audio: {e}", exc_info=True)
            await safe_edit_message(
                processing_msg, "❌ An error occurred during conversion."
            )
        finally:
            db.close()
