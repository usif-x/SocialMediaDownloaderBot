#!/usr/bin/env python3
"""
YouTube Cookie Refresher - Background system for maintaining fresh YouTube cookies
Uses Playwright with Chromium to periodically fetch cookies without logging in.
"""

import asyncio
import logging
import os
import random
import tempfile
import time
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("cookie_refresher.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


class YouTubeCookieRefresher:
    """Handles YouTube cookie extraction using Playwright"""

    def __init__(
        self,
        cookies_file: str = "cookies.txt",
        profile_dir: str = "./browser_profile",
        headless: bool = False,
    ):
        self.cookies_file = cookies_file
        self.profile_dir = profile_dir
        self.headless = headless

        # Ensure profile directory exists
        Path(self.profile_dir).mkdir(parents=True, exist_ok=True)

    async def random_delay(self, min_seconds: float = 0.5, max_seconds: float = 2.0):
        """Add random delay to simulate human behavior"""
        delay = random.uniform(min_seconds, max_seconds)
        await asyncio.sleep(delay)

    async def human_like_mouse_movement(self, page):
        """Simulate human-like mouse movements"""
        try:
            # Get viewport size
            viewport = page.viewport_size
            if not viewport:
                return

            # Random positions within viewport
            for _ in range(random.randint(2, 4)):
                x = random.randint(0, viewport["width"])
                y = random.randint(0, viewport["height"])
                await page.mouse.move(x, y)
                await self.random_delay(0.1, 0.3)
        except Exception as e:
            logger.warning(f"Mouse movement failed: {e}")

    async def scroll_page(self, page):
        """Simulate human-like scrolling"""
        try:
            # Random scroll
            scroll_amount = random.randint(100, 500)
            await page.evaluate(f"window.scrollBy(0, {scroll_amount})")
            await self.random_delay(0.5, 1.5)

            # Scroll back up a bit
            scroll_back = random.randint(50, 200)
            await page.evaluate(f"window.scrollBy(0, -{scroll_back})")
            await self.random_delay(0.3, 0.8)
        except Exception as e:
            logger.warning(f"Scrolling failed: {e}")

    def cookies_to_netscape_format(self, cookies: list) -> str:
        """Convert Playwright cookies to Netscape format for yt-dlp"""
        lines = [
            "# Netscape HTTP Cookie File",
            "# http://curl.haxx.se/rfc/cookie_spec.html",
            "# This is a generated file!  Do not edit.",
            "",
        ]

        for cookie in cookies:
            # Netscape format fields:
            # domain, flag, path, secure, expiration, name, value
            domain = cookie.get("domain", "")
            flag = "TRUE" if domain.startswith(".") else "FALSE"
            path = cookie.get("path", "/")
            secure = "TRUE" if cookie.get("secure", False) else "FALSE"

            # Convert expiration (Playwright uses Unix timestamp)
            expires = cookie.get("expires", -1)
            if expires == -1:
                expires = 0  # Session cookie

            name = cookie.get("name", "")
            value = cookie.get("value", "")

            # Format: domain  flag  path  secure  expiration  name  value
            line = (
                f"{domain}\t{flag}\t{path}\t{secure}\t{int(expires)}\t{name}\t{value}"
            )
            lines.append(line)

        return "\n".join(lines) + "\n"

    async def fetch_cookies(self) -> bool:
        """
        Open YouTube in Chromium, browse naturally, extract cookies.
        Returns True if successful, False otherwise.
        """
        logger.info("Starting cookie refresh...")

        try:
            async with async_playwright() as p:
                # Launch browser with persistent context
                logger.info(f"Launching Chromium (headless={self.headless})...")

                context = await p.chromium.launch_persistent_context(
                    user_data_dir=self.profile_dir,
                    headless=self.headless,
                    viewport={"width": 1920, "height": 1080},
                    user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    locale="en-US",
                    timezone_id="America/New_York",
                    # Anti-detection settings
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--disable-dev-shm-usage",
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                    ],
                    # Permissions
                    permissions=["geolocation"],
                )

                # Get or create page
                if len(context.pages) > 0:
                    page = context.pages[0]
                else:
                    page = await context.new_page()

                # Navigate to YouTube
                logger.info("Navigating to YouTube...")
                await page.goto("https://www.youtube.com", wait_until="networkidle")

                # Random delay after page load
                await self.random_delay(2, 4)

                # Simulate human behavior
                logger.info("Simulating human behavior...")

                # Mouse movements
                await self.human_like_mouse_movement(page)

                # Random scrolling
                await self.scroll_page(page)

                # Maybe click on a random video (just hover, don't actually click)
                try:
                    videos = await page.query_selector_all("ytd-video-renderer")
                    if videos and len(videos) > 0:
                        random_video = random.choice(videos[:10])
                        await random_video.hover()
                        await self.random_delay(0.5, 1.5)
                except Exception as e:
                    logger.warning(f"Video hover failed: {e}")

                # Another scroll
                await self.scroll_page(page)

                # Final delay before extracting cookies
                await self.random_delay(1, 3)

                # Extract cookies
                logger.info("Extracting cookies...")
                cookies = await context.cookies()

                # Filter YouTube cookies
                youtube_cookies = [
                    c
                    for c in cookies
                    if "youtube.com" in c.get("domain", "")
                    or "google.com" in c.get("domain", "")
                ]

                logger.info(f"Found {len(youtube_cookies)} YouTube/Google cookies")

                if not youtube_cookies:
                    logger.warning("No cookies found!")
                    await context.close()
                    return False

                # Convert to Netscape format
                netscape_cookies = self.cookies_to_netscape_format(youtube_cookies)

                # Save cookies atomically
                self.save_cookies_atomic(netscape_cookies)

                logger.info(f"Cookies saved to {self.cookies_file}")

                # Close browser
                await context.close()

                return True

        except Exception as e:
            logger.error(f"Error fetching cookies: {e}", exc_info=True)
            return False

    def save_cookies_atomic(self, content: str):
        """
        Save cookies atomically to avoid corruption if yt-dlp is reading the file.
        Uses temp file + atomic rename.
        """
        # Get absolute path of cookies file
        cookies_path = Path(self.cookies_file).resolve()

        # Create temp file in same directory (for atomic rename)
        temp_fd, temp_path = tempfile.mkstemp(
            dir=cookies_path.parent, prefix=".cookies_", suffix=".tmp"
        )

        try:
            # Write to temp file
            with os.fdopen(temp_fd, "w") as f:
                f.write(content)

            # Atomic rename (replaces existing file)
            os.replace(temp_path, cookies_path)

            logger.info(f"Cookies file updated atomically: {cookies_path}")

        except Exception as e:
            # Clean up temp file on error
            try:
                os.unlink(temp_path)
            except:
                pass
            raise e


async def main():
    """Main function for standalone execution"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Fetch YouTube cookies using Playwright"
    )
    parser.add_argument(
        "--cookies-file",
        default="cookies.txt",
        help="Path to cookies file (default: cookies.txt)",
    )
    parser.add_argument(
        "--profile-dir",
        default="./browser_profile",
        help="Browser profile directory (default: ./browser_profile)",
    )
    parser.add_argument(
        "--headless", action="store_true", help="Run browser in headless mode"
    )

    args = parser.parse_args()

    refresher = YouTubeCookieRefresher(
        cookies_file=args.cookies_file,
        profile_dir=args.profile_dir,
        headless=args.headless,
    )

    success = await refresher.fetch_cookies()

    if success:
        logger.info("✅ Cookie refresh completed successfully!")
        return 0
    else:
        logger.error("❌ Cookie refresh failed!")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
