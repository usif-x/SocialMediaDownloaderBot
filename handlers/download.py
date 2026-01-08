import ast
import asyncio
import logging
import os
import re
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from database import Download, User, get_db
from utils import (
    VideoDownloader,
    format_duration,
    format_views,
    redis_client,
    telethon_uploader,
)


async def handle_url(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    url: str = None,
    existing_message=None,
):
    """Handle video URL from user"""
    logger = logging.getLogger(__name__)
    user = update.effective_user

    # Use provided URL or get from message
    if url is None:
        url = update.message.text.strip()

    logger.info(f"User {user.id} sent URL: {url}")

    # Check if URL is from YouTube
    youtube_patterns = [
        r"(https?://)?(www\.)?(youtube\.com|youtu\.be)",
        r"(https?://)?(m\.)?youtube\.com",
        r"(https?://)?youtube\.com/shorts/",
    ]

    is_youtube = any(
        re.search(pattern, url, re.IGNORECASE) for pattern in youtube_patterns
    )

    if not is_youtube:
        await update.message.reply_text(
            "❌ This bot only supports YouTube links.\n\n"
            "Please send a valid YouTube video URL or use `@vid [search terms]` to search for videos.",
            parse_mode="Markdown",
        )
        return

    # Basic URL validation
    url_pattern = re.compile(
        r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+"
    )

    if not url_pattern.match(url):
        await update.message.reply_text(
            "❌ Invalid URL. Please send a valid video link."
        )
        return

    # Send processing message (or reuse existing one)
    if existing_message:
        processing_msg = existing_message
        await processing_msg.edit_text("🔄 Fetching video information...")
    else:
        processing_msg = await update.message.reply_text(
            "🔄 Fetching video information..."
        )

    # Get database session
    db = get_db()
    try:
        # Get user from database
        db_user = db.query(User).filter(User.telegram_id == user.id).first()

        if not db_user:
            await processing_msg.edit_text(
                "❌ User not found. Please use /start first."
            )
            return

        # Create download record
        download = Download(user_id=db_user.id, url=url, status="processing")
        db.add(download)
        db.commit()
        db.refresh(download)
        download_id = download.id  # Save ID before closing session

        # Extract video info in executor to not block other users
        downloader = VideoDownloader()
        loop = asyncio.get_event_loop()
        video_info = await loop.run_in_executor(
            None, lambda: downloader.get_video_info(url)
        )

        if not video_info:
            download.status = "failed"
            download.error_message = "Failed to extract video information"
            db.commit()

            # Extract YouTube video ID from URL for retry
            video_id = None
            patterns = [
                r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)([a-zA-Z0-9_-]{11})",
            ]
            for pattern in patterns:
                match = re.search(pattern, url)
                if match:
                    video_id = match.group(1)
                    break

            if video_id:
                keyboard = [
                    [
                        InlineKeyboardButton(
                            "🔄 Retry", callback_data=f"retry_yt_{video_id}"
                        )
                    ]
                ]
            else:
                context.user_data[f"retry_url_{user.id}"] = url
                keyboard = [
                    [
                        InlineKeyboardButton(
                            "🔄 Retry", callback_data=f"retry_ctx_{user.id}"
                        )
                    ]
                ]

            reply_markup = InlineKeyboardMarkup(keyboard)

            await processing_msg.edit_text(
                "❌ Failed to extract video information. Please check the URL and try again.",
                reply_markup=reply_markup,
            )
            return

        # Update download record
        download.title = video_info["title"]
        download.platform = video_info["platform"]
        download.duration = video_info["duration"]
        download.views = video_info["views"]
        db.commit()

        # Cache video info in Redis and context
        redis_client.set_video_info(user.id, video_info)
        context.user_data[f"video_info_{download.id}"] = video_info

        # Get format availability - check the actual lists AND flags
        video_formats = video_info.get("video_formats", [])
        audio_formats = video_info.get("audio_formats", [])
        image_formats = video_info.get("image_formats", [])

        # Use both list check AND flags for better reliability
        has_video = bool(video_formats) or video_info.get("has_video", False)
        has_audio = bool(audio_formats) or video_info.get("has_audio", False)
        has_image = bool(image_formats) or video_info.get("has_image", False)

        # Prepare info message based on content type
        if has_image and not has_video:
            # Image content
            info_message = (
                f"🖼 *Image Information*\n\n"
                f"📝 *Title:* {video_info['title']}\n"
                f"👤 *Uploader:* {video_info['uploader']}\n"
                f"🌐 *Platform:* {video_info['platform']}\n"
                f"👁 *Views:* {format_views(video_info['views'])}\n\n"
                f"🎯 *Select Format:*"
            )
        else:
            # Video/Audio content
            info_message = (
                f"📹 *Video Information*\n\n"
                f"📝 *Title:* {video_info['title']}\n"
                f"👤 *Uploader:* {video_info['uploader']}\n"
                f"🌐 *Platform:* {video_info['platform']}\n"
                f"⏱ *Duration:* {format_duration(video_info['duration'])}\n"
                f"👁 *Views:* {format_views(video_info['views'])}\n\n"
                f"🎯 *Select Format Type:*"
            )

        # Create format type selection keyboard
        keyboard = []

        # Add buttons based on what's available
        if has_video:
            keyboard.append(
                [
                    InlineKeyboardButton(
                        "🎬 Video", callback_data=f"type_video_{download.id}"
                    )
                ]
            )

        if has_audio:
            keyboard.append(
                [
                    InlineKeyboardButton(
                        "🎵 Audio Only", callback_data=f"type_audio_{download.id}"
                    )
                ]
            )

        if has_image:
            keyboard.append(
                [
                    InlineKeyboardButton(
                        "🖼 Image", callback_data=f"type_image_{download.id}"
                    )
                ]
            )

        # If no formats detected at all (shouldn't happen with YouTube), show error
        if not keyboard:
            await processing_msg.edit_text(
                "❌ No downloadable formats found for this video.\n"
                "This might be a private or unavailable video."
            )
            download.status = "failed"
            download.error_message = "No formats available"
            db.commit()
            return

        # Always show the keyboard with format options
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Send thumbnail with caption and keyboard
        thumbnail_url = video_info.get("thumbnail")
        if thumbnail_url:
            try:
                await processing_msg.delete()
                await update.message.reply_photo(
                    photo=thumbnail_url,
                    caption=info_message,
                    reply_markup=reply_markup,
                    parse_mode="Markdown",
                )
            except Exception as e:
                logger.warning(f"Failed to send photo: {e}")
                await processing_msg.edit_text(
                    info_message, reply_markup=reply_markup, parse_mode="Markdown"
                )
        else:
            await processing_msg.edit_text(
                info_message, reply_markup=reply_markup, parse_mode="Markdown"
            )

    except Exception as e:
        logger.error(f"Error in handle_url: {e}", exc_info=True)
        try:
            await processing_msg.edit_text(
                "❌ An error occurred while processing your request. Please try again."
            )
        except Exception as msg_error:
            logger.error(f"Failed to edit error message: {msg_error}")
            try:
                await update.message.reply_text(
                    "❌ An error occurred. Please try again."
                )
            except:
                pass
    finally:
        try:
            db.close()
        except:
            pass


