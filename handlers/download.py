import ast
import asyncio
import logging
import os
import re
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from database import Download, User, get_db
from utils import VideoDownloader, format_duration, format_views, redis_client


async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle video URL from user"""
    logger = logging.getLogger(__name__)
    user = update.effective_user
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

    # Send processing message
    processing_msg = await update.message.reply_text("🔄 Fetching video information...")

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
            await processing_msg.edit_text(
                "❌ Failed to extract video information. Please check the URL and try again."
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

        # Prepare info message based on content type
        has_video = video_info.get("has_video", False)
        has_audio = video_info.get("has_audio", False)
        has_image = video_info.get("has_image", False)

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

        if video_info.get("video_formats"):
            keyboard.append(
                [
                    InlineKeyboardButton(
                        "🎬 Video", callback_data=f"type_video_{download.id}"
                    )
                ]
            )

        if video_info.get("audio_formats"):
            keyboard.append(
                [
                    InlineKeyboardButton(
                        "🎵 Audio Only", callback_data=f"type_audio_{download.id}"
                    )
                ]
            )

        if video_info.get("image_formats"):
            keyboard.append(
                [
                    InlineKeyboardButton(
                        "🖼 Image", callback_data=f"type_image_{download.id}"
                    )
                ]
            )

        if not keyboard:
            # No formats available, try best
            info_message = info_message.replace(
                "*Select Format Type:*", "⬇️ Starting download..."
            )

            # Send thumbnail with caption
            thumbnail_url = video_info.get("thumbnail")
            if thumbnail_url:
                try:
                    await processing_msg.delete()
                    await update.message.reply_photo(
                        photo=thumbnail_url, caption=info_message, parse_mode="Markdown"
                    )
                except:
                    await processing_msg.edit_text(info_message, parse_mode="Markdown")
            else:
                await processing_msg.edit_text(info_message, parse_mode="Markdown")

            await download_and_send_video(
                update, context, download.id, "video", "best", None, user.id
            )
        else:
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
                except:
                    await processing_msg.edit_text(
                        info_message, reply_markup=reply_markup, parse_mode="Markdown"
                    )
            else:
                await processing_msg.edit_text(
                    info_message, reply_markup=reply_markup, parse_mode="Markdown"
                )

    except Exception as e:
        logger = logging.getLogger(__name__)
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


async def download_and_send_video(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    download_id: int,
    format_type: str,
    quality: str,
    format_id: str,
    user_id: int,
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

        # Send downloading message
        download_msg = await context.bot.send_message(
            chat_id=user_id,
            text=f"⬇️ Downloading {format_type} in {quality}...\n\nPlease wait, this may take a few moments.",
        )

        # Progress tracking with queue for thread-safe communication
        import queue
        import threading

        progress_queue = queue.Queue()
        stop_progress = threading.Event()

        async def progress_updater():
            """Async task to update progress messages from queue"""
            last_text = ""
            while not stop_progress.is_set():
                try:
                    # Non-blocking check with timeout
                    text = progress_queue.get(timeout=0.5)
                    if text and text != last_text:
                        try:
                            await download_msg.edit_text(text)
                            last_text = text
                        except Exception:
                            pass
                except queue.Empty:
                    await asyncio.sleep(0.1)
                except Exception:
                    break

        def sync_progress_callback(percentage: float, status_text: str):
            """Sync callback that puts progress in queue"""
            try:
                # Clear old items and add new one
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
            # Handle image download - no progress needed
            image_formats = video_info.get("image_formats", [])
            if format_id and format_id.isdigit():
                idx = int(format_id)
                if idx < len(image_formats):
                    image_url = image_formats[idx].get("url")
                else:
                    image_url = image_formats[0].get("url") if image_formats else None
            else:
                # Best quality = first (highest res)
                image_url = image_formats[0].get("url") if image_formats else None

            if not image_url:
                await download_msg.edit_text("❌ Image URL not found")
                download.status = "failed"
                download.error_message = "Image URL not found"
                db.commit()
                return

            await download_msg.edit_text("⬇️ Downloading image...")

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
                download.status = "failed"
                download.error_message = error_msg or "Download failed"
                db.commit()
                await download_msg.edit_text(
                    f"❌ Download failed: {error_msg or 'Unknown error'}"
                )
                downloader.cleanup_user_files(user_id)
                return

        else:
            # Handle video/audio download with progress
            # Start progress updater task
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

            # Stop progress updater
            stop_progress.set()
            progress_task.cancel()
            try:
                await progress_task
            except asyncio.CancelledError:
                pass

            if not file_path:
                download.status = "failed"
                download.error_message = error_msg or "Download failed"
                db.commit()
                await download_msg.edit_text(
                    f"❌ Download failed: {error_msg or 'Unknown error'}"
                )
                # Clean up any leftover files
                downloader.cleanup_user_files(user_id)
                return

        # Send video or audio
        await download_msg.edit_text("📤 Uploading...")

        # Check file size
        import os

        file_size = os.path.getsize(file_path)

        # Telegram file size limit is 50MB for bots
        if file_size > 50 * 1024 * 1024:
            await download_msg.edit_text(
                f"❌ File too large ({file_size / (1024*1024):.1f}MB).\n"
                f"Telegram bot limit is 50MB.\n\n"
                f"Try selecting a lower quality."
            )
            try:
                os.remove(file_path)
            except:
                pass
            download.status = "failed"
            download.error_message = f"File too large: {file_size / (1024*1024):.1f}MB"
            db.commit()
            return

        caption = f"🎬 {video_info['title']}\n\n💾 Quality: {quality}"

        # Get performer (channel name) for audio
        performer = video_info.get("uploader", "Unknown Artist")

        # Download thumbnail for audio
        thumbnail_path = None
        if format_type == "audio":
            try:
                import requests

                thumbnail_url = video_info.get("thumbnail")
                if thumbnail_url:
                    # Download thumbnail
                    thumbnail_dir = os.path.join(
                        os.path.dirname(file_path), "thumbnails"
                    )
                    os.makedirs(thumbnail_dir, exist_ok=True)
                    thumbnail_path = os.path.join(thumbnail_dir, f"thumb_{user_id}.jpg")

                    response = requests.get(thumbnail_url, timeout=10)
                    if response.status_code == 200:
                        with open(thumbnail_path, "wb") as f:
                            f.write(response.content)
            except Exception as e:
                logger.warning(f"Failed to download thumbnail: {e}")
                thumbnail_path = None

        # Send media and capture message/file IDs for restore feature
        sent_message = None
        file_id = None

        with open(file_path, "rb") as media_file:
            if format_type == "audio":
                # Prepare thumbnail for audio
                thumbnail_file = None
                if thumbnail_path and os.path.exists(thumbnail_path):
                    thumbnail_file = open(thumbnail_path, "rb")

                try:
                    sent_message = await context.bot.send_audio(
                        chat_id=user_id,
                        audio=media_file,
                        thumbnail=thumbnail_file,
                        caption=caption,
                        title=video_info["title"],
                        performer=performer,
                        duration=video_info.get("duration", 0),
                        read_timeout=120,
                        write_timeout=120,
                    )
                    if sent_message.audio:
                        file_id = sent_message.audio.file_id
                finally:
                    # Clean up thumbnail file
                    if thumbnail_file:
                        thumbnail_file.close()
                    if thumbnail_path and os.path.exists(thumbnail_path):
                        try:
                            os.remove(thumbnail_path)
                        except:
                            pass
            elif format_type == "image":
                sent_message = await context.bot.send_photo(
                    chat_id=user_id,
                    photo=media_file,
                    caption=f"🖼 {video_info['title']}",
                    read_timeout=120,
                    write_timeout=120,
                )
                if sent_message.photo:
                    file_id = sent_message.photo[-1].file_id
            else:
                sent_message = await context.bot.send_video(
                    chat_id=user_id,
                    video=media_file,
                    caption=caption,
                    supports_streaming=True,
                    read_timeout=120,
                    write_timeout=120,
                )
                if sent_message.video:
                    file_id = sent_message.video.file_id

        # Update download status with message_id and file_id for restore
        download.status = "completed"
        download.quality = quality
        download.format_type = format_type
        download.file_size = file_size
        download.completed_at = datetime.utcnow()
        if sent_message:
            download.message_id = sent_message.message_id
        if file_id:
            download.file_id = file_id
        db.commit()

        # Update download message to show completed
        icon = (
            "🎬"
            if format_type == "video"
            else ("🖼" if format_type == "image" else "🎵")
        )
        try:
            await download_msg.edit_text(
                f"✅ *Downloaded Successfully!*\n\n"
                f"{icon} *Format:* {format_type.title()}\n"
                f"📊 *Quality:* {quality}\n"
                f"💾 *Size:* {file_size / (1024*1024):.1f}MB",
                parse_mode="Markdown",
            )
        except:
            await download_msg.delete()

        # Clean up file
        try:
            downloader.cleanup_user_files(user_id)
        except:
            pass

        # Clean up Redis cache and context
        redis_client.delete_video_info(user_id)
        if f"video_info_{download_id}" in context.user_data:
            del context.user_data[f"video_info_{download_id}"]

    except Exception as e:
        logger.error(f"Error in download_and_send_video: {e}", exc_info=True)
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text="❌ An error occurred during download. Please try again.",
            )
        except:
            pass
    finally:
        db.close()
