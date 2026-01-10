import asyncio
import logging
import os
import time
from typing import Callable, Dict, List, Optional, Tuple

import yt_dlp

from config.settings import settings

logger = logging.getLogger(__name__)


def create_progress_bar(percentage: float, length: int = 10) -> str:
    """Create a text progress bar"""
    filled = int(length * percentage / 100)
    empty = length - filled
    bar = "█" * filled + "░" * empty
    return bar


class VideoDownloader:
    """Wrapper for yt-dlp to handle video downloads"""

    def __init__(self):
        self.download_path = settings.TEMP_DOWNLOAD_PATH
        os.makedirs(self.download_path, exist_ok=True)

    def get_video_info(self, url: str) -> Optional[Dict]:
        """
        Extract video information without downloading

        Returns:
            Dictionary containing video info or None if failed
        """
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": False,
            "socket_timeout": 30,
            "skip_download": True,
            # Important: ignore format errors during info extraction
            "ignore_no_formats_error": True,
            "youtube_include_dash_manifest": True,
            "extractor_args": {
                "instagram": {"skip": ["dash"]},
                "youtube": {"player_client": ["android", "web"]},
            },
            # Add user agent to avoid bot detection
            "http_headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            },
        }

        # Add cookie support for YouTube and other sites
        cookies_file = os.path.join(os.path.dirname(self.download_path), "cookies.txt")
        if os.path.exists(cookies_file):
            ydl_opts["cookiefile"] = cookies_file
            logger.info(f"Using cookies file: {cookies_file}")
            # Log cookie content for debugging
            try:
                with open(cookies_file, "r") as f:
                    cookie_content = f.read()
                    logger.info(
                        f"--- DOWNLOADER COOKIES ({len(cookie_content)} chars) ---\n{cookie_content}\n-----------------------------------"
                    )
            except Exception as e:
                logger.error(f"Failed to read cookies file for logging: {e}")
        else:
            logger.warning(f"No cookies file found at {cookies_file}")

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                try:
                    info = ydl.extract_info(url, download=False)
                except yt_dlp.utils.DownloadError as e:
                    if "Requested format is not available" in str(e):
                        logger.warning(
                            "Default extraction failed, trying iOS client fallback..."
                        )
                        # Fallback for restricted videos (often work with iOS client)
                        ydl_opts["extractor_args"] = {
                            "youtube": {
                                "player_client": [
                                    "ios",
                                    "ios_embedded",
                                    "web_embedded",
                                ],
                                "skip": ["dash", "hls"],
                            }
                        }
                        with yt_dlp.YoutubeDL(ydl_opts) as ydl_fallback:
                            try:
                                info = ydl_fallback.extract_info(url, download=False)
                            except yt_dlp.utils.DownloadError as fallback_e:
                                logger.error(
                                    f"iOS client fallback also failed: {fallback_e}"
                                )
                                raise fallback_e  # Re-raise the fallback error if it fails
                    else:
                        raise e

                if not info:
                    return None

                # Check if this is a video or audio-only content
                has_video = (
                    info.get("vcodec") != "none" and info.get("vcodec") is not None
                )
                has_audio = (
                    info.get("acodec") != "none" and info.get("acodec") is not None
                )

                # Check if this is an image (Instagram, Twitter images, etc.)
                # IMPORTANT: YouTube thumbnails/storyboards should NOT be classified as images
                is_image = False
                image_urls = []

                # Get platform/extractor name
                platform = info.get("extractor", "").lower()

                # Only check for image formats if NOT YouTube
                # YouTube has image formats (thumbnails/storyboards) but they're not the main content
                if "formats" in info and info["formats"] and "youtube" not in platform:
                    for fmt in info["formats"]:
                        ext = fmt.get("ext", "").lower()
                        # Skip storyboards and thumbnails
                        format_note = (fmt.get("format_note") or "").lower()
                        if "storyboard" in format_note or "thumbnail" in format_note:
                            continue

                        if ext in ["jpg", "jpeg", "png", "webp", "gif"]:
                            is_image = True
                            image_urls.append(
                                {
                                    "url": fmt.get("url"),
                                    "ext": ext,
                                    "width": fmt.get("width", 0),
                                    "height": fmt.get("height", 0),
                                }
                            )

                # Also check direct URL for images (but not for YouTube)
                direct_url = info.get("url", "")
                if (
                    direct_url
                    and "youtube" not in platform
                    and any(
                        direct_url.lower().endswith(ext)
                        for ext in [".jpg", ".jpeg", ".png", ".webp", ".gif"]
                    )
                ):
                    is_image = True
                    ext = direct_url.split(".")[-1].lower().split("?")[0]
                    image_urls.append(
                        {
                            "url": direct_url,
                            "ext": ext,
                            "width": info.get("width", 0),
                            "height": info.get("height", 0),
                        }
                    )

                # Check thumbnail as fallback for image posts (but NOT for YouTube)
                # YouTube always has thumbnails, but they're not the main content
                if (
                    not has_video
                    and not has_audio
                    and info.get("thumbnail")
                    and "youtube" not in platform
                ):
                    thumb = info.get("thumbnail", "")
                    if thumb and not image_urls:
                        is_image = True
                        image_urls.append(
                            {
                                "url": thumb,
                                "ext": "jpg",
                                "width": 0,
                                "height": 0,
                            }
                        )

                # Extract available formats - separate video and audio
                video_formats = []
                audio_formats = []
                image_formats = []

                # Get duration for filesize estimation
                video_duration = info.get("duration") or 0

                if "formats" in info and info["formats"]:
                    seen_video_qualities = set()
                    seen_audio_qualities = set()

                    for fmt in info["formats"]:
                        fmt_vcodec = fmt.get("vcodec", "none")
                        fmt_acodec = fmt.get("acodec", "none")
                        protocol = fmt.get("protocol", "")

                        # Special handling for storyboard and thumbnails
                        format_note = (fmt.get("format_note") or "").lower()
                        if "storyboard" in format_note or "thumbnail" in format_note:
                            continue

                        # Determine resolution
                        height = fmt.get("height") or 0
                        width = fmt.get("width") or 0

                        if height:
                            resolution = f"{width}x{height}"
                        elif (
                            fmt.get("resolution")
                            and fmt.get("resolution") != "audio only"
                        ):
                            resolution = fmt.get("resolution")
                            # Try to parse height from resolution string (e.g. "1280x720")
                            try:
                                if "x" in resolution:
                                    height = int(resolution.split("x")[1])
                            except:
                                height = 0
                        else:
                            resolution = "Audio Only"
                            height = 0

                        # Format entry for selection
                        filesize = fmt.get("filesize") or fmt.get("filesize_approx")
                        if (
                            not filesize
                            and video_duration > 0
                            and (fmt.get("tbr") or fmt.get("vbr"))
                        ):
                            # Estimate filesize from bitrate
                            # filesize = (bitrate in bits/sec * duration) / 8
                            tbr = fmt.get("tbr") or fmt.get("vbr")
                            if tbr:
                                filesize = int((tbr * 1024 * video_duration) / 8)

                        format_entry = {
                            "format_id": fmt["format_id"],
                            "ext": fmt.get("ext", "mp4"),
                            "resolution": resolution,
                            "filesize": filesize,
                            "vcodec": fmt_vcodec,
                            "acodec": fmt_acodec,
                            "protocol": protocol,
                            "height": height,
                        }

                        # Check for video formats (including Apple HLS/m3u8)
                        is_video = fmt_vcodec and fmt_vcodec != "none"

                        # Add all video formats with valid height
                        if (
                            is_video
                            and height > 0
                            and height not in seen_video_qualities
                        ):
                            # Add quality label based on height
                            if height >= 2160:
                                quality_label = "4K (2160p)"
                            elif height >= 1440:
                                quality_label = "2K (1440p)"
                            elif height >= 1080:
                                quality_label = "Full HD (1080p)"
                            elif height >= 720:
                                quality_label = "HD (720p)"
                            elif height >= 480:
                                quality_label = "SD (480p)"
                            elif height >= 360:
                                quality_label = "360p"
                            elif height >= 240:
                                quality_label = "240p"
                            else:
                                quality_label = "144p"

                            format_entry["quality"] = quality_label
                            video_formats.append(format_entry)
                            seen_video_qualities.add(height)

                        # Check for audio formats
                        elif fmt_acodec and fmt_acodec != "none":
                            # Use bitrate as quality identifier
                            abr = fmt.get("abr", 0) or 0
                            if abr > 0 and abr not in seen_audio_qualities:
                                # Add quality label based on bitrate
                                if abr >= 256:
                                    quality_label = f"High ({int(abr)}kbps)"
                                elif abr >= 192:
                                    quality_label = f"Medium ({int(abr)}kbps)"
                                else:
                                    quality_label = f"Low ({int(abr)}kbps)"

                                format_entry["quality"] = quality_label
                                format_entry["abr"] = abr
                                audio_formats.append(format_entry)
                                seen_audio_qualities.add(abr)

                # Sort formats: higher resolution/bitrate first
                video_formats.sort(key=lambda x: x.get("height", 0), reverse=True)
                audio_formats.sort(
                    key=lambda x: x.get("filesize", 0) or 0, reverse=True
                )

                # Always provide options even if no specific formats found
                # This handles single-format videos (like Instagram)
                if not video_formats and has_video:
                    video_formats.append(
                        {
                            "format_id": "best",
                            "quality": "Best",
                            "ext": "mp4",
                            "filesize": 0,
                            "has_audio": has_audio,
                        }
                    )

                # Always allow audio extraction if content has audio
                if not audio_formats and has_audio:
                    audio_formats.append(
                        {
                            "format_id": "bestaudio",
                            "quality": "Best",
                            "ext": "m4a",
                            "filesize": 0,
                        }
                    )

                # If still no formats, check if there's a direct URL or formats exist
                # This is a fallback for platforms like Instagram
                if not video_formats and not audio_formats and not is_image:
                    if info.get("url") or info.get("formats"):
                        # Add fallback formats based on what content exists
                        if has_video:
                            video_formats.append(
                                {
                                    "format_id": "best",
                                    "quality": "Best",
                                    "ext": "mp4",
                                    "filesize": 0,
                                    "has_audio": has_audio,
                                }
                            )
                        if has_audio:
                            audio_formats.append(
                                {
                                    "format_id": "bestaudio",
                                    "quality": "Best",
                                    "ext": "m4a",
                                    "filesize": 0,
                                }
                            )

                # Extra fallback: if nothing detected but we have thumbnail AND not YouTube, treat as image
                if (
                    not video_formats
                    and not audio_formats
                    and not image_formats
                    and "youtube" not in platform
                ):
                    if info.get("thumbnail"):
                        is_image = True
                        image_urls.append(
                            {
                                "url": info.get("thumbnail"),
                                "ext": "jpg",
                                "width": 0,
                                "height": 0,
                            }
                        )
                        image_formats.append(
                            {
                                "url": info.get("thumbnail"),
                                "quality": "Original",
                                "ext": "jpg",
                            }
                        )

                # Build image formats list
                if image_urls:
                    # Sort by resolution (highest first)
                    image_urls.sort(
                        key=lambda x: (x.get("width", 0) * x.get("height", 0)),
                        reverse=True,
                    )
                    for img in image_urls[:5]:  # Limit to top 5
                        width = img.get("width", 0)
                        height = img.get("height", 0)
                        quality = (
                            f"{width}x{height}" if width and height else "Original"
                        )
                        image_formats.append(
                            {
                                "url": img["url"],
                                "quality": quality,
                                "ext": img["ext"],
                            }
                        )

                return {
                    "title": info.get("title", "Unknown"),
                    "duration": info.get("duration") or 0,
                    "views": info.get("view_count") or 0,
                    "width": info.get("width") or 0,
                    "height": info.get("height") or 0,
                    "uploader": info.get("uploader")
                    or info.get("channel")
                    or "Unknown",
                    "thumbnail": info.get("thumbnail", ""),
                    "platform": info.get("extractor", "Unknown"),
                    "url": url,
                    "video_formats": video_formats[:8],
                    "audio_formats": audio_formats[:8],
                    "image_formats": image_formats,
                    "has_video": bool(video_formats),
                    "has_audio": bool(audio_formats),
                    "has_image": bool(image_formats),
                }

        except Exception as e:
            logger.error(f"Error extracting video info: {e}", exc_info=True)
            return None

    def download_video(
        self,
        url: str,
        format_type: str = "video",
        quality: str = "best",
        format_id: str = None,
        user_id: int = 0,
        progress_callback: Callable[[float, str], None] = None,
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Download video or audio with specified quality

        Args:
            url: Video URL
            format_type: 'video' or 'audio'
            quality: Quality format (e.g., '720p', 'best', '128kbps')
            format_id: Specific format ID from yt-dlp
            user_id: User ID for organizing downloads
            progress_callback: Optional callback function(percentage, status_text)

        Returns:
            Tuple of (file_path, error_message)
        """
        self._progress_callback = progress_callback
        self._last_progress_update = 0
        user_path = os.path.join(self.download_path, str(user_id))
        os.makedirs(user_path, exist_ok=True)

        # Clean filename template
        output_template = os.path.join(user_path, "%(title).100s.%(ext)s")

        # Configure format string based on type and quality selection
        if format_type == "audio":
            # For audio, use format_id if provided, otherwise best
            if format_id and format_id != "best" and format_id != "bestaudio":
                format_string = f"{format_id}/bestaudio/best"
            else:
                format_string = "bestaudio/best"
        else:
            # For video, use format_id if provided to get specific quality
            if format_id and format_id != "best":
                # Use the specific format ID and merge with best audio
                # Format: specified_video+bestaudio/specified_video/fallback
                format_string = (
                    f"{format_id}+bestaudio/{format_id}/bestvideo+bestaudio/best"
                )
            elif quality and quality != "best" and quality != "Best":
                # If quality is specified (e.g., "720p", "480p") but no format_id
                # Extract height from quality string
                quality_height = quality.replace("p", "")
                if quality_height.isdigit():
                    # Select video with specific height and merge with best audio
                    format_string = f"bestvideo[height<={quality_height}]+bestaudio/best[height<={quality_height}]"
                else:
                    format_string = "bestvideo+bestaudio/best"
            else:
                # Default: best quality with audio
                format_string = "bestvideo+bestaudio/best"

        ydl_opts = {
            "format": format_string,
            "outtmpl": output_template,
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,  # Suppress terminal progress
            "ignoreerrors": False,
            "socket_timeout": 60,
            "retries": 3,
            "fragment_retries": 3,
            "restrictfilenames": True,
            "progress_hooks": [self._progress_hook],
            "extractor_args": {
                "instagram": {"skip": ["dash"]},
            },
            # Add user agent to avoid bot detection
            "http_headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            },
        }

        # Add cookie support
        cookies_file = os.path.join(os.path.dirname(self.download_path), "cookies.txt")
        if os.path.exists(cookies_file):
            ydl_opts["cookiefile"] = cookies_file
            # Log cookie content for debugging
            try:
                with open(cookies_file, "r") as f:
                    cookie_content = f.read()
                    logger.info(
                        f"--- DOWNLOADER COOKIES ({len(cookie_content)} chars) ---\n{cookie_content}\n-----------------------------------"
                    )
            except Exception as e:
                logger.error(f"Failed to read cookies file for logging: {e}")

        # Add postprocessors based on format type
        if format_type == "video":
            ydl_opts["merge_output_format"] = "mp4"
            # Use FFmpegVideoConvertor to ensure proper merging
            ydl_opts["postprocessors"] = [
                {
                    "key": "FFmpegVideoConvertor",
                    "preferedformat": "mp4",
                },
                {
                    "key": "FFmpegMetadata",
                },
                {
                    "key": "EmbedThumbnail",
                },
            ]
            ydl_opts["writethumbnail"] = True
            # Ensure ffmpeg merges audio and video
            ydl_opts["keepvideo"] = False
        else:
            # For audio, extract audio and embed thumbnail
            ydl_opts["writethumbnail"] = True
            ydl_opts["postprocessors"] = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "m4a",
                    "preferredquality": "192",
                },
                {
                    "key": "EmbedThumbnail",
                    "already_have_thumbnail": False,
                },
                {
                    "key": "FFmpegMetadata",
                },
            ]

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)

                if not info:
                    return None, "Failed to download"

                filename = ydl.prepare_filename(info)

                # Get the base name for file search
                base_name = os.path.splitext(filename)[0]

                # Handle different output extensions based on format type
                if format_type == "audio":
                    possible_extensions = [".m4a", ".mp3", ".opus", ".webm", ".ogg"]
                else:
                    possible_extensions = [".mp4", ".webm", ".mkv", ".mov", ".avi"]

                # Try original filename first
                if os.path.exists(filename):
                    return filename, None

                # Try with different extensions
                for ext in possible_extensions:
                    test_path = f"{base_name}{ext}"
                    if os.path.exists(test_path):
                        return test_path, None

                # Try to find any matching file in the directory
                if os.path.exists(user_path):
                    # Get title from info for matching
                    title_part = info.get("title", "")[:50] if info.get("title") else ""

                    latest_file = None
                    latest_time = 0

                    for f in os.listdir(user_path):
                        full_path = os.path.join(user_path, f)
                        if os.path.isfile(full_path):
                            file_time = os.path.getmtime(full_path)
                            # Prefer files modified in last 60 seconds
                            if file_time > latest_time:
                                latest_time = file_time
                                latest_file = full_path

                    if latest_file:
                        return latest_file, None

                return None, "File not found after download"

        except yt_dlp.utils.DownloadError as e:
            error_msg = str(e)
            logger.error(f"Download error: {error_msg}")
            return None, f"Download failed: {error_msg[:100]}"
        except Exception as e:
            logger.error(f"Error downloading: {e}", exc_info=True)
            return None, str(e)[:100]

    def download_image(
        self,
        image_url: str,
        user_id: int = 0,
        filename: str = "image",
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Download image from URL

        Args:
            image_url: Direct image URL
            user_id: User ID for organizing downloads
            filename: Base filename for the image

        Returns:
            Tuple of (file_path, error_message)
        """
        import urllib.error
        import urllib.request

        user_path = os.path.join(self.download_path, str(user_id))
        os.makedirs(user_path, exist_ok=True)

        try:
            # Get file extension from URL
            ext = image_url.split(".")[-1].lower().split("?")[0]
            if ext not in ["jpg", "jpeg", "png", "webp", "gif"]:
                ext = "jpg"

            # Clean filename
            clean_filename = "".join(
                c if c.isalnum() or c in "._- " else "_" for c in filename[:100]
            )
            file_path = os.path.join(user_path, f"{clean_filename}.{ext}")

            # Download image
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            request = urllib.request.Request(image_url, headers=headers)

            with urllib.request.urlopen(request, timeout=30) as response:
                with open(file_path, "wb") as f:
                    f.write(response.read())

            if os.path.exists(file_path):
                return file_path, None
            else:
                return None, "Failed to save image"

        except urllib.error.URLError as e:
            logger.error(f"Image download URL error: {e}")
            return None, f"Failed to download image: {str(e)[:50]}"
        except Exception as e:
            logger.error(f"Image download error: {e}", exc_info=True)
            return None, str(e)[:100]

    def _progress_hook(self, d: Dict):
        """Progress hook called by yt-dlp during download"""
        if not self._progress_callback:
            return

        # Throttle updates to avoid spam (max once per second)
        current_time = time.time()
        if (
            current_time - self._last_progress_update < 1.0
            and d["status"] != "finished"
        ):
            return
        self._last_progress_update = current_time

        try:
            if d["status"] == "downloading":
                # Calculate percentage
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                downloaded = d.get("downloaded_bytes", 0)

                if total > 0:
                    percentage = (downloaded / total) * 100
                else:
                    percentage = 0

                # Get speed and ETA
                speed = d.get("speed", 0) or 0
                eta = d.get("eta", 0) or 0

                # Format speed
                if speed > 0:
                    if speed >= 1024 * 1024:
                        speed_str = f"{speed / (1024 * 1024):.1f} MB/s"
                    else:
                        speed_str = f"{speed / 1024:.1f} KB/s"
                else:
                    speed_str = "-- KB/s"

                # Format ETA
                if eta > 0:
                    eta = int(eta)  # Convert to integer to avoid decimals
                    if eta >= 3600:
                        eta_str = f"{eta // 3600}h {(eta % 3600) // 60}m"
                    elif eta >= 60:
                        eta_str = f"{eta // 60}m {eta % 60}s"
                    else:
                        eta_str = f"{eta}s"
                else:
                    eta_str = "--"

                # Create progress bar
                bar = create_progress_bar(percentage)

                # Format downloaded size
                if downloaded >= 1024 * 1024:
                    downloaded_str = f"{downloaded / (1024 * 1024):.1f} MB"
                else:
                    downloaded_str = f"{downloaded / 1024:.1f} KB"

                status_text = (
                    f"⬇️ Downloading...\n\n"
                    f"{bar} {percentage:.1f}%\n\n"
                    f"📦 {downloaded_str}\n"
                    f"⚡ {speed_str}\n"
                    f"⏱ ETA: {eta_str}"
                )

                self._progress_callback(percentage, status_text)

            elif d["status"] == "finished":
                self._progress_callback(100, "✅ Download complete! Processing...")

        except Exception as e:
            logger.debug(f"Progress hook error: {e}")

    def cleanup_user_files(self, user_id: int):
        """Clean up all files for a user"""
        user_path = os.path.join(self.download_path, str(user_id))
        if os.path.exists(user_path):
            try:
                for f in os.listdir(user_path):
                    file_path = os.path.join(user_path, f)
                    if os.path.isfile(file_path):
                        os.remove(file_path)
            except Exception as e:
                logger.error(f"Error cleaning up files: {e}")

    @staticmethod
    def get_supported_sites() -> List[str]:
        """Get list of supported sites"""
        return settings.SUPPORTED_SITES

    @staticmethod
    def get_supported_sites() -> List[str]:
        """Get list of supported sites"""
        return settings.SUPPORTED_SITES