async def safe_edit_message(message, text, parse_mode=None):
    """Safely edit a message whether it has text or caption"""
    try:
        if message.photo or message.video or message.audio or message.document:
            await message.edit_caption(caption=text, parse_mode=parse_mode)
        else:
            await message.edit_text(text, parse_mode=parse_mode)
    except Exception:
        pass


async def download_and_send_video(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    download_id: int,
    format_type: str,
    quality: str,
    format_id: str,
    user_id: int,
    existing_message=None,
):
    """Download and send video to user"""
    logger = logging.getLogger(__name__)
    db = get_db()
    try:
        download = db.query(Download).filter(Download.id == download_id).first()

        if not download:
            return

        # Get video info from Redis or context
        video_info_str = redis_client.get_video_info(user_id)
        if video_info_str:
            video_info = ast.literal_eval(video_info_str)
        elif f"video_info_{download_id}" in context.user_data:
            video_info = context.user_data[f"video_info_{download_id}"]
        else:
            await context.bot.send_message(
                chat_id=user_id, text="❌ Session expired. Please send the link again."
            )
            return

        # Send downloading message or use existing one
        if existing_message:
            current_text = existing_message.text or existing_message.caption or ""
            # Truncate text if too long to append
            if len(current_text) > 800:
                current_text = current_text[:800] + "..."

            await safe_edit_message(
                existing_message,
                f"{current_text}\n\n⬇️ Downloading...\nPlease wait...",
                parse_mode="Markdown",
            )
            download_msg = existing_message
        else:
            download_msg = await context.bot.send_message(
                chat_id=user_id,
                text=f"⬇️ Downloading {format_type} in {quality}...\n\nPlease wait...",
            )

        # Progress tracking
        import queue
        import threading

        progress_queue = queue.Queue()
        stop_progress = threading.Event()

        async def progress_updater():
            last_text = ""
            while not stop_progress.is_set():
                try:
                    text = progress_queue.get(timeout=0.5)
                    if text and text != last_text:
                        try:
                            await safe_edit_message(download_msg, text)
                            last_text = text
                        except Exception:
                            pass
                except queue.Empty:
                    await asyncio.sleep(0.1)
                except Exception:
                    break

        def sync_progress_callback(percentage: float, status_text: str):
            try:
                while not progress_queue.empty():
                    try:
                        progress_queue.get_nowait()
                    except queue.Empty:
                        break
                progress_queue.put(status_text)
            except Exception:
                pass

        # Download based on format type
        downloader = VideoDownloader()

        if format_type == "image":
            image_formats = video_info.get("image_formats", [])
            image_url = image_formats[0].get("url") if image_formats else None

            # Fallback if no specific image format but info has thumbnail
            if not image_url and video_info.get("thumbnail"):
                image_url = video_info.get("thumbnail")

            if not image_url:
                await safe_edit_message(download_msg, "❌ Image URL not found")
                return

            await safe_edit_message(download_msg, "⬇️ Downloading image...")

            loop = asyncio.get_event_loop()
            file_path, error_msg = await loop.run_in_executor(
                None,
                lambda: downloader.download_image(
                    image_url,
                    user_id,
                    video_info.get("title", "image"),
                ),
            )

            if not file_path:
                await safe_edit_message(
                    download_msg, f"❌ Download failed: {error_msg}"
                )
                return

        else:
            # Handle video/audio download
            progress_task = asyncio.create_task(progress_updater())

            loop = asyncio.get_event_loop()
            file_path, error_msg = await loop.run_in_executor(
                None,
                lambda: downloader.download_video(
                    video_info["url"],
                    format_type,
                    quality,
                    format_id,
                    user_id,
                    progress_callback=sync_progress_callback,
                ),
            )

            stop_progress.set()
            progress_task.cancel()
            try:
                await progress_task
            except asyncio.CancelledError:
                pass

            if not file_path:
                await safe_edit_message(
                    download_msg, f"❌ Download failed: {error_msg or 'Unknown error'}"
                )
                downloader.cleanup_user_files(user_id)
                return

        # Uploading logic
        await safe_edit_message(download_msg, "📤 Uploading...")

        file_size = os.path.getsize(file_path)
        bot_api_limit = 50 * 1024 * 1024
        telethon_limit = 2000 * 1024 * 1024
        use_telethon = False

        if file_size > bot_api_limit:
            if file_size > telethon_limit:
                await safe_edit_message(download_msg, "❌ File too large (>2GB).")
                os.remove(file_path)
                return
            use_telethon = True
            await safe_edit_message(
                download_msg, "📤 Uploading large file (using Telethon)..."
            )

        caption = f"🎬 {video_info['title']}\n\n💾 Quality: {quality}"
        performer = video_info.get("uploader", "Unknown")

        if format_type == "audio":
            caption = f"🎵 {video_info['title']}\n\n👤 Artist: {performer}\n💾 Quality: {quality}"

        # Download thumbnail
        thumbnail_path = None
        try:
            import requests

            thumbnail_url = video_info.get("thumbnail")
            if thumbnail_url:
                thumbnail_dir = os.path.join(os.path.dirname(file_path), "thumbnails")
                os.makedirs(thumbnail_dir, exist_ok=True)
                thumbnail_path = os.path.join(thumbnail_dir, f"thumb_{user_id}.jpg")
                response = requests.get(thumbnail_url, timeout=10)
                if response.status_code == 200:
                    with open(thumbnail_path, "wb") as f:
                        f.write(response.content)
        except Exception:
            thumbnail_path = None

        if use_telethon:
            try:
                # Mock progress for telethon
                async def telethon_progress(percentage, current, total):
                    pass

                channel_id, message_id = await telethon_uploader.upload_file(
                    user_id,
                    file_path,
                    caption=caption,
                    progress_callback=telethon_progress,
                    thumbnail_path=thumbnail_path,
                    is_audio=(format_type == "audio"),
                    audio_title=video_info.get("title"),
                    audio_performer=performer,
                    audio_duration=video_info.get("duration", 0),
                    is_video=(format_type == "video"),
                    video_duration=video_info.get("duration", 0),
                )

                if not channel_id or not message_id:
                    raise Exception(str(message_id))

                await safe_edit_message(download_msg, "📤 Sending to you...")
                await context.bot.copy_message(
                    chat_id=user_id,
                    from_chat_id=channel_id,
                    message_id=message_id,
                )
            except Exception as e:
                logger.error(f"Telethon upload error: {e}")
                await safe_edit_message(download_msg, "❌ Upload failed.")
        else:
            with open(file_path, "rb") as media_file:
                thumb_file = (
                    open(thumbnail_path, "rb")
                    if thumbnail_path and os.path.exists(thumbnail_path)
                    else None
                )
                try:
                    if format_type == "audio":
                        await context.bot.send_audio(
                            chat_id=user_id,
                            audio=media_file,
                            thumbnail=thumb_file,
                            caption=caption,
                            title=video_info["title"],
                            performer=performer,
                            duration=video_info.get("duration", 0),
                            write_timeout=60,
                        )
                    elif format_type == "image":
                        await context.bot.send_photo(
                            chat_id=user_id, photo=media_file, caption=caption
                        )
                    else:
                        await context.bot.send_video(
                            chat_id=user_id,
                            video=media_file,
                            caption=caption,
                            thumbnail=thumb_file,
                            supports_streaming=True,
                            write_timeout=60,
                        )
                finally:
                    if thumb_file:
                        thumb_file.close()

        # Success message
        try:
            await safe_edit_message(download_msg, "✅ Download Complete!")
        except:
            pass

        # Cleanup
        downloader.cleanup_user_files(user_id)
        if thumbnail_path and os.path.exists(thumbnail_path):
            os.remove(thumbnail_path)

        download.status = "completed"
        download.completed_at = datetime.utcnow()
        db.commit()

    except Exception as e:
        logger.error(f"Error in download_and_send: {e}", exc_info=True)
        try:
            await context.bot.send_message(chat_id=user_id, text="❌ Error occurred.")
        except:
            pass
    finally:
        db.close()
