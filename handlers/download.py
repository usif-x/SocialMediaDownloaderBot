import ast
import asyncio
import logging
import os
import re
import time
import urllib.parse
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from database import Download, User, get_db
from utils import (
    VideoDownloader,
    format_duration,
    format_file_size,
    format_views,
    redis_client,
    telethon_uploader,
)
from utils.downloader import create_progress_bar


def normalize_youtube_url(url: str) -> str:
    """Normalize YouTube URL by extracting video ID and stripping extra parameters"""
    # Standard video patterns
    video_id_patterns = [
        r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)([a-zA-Z0-9_-]{11})",
        r"(?:youtube\.com/embed/|youtube\.com/v/|youtube\.com/vi/)([a-zA-Z0-9_-]{11})",
    ]

    for pattern in video_id_patterns:
        match = re.search(pattern, url)
        if match:
            video_id = match.group(1)
            # Use short format if originally short, else standard
            if "youtu.be" in url:
                return f"https://youtu.be/{video_id}"
            return f"https://www.youtube.com/watch?v={video_id}"

    return url


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

    url = normalize_youtube_url(url)

    logger.info(f"User {user.id} sent URL: {url}")

    # Check if URL is from YouTube or Instagram
    youtube_patterns = [
        r"(https?://)?(www\.)?(youtube\.com|youtu\.be)",
        r"(https?://)?(m\.)?youtube\.com",
        r"(https?://)?youtube\.com/shorts/",
    ]

    instagram_patterns = [
        r"(https?://)?(www\.)?instagram\.com/(?:reel|reels)/",
        r"(https?://)?(www\.)?instagram\.com/p/",
        r"(https?://)?(www\.)?instagram\.com/tv/",
    ]

    # TikTok URL patterns (supports main site and short vm links)
    tiktok_patterns = [
        r"(https?://)?(www\.)?tiktok\.com",
        r"(https?://)?vm\.tiktok\.com",
    ]

    facebook_patterns = [
        r"(https?://)?(www\.)?facebook\.com",
        r"(https?://)?fb\.watch",
    ]

    # SoundCloud patterns
    soundcloud_patterns = [
        r"(https?://)?(www\.)?soundcloud\.com",
        r"(https?://)?(m\.)?soundcloud\.com",
    ]

    is_youtube = any(
        re.search(pattern, url, re.IGNORECASE) for pattern in youtube_patterns
    )

    is_instagram = any(
        re.search(pattern, url, re.IGNORECASE) for pattern in instagram_patterns
    )

    is_tiktok = any(
        re.search(pattern, url, re.IGNORECASE) for pattern in tiktok_patterns
    )

    is_facebook = any(
        re.search(pattern, url, re.IGNORECASE) for pattern in facebook_patterns
    )

    is_soundcloud = any(
        re.search(pattern, url, re.IGNORECASE) for pattern in soundcloud_patterns
    )

    if (
        not is_youtube
        and not is_instagram
        and not is_tiktok
        and not is_facebook
        and not is_soundcloud
    ):
        await update.message.reply_text(
            "❌ This bot only supports YouTube, Instagram, TikTok, Facebook and SoundCloud links.\n\n"
            "Please send a valid YouTube, Instagram, TikTok, Facebook or SoundCloud link.",
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

        # Daily quota reset if day changed
        now = datetime.utcnow()
        if not db_user.last_quota_reset or db_user.last_quota_reset.date() < now.date():
            db_user.used_quota = 0 if db_user.used_quota is None else 0
            db_user.last_quota_reset = now
            db.commit()

        # Check daily quota
        if (
            db_user.used_quota is not None
            and db_user.daily_quota is not None
            and db_user.used_quota >= db_user.daily_quota
        ):
            await processing_msg.edit_text(
                "🔐 You have reached your daily download limit. Please wait until your quota resets tomorrow."
            )
            return

        # Check if user already has an active downloading process
        if db_user.is_downloading:
            # Find the active download for this user to allow cancellation
            active_dl = (
                db.query(Download)
                .filter(Download.user_id == db_user.id, Download.status == "processing")
                .order_by(Download.created_at.desc())
                .first()
            )
            keyboard = []
            if active_dl:
                keyboard = [
                    [
                        InlineKeyboardButton(
                            "🛑 Cancel Download",
                            callback_data=f"cancel_processing_{active_dl.id}",
                        )
                    ]
                ]
            reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
            await processing_msg.edit_text(
                "⏳ You already have a download processing. Please wait or cancel it to start a new one.",
                reply_markup=reply_markup,
            )
            return

        # Reserve user's slot for this download
        db_user.is_downloading = True
        db.commit()

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

            # release download slot
            try:
                db_user.is_downloading = False
                db.commit()
            except:
                pass

            # Extract video ID from URL for retry (YouTube, Instagram, TikTok, Facebook, SoundCloud)
            video_id = None
            platform_prefix = "yt"

            # Try YouTube patterns first
            youtube_patterns = [
                r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)([a-zA-Z0-9_-]{11})",
            ]
            for pattern in youtube_patterns:
                match = re.search(pattern, url)
                if match:
                    video_id = match.group(1)
                    platform_prefix = "yt"
                    break

            # Try Instagram patterns if not YouTube
            if not video_id:
                instagram_patterns = [
                    r"instagram\.com/(?:reel|reels|p|tv)/([a-zA-Z0-9_-]+)",
                ]
                for pattern in instagram_patterns:
                    match = re.search(pattern, url)
                    if match:
                        video_id = match.group(1)
                        platform_prefix = "ig"
                        break

            # Try TikTok patterns if not found yet
            if not video_id:
                tiktok_patterns = [
                    r"tiktok\.com/@[^/]+/video/([0-9]+)",
                    r"tiktok\.com/v/([0-9]+)",
                    r"vm\.tiktok\.com/([A-Za-z0-9_-]+)",
                ]
                for pattern in tiktok_patterns:
                    match = re.search(pattern, url)
                    if match:
                        video_id = match.group(1)
                        platform_prefix = "tt"
                        break

            # Try Facebook patterns if still not found
            if not video_id:
                facebook_id_patterns = [
                    r"facebook\.com/(?:reel|reels)/([0-9A-Za-z_-]+)",
                    r"facebook\.com/.+/videos?/([0-9]+)",
                    r"facebook\.com/share/v/([A-Za-z0-9_-]+)",
                    r"fb\.watch/([A-Za-z0-9_-]+)",
                ]
                for pattern in facebook_id_patterns:
                    match = re.search(pattern, url)
                    if match:
                        video_id = match.group(1)
                        platform_prefix = "fb"
                        break

            # Try Spotify if still not found
            # (Spotify support removed)

            # Try SoundCloud if still not found
            if not video_id:
                soundcloud_id_patterns = [
                    r"soundcloud\.com/([^?#]+)",
                ]
                for pattern in soundcloud_id_patterns:
                    match = re.search(pattern, url)
                    if match:
                        raw_id = match.group(1).rstrip("/")
                        # URL-encode the track path (artist/track) for safe callback data
                        video_id = urllib.parse.quote_plus(raw_id)
                        platform_prefix = "sc"
                        break

            if video_id:
                # Use video ID in callback - much shorter than full URL
                keyboard = [
                    [
                        InlineKeyboardButton(
                            "🔄 Retry",
                            callback_data=f"retry_{platform_prefix}_{video_id}",
                        )
                    ]
                ]
            else:
                # Fallback: store in context if we can't extract ID
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

        # Prepare info message based on content type
        has_video = video_info.get("has_video", False)
        has_audio = video_info.get("has_audio", False)
        has_image = video_info.get("has_image", False)

        if has_image and not has_video:
            # Image content - escape Markdown special characters
            title = video_info['title'].replace('*', '\\*').replace('_', '\\_').replace('[', '\\[').replace(']', '\\]')
            uploader = video_info['uploader'].replace('*', '\\*').replace('_', '\\_').replace('[', '\\[').replace(']', '\\]')
            platform = video_info['platform'].replace('*', '\\*').replace('_', '\\_').replace('[', '\\[').replace(']', '\\]')
            
            info_message = (
                f"🖼 *Image Information*\n\n"
                f"📝 *Title:* {title}\n"
                f"👤 *Uploader:* {uploader}\n"
                f"🌐 *Platform:* {platform}\n"
                f"👁 *Views:* {format_views(video_info['views'])}\n\n"
                f"🎯 *Select Format:*"
            )
        else:
            # Video/Audio content - escape Markdown special characters in title and uploader
            title = video_info['title'].replace('*', '\\*').replace('_', '\\_').replace('[', '\\[').replace(']', '\\]')
            uploader = video_info['uploader'].replace('*', '\\*').replace('_', '\\_').replace('[', '\\[').replace(']', '\\]')
            platform = video_info['platform'].replace('*', '\\*').replace('_', '\\_').replace('[', '\\[').replace(']', '\\]')
            
            info_message = (
                f"📹 *Video Information*\n\n"
                f"📝 *Title:* {title}\n"
                f"👤 *Uploader:* {uploader}\n"
                f"🌐 *Platform:* {platform}\n"
                f"🕔 *Duration:* {format_duration(video_info['duration'])}\n"
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
                        "🎵 Audio", callback_data=f"type_audio_{download.id}"
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
            # No formats available, try user's preferred format
            preferred_format = db_user.preferred_format or "video"
            info_message = info_message.replace(
                "*Select Format Type:*", f"⬇️ Starting download ({preferred_format})..."
            )

            # Send thumbnail with caption
            thumbnail_url = video_info.get("thumbnail")
            if thumbnail_url:
                try:
                    try:
                        await update.message.reply_photo(
                            photo=thumbnail_url,
                            caption=info_message,
                            parse_mode="Markdown",
                        )
                        # If photo sent successfully, delete processing message
                        try:
                            await processing_msg.delete()
                        except:
                            pass
                    except Exception as photo_error:
                        logger.warning(f"Failed to send photo with Markdown: {photo_error}")
                        try:
                            await update.message.reply_photo(
                                photo=thumbnail_url,
                                caption=info_message,
                            )
                            # If photo sent successfully, delete processing message
                            try:
                                await processing_msg.delete()
                            except:
                                pass
                        except Exception as photo_error_plain:
                            logger.warning(f"Failed to send photo without parsing: {photo_error_plain}")
                            # Fall back to editing the processing message instead of deleting it
                            await safe_edit_message(processing_msg, info_message, parse_mode=None)
                except Exception as e:
                    logger.error(f"Failed to send photo: {e}")
                    # Fall back to editing the processing message
                    await safe_edit_message(processing_msg, info_message, parse_mode=None)
            else:
                await processing_msg.edit_text(info_message, parse_mode="Markdown")

            await download_and_send_video(
                update, context, download.id, preferred_format, "best", None, user.id
            )
        else:
            reply_markup = InlineKeyboardMarkup(keyboard)

            # Send thumbnail with caption and keyboard
            thumbnail_url = video_info.get("thumbnail")
            if thumbnail_url:
                try:
                    try:
                        await update.message.reply_photo(
                            photo=thumbnail_url,
                            caption=info_message,
                            reply_markup=reply_markup,
                            parse_mode="Markdown",
                        )
                        # If photo sent successfully, delete processing message
                        try:
                            await processing_msg.delete()
                        except:
                            pass
                    except Exception as photo_error:
                        logger.warning(f"Failed to send photo with Markdown: {photo_error}")
                        try:
                            await update.message.reply_photo(
                                photo=thumbnail_url,
                                caption=info_message,
                                reply_markup=reply_markup,
                                parse_mode="MarkdownV2",
                            )
                            # If photo sent successfully, delete processing message
                            try:
                                await processing_msg.delete()
                            except:
                                pass
                        except Exception as photo_error_v2:
                            logger.warning(f"Failed to send photo with MarkdownV2: {photo_error_v2}")
                            # Fall back to editing the processing message instead of deleting it
                            await safe_edit_message(
                                processing_msg, info_message, parse_mode=None, reply_markup=reply_markup
                            )
                except Exception as e:
                    logger.error(f"Failed to send photo: {e}")
                    # Fall back to editing the processing message
                    await safe_edit_message(
                        processing_msg, info_message, parse_mode=None, reply_markup=reply_markup
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
        # If an error occurred before handing off to download, clear the downloading flag
        try:
            if db and db_user:
                active = (
                    db.query(Download)
                    .filter(
                        Download.user_id == db_user.id, Download.status == "processing"
                    )
                    .first()
                )
                if not active and db_user.is_downloading:
                    db_user.is_downloading = False
                    db.commit()
        except Exception:
            pass
    finally:
        try:
            db.close()
        except:
            pass


async def safe_edit_message(message, text, parse_mode=None, reply_markup=None):
    """Safely edit a message whether it has text or caption"""
    logger = logging.getLogger(__name__)
    
    # Check if message exists
    if not message:
        logger.error("Cannot edit: message is None")
        return
        
    # Log what we're trying to do
    logger.debug(f"safe_edit_message: text_length={len(text)}, parse_mode={parse_mode}, has_photo={bool(message.photo)}")
    
    try:
        if message.photo or message.video or message.audio or message.document:
            # Message has media, edit caption
            await message.edit_caption(
                caption=text, parse_mode=parse_mode, reply_markup=reply_markup
            )
        else:
            # Text-only message
            await message.edit_text(
                text, parse_mode=parse_mode, reply_markup=reply_markup
            )
    except Exception as e:
        logger.warning(f"First edit attempt failed: {e}")
        # If edit fails, try the other method as fallback
        try:
            if message.text:
                await message.edit_text(
                    text, parse_mode=parse_mode, reply_markup=reply_markup
                )
            else:
                await message.edit_caption(
                    caption=text, parse_mode=parse_mode, reply_markup=reply_markup
                )
        except Exception as e2:
            logger.error(f"Both edit attempts failed: {e2}")
            pass  # Ignore if both fail


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
            # Update existing message
            current_text = existing_message.text or existing_message.caption or ""
            await safe_edit_message(
                existing_message,
                f"{current_text}\n\n⬇️ Downloading...\nPlease wait, this may take a few moments.",
                parse_mode="Markdown",
            )
            download_msg = existing_message
        else:
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
                            await safe_edit_message(download_msg, text)
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
                await safe_edit_message(download_msg, "❌ Image URL not found")
                download.status = "failed"
                download.error_message = "Image URL not found"
                db.commit()
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
                download.status = "failed"
                download.error_message = error_msg or "Download failed"
                db.commit()
                await safe_edit_message(
                    download_msg, f"❌ {error_msg or 'Unknown error'}"
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
                await safe_edit_message(
                    download_msg, f"❌ {error_msg or 'Unknown error'}"
                )
                # Clean up any leftover files
                downloader.cleanup_user_files(user_id)
                return

        # Send video or audio
        await safe_edit_message(download_msg, "📤 Uploading...")

        # Check file size
        import os

        file_size = os.path.getsize(file_path)

        # Telegram limits
        bot_api_limit = 50 * 1024 * 1024  # 50MB for Bot API
        telethon_limit = 2 * 1024 * 1024 * 1024  # 2GB for Telethon (user client)

        use_telethon = False

        # If file exceeds Bot API limit, try Telethon
        if file_size > bot_api_limit:
            if file_size > telethon_limit:
                await safe_edit_message(
                    download_msg,
                    f"❌ File too large ({file_size / (1024*1024):.1f}MB).\n"
                    f"Maximum supported size is 2GB.",
                )
                try:
                    os.remove(file_path)
                except:
                    pass
                download.status = "failed"
                download.error_message = (
                    f"File too large: {file_size / (1024*1024):.1f}MB"
                )
                db.commit()
                return

            # Try to use Telethon for large files
            use_telethon = True
            await safe_edit_message(
                download_msg,
                f"📤 Uploading large file ({file_size / (1024*1024):.1f}MB)...\n"
                f"This may take a while...",
            )

        caption = f"🎬 {video_info['title']}\n\n💾 Quality: {quality}"

        # Get performer (channel name) for audio
        performer = video_info.get("uploader") or "Unknown Artist"

        # For audio, update caption to include artist
        if format_type == "audio":
            caption = f"🎵 {video_info['title']}\n\n👤 Artist: {performer}\n💾 Quality: {quality}"

        # Download thumbnail for both audio and video
        thumbnail_path = None
        try:
            import requests

            thumbnail_url = video_info.get("thumbnail")
            if thumbnail_url:
                # Download thumbnail
                thumbnail_dir = os.path.join(os.path.dirname(file_path), "thumbnails")
                os.makedirs(thumbnail_dir, exist_ok=True)
                thumbnail_path = os.path.join(thumbnail_dir, f"thumb_{user_id}.jpg")

                def download_thumb():
                    try:
                        resp = requests.get(thumbnail_url, timeout=10)
                        if resp.status_code == 200:
                            with open(thumbnail_path, "wb") as f:
                                f.write(resp.content)
                            return True
                    except:
                        return False
                    return False

                # Run in executor
                loop = asyncio.get_event_loop()
                thumb_success = await loop.run_in_executor(None, download_thumb)

                if not thumb_success:
                    thumbnail_path = None

        except Exception as e:
            logger.warning(f"Failed to download thumbnail: {e}")
            thumbnail_path = None

        # Send media and capture message/file IDs for restore feature
        sent_message = None
        file_id = None

        # Use Telethon for large files
        if use_telethon:
            try:
                # Progress callback for Telethon upload: refresh every 3 seconds
                start_time = time.time()
                last_update = [start_time]  # timestamp of last update

                async def telethon_progress(percentage, current, total):
                    # Refresh every 3 seconds
                    now = time.time()
                    if now - last_update[0] < 3:
                        return
                    last_update[0] = now

                    # Calculate speed and ETA
                    elapsed = now - start_time
                    speed = current / elapsed if elapsed > 0 else 0
                    eta = (total - current) / speed if speed > 0 else 0

                    speed_str = f"{format_file_size(int(speed))}/s"
                    eta_str = format_duration(int(eta)) if eta > 0 else "Calculating..."
                    progress_bar = create_progress_bar(percentage, length=10)

                    try:
                        await safe_edit_message(
                            download_msg,
                            f"📤 Uploading large file...\n\n"
                            f"📈 {progress_bar} {percentage:.1f}%\n"
                            f"📤 Uploaded: {format_file_size(current)} / {format_file_size(total)}\n"
                            f"⚡ Speed: {speed_str}\n"
                            f"🕔 Estimated Time: {eta_str}",
                        )
                    except:
                        pass

                # Upload using Telethon (to storage channel)
                channel_id, message_id = await telethon_uploader.upload_file(
                    user_id,
                    file_path,
                    caption=caption,
                    progress_callback=telethon_progress,
                    thumbnail_path=thumbnail_path,
                    is_audio=(format_type == "audio"),
                    audio_title=video_info["title"] if format_type == "audio" else None,
                    audio_performer=performer if format_type == "audio" else None,
                    audio_duration=(
                        video_info.get("duration", 0) if format_type == "audio" else 0
                    ),
                    is_video=(format_type == "video"),
                    video_duration=(
                        video_info.get("duration", 0) if format_type == "video" else 0
                    ),
                    video_width=(
                        video_info.get("width", 1280) if format_type == "video" else 0
                    ),
                    video_height=(
                        video_info.get("height", 720) if format_type == "video" else 0
                    ),
                )

                if not channel_id or not message_id:
                    error_msg = (
                        message_id if isinstance(message_id, str) else "Unknown error"
                    )
                    await safe_edit_message(
                        download_msg,
                        f"❌ Failed to upload large file: {error_msg}\n\n"
                        f"Make sure STORAGE_CHANNEL_ID is set in .env",
                    )
                    download.status = "failed"
                    download.error_message = f"Telethon upload failed: {error_msg}"
                    db.commit()
                    downloader.cleanup_user_files(user_id)
                    return

                # Now copy the message from channel to user using Bot API
                await safe_edit_message(download_msg, "📤 Sending file to you...")

                # Create convert to audio button
                convert_markup = None
                if format_type == "video":
                    convert_markup = InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton(
                                    "🎵 Convert to Audio",
                                    callback_data=f"convert_audio_{download_id}",
                                )
                            ]
                        ]
                    )

                try:
                    sent_message = await context.bot.copy_message(
                        chat_id=user_id,
                        from_chat_id=channel_id,
                        message_id=message_id,
                        reply_markup=convert_markup,
                    )
                    if sent_message and hasattr(sent_message, "video"):
                        file_id = (
                            sent_message.video.file_id if sent_message.video else None
                        )
                    elif sent_message and hasattr(sent_message, "document"):
                        file_id = (
                            sent_message.document.file_id
                            if sent_message.document
                            else None
                        )

                except Exception as e:
                    logger.error(f"Failed to copy message from channel: {e}")
                    await safe_edit_message(
                        download_msg,
                        f"❌ Failed to send file.\n"
                        f"Make sure the bot is admin in the storage channel.",
                    )
                    download.status = "failed"
                    download.error_message = f"Failed to copy from channel: {str(e)}"
                    db.commit()
                    downloader.cleanup_user_files(user_id)
                    return

                # Mark as sent successfully - file sent from bot!

            except Exception as e:
                logger.error(f"Telethon upload error: {e}", exc_info=True)
                await safe_edit_message(
                    download_msg,
                    f"❌ Failed to upload large file: {str(e)[:100]}\n\n"
                    f"Please select a lower quality (under 50MB).",
                )
                download.status = "failed"
                download.error_message = str(e)[:200]
                db.commit()
                downloader.cleanup_user_files(user_id)
                return
        else:
            # Use Bot API for files under 50MB
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
                    # Prepare thumbnail for video
                    thumbnail_file = None
                    if thumbnail_path and os.path.exists(thumbnail_path):
                        thumbnail_file = open(thumbnail_path, "rb")

                    # Create convert to audio button
                    convert_markup = InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton(
                                    "🎵 Convert to Audio",
                                    callback_data=f"convert_audio_{download_id}",
                                )
                            ]
                        ]
                    )

                    try:
                        # Determine width/height
                        video_width = video_info.get("width", 0)
                        video_height = video_info.get("height", 0)

                        # Note: video_info['video_formats'] is used to populate keyboard
                        # We try to find the selected format to get specific dimensions
                        if format_id and video_info.get("video_formats"):
                            for fmt in video_info["video_formats"]:
                                if str(fmt.get("format_id")) == str(format_id):
                                    if fmt.get("width") and fmt.get("height"):
                                        video_width = fmt["width"]
                                        video_height = fmt["height"]
                                    break

                        sent_message = await context.bot.send_video(
                            chat_id=user_id,
                            video=media_file,
                            caption=caption,
                            thumbnail=thumbnail_file,
                            duration=video_info.get("duration", 0),
                            width=video_width,
                            height=video_height,
                            supports_streaming=True,
                            read_timeout=120,
                            write_timeout=120,
                            reply_markup=convert_markup,
                        )
                        if sent_message.video:
                            file_id = sent_message.video.file_id
                    finally:
                        # Clean up thumbnail file
                        if thumbnail_file:
                            thumbnail_file.close()

        # Update download status with message_id and file_id for restore
        download.status = "completed"
        download.quality = quality
        download.format_type = format_type
        download.file_size = file_size
        download.completed_at = datetime.utcnow()
        # Only set message_id and file_id if sent via Bot API (not Telethon)
        if sent_message and not use_telethon:
            if hasattr(sent_message, "message_id"):
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
            await safe_edit_message(
                download_msg,
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
        # Ensure we clear the user's downloading flag and update quota on success
        try:
            try:
                if download:
                    user_obj = (
                        db.query(User).filter(User.id == download.user_id).first()
                    )
                else:
                    user_obj = (
                        db.query(User).filter(User.telegram_id == user_id).first()
                    )
                if user_obj:
                    # Increment used_quota only if download completed successfully
                    try:
                        if download and download.status == "completed":
                            if user_obj.used_quota is None:
                                user_obj.used_quota = 0
                            user_obj.used_quota += 1
                    except Exception:
                        pass

                    # Clear downloading flag
                    try:
                        user_obj.is_downloading = False
                    except Exception:
                        pass

                    db.commit()
            except Exception as e:
                logger.warning(f"Failed updating user quota/is_downloading: {e}")
        finally:
            try:
                db.close()
            except:
                pass
