
import asyncio
import glob
import logging
import os
import platform
import random
import shutil
import subprocess
import tempfile
import time
from datetime import datetime

from fake_useragent import UserAgent
from playwright.async_api import async_playwright

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

COOKIES_FILE_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../cookies/cookies.txt"))

class CookieRefresher:
    def __init__(self):
        self.xvfb_process = None

    def start_xvfb(self):
        """Start Xvfb if on Linux"""
        if platform.system() == "Linux":
            logger.info("Starting Xvfb...")
            # Check if a display is already active
            if os.environ.get("DISPLAY"):
                logger.info(f"DISPLAY already set: {os.environ['DISPLAY']}")
                return

            display_num = 99
            os.environ["DISPLAY"] = f":{display_num}"
            
            # Start Xvfb
            xvfb_cmd = ["Xvfb", f":{display_num}", "-screen", "0", "1280x1024x24", "-ac"]
            try:
                self.xvfb_process = subprocess.Popen(
                    xvfb_cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                logger.info(f"Xvfb started on :{display_num}")
                time.sleep(2)  # Give Xvfb time to start
            except FileNotFoundError:
                logger.error("Xvfb not found. Please install it with 'apt-get install xvfb'")
            except Exception as e:
                logger.error(f"Failed to start Xvfb: {e}")

    def stop_xvfb(self):
        """Stop Xvfb process"""
        if self.xvfb_process:
            logger.info("Stopping Xvfb...")
            self.xvfb_process.terminate()
            try:
                self.xvfb_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.xvfb_process.kill()
            self.xvfb_process = None
        
        # Clean up environment variable so next run starts a fresh Xvfb
        if "DISPLAY" in os.environ:
            del os.environ["DISPLAY"]

    async def refresh(self):
        """Refreshes YouTube cookies"""
        logger.info("Starting cookie refresh process...")
        self.start_xvfb()

        ua = UserAgent()
        user_agent = ua.chrome

        async with async_playwright() as p:
            # Launch browser
            # We use a persistent context to simulate a real user profile if we wanted to keep session
            # But the requirement is to periodically fetch *without* logging in, so a fresh context is likely okay
            # However, to be more "human", we mimic a regular chrome instance.
            
            browser = await p.chromium.launch(
                headless=False,  # Requirements say non-headless (handled by Xvfb)
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-blink-features=AutomationControlled",
                ]
            )
            
            context = await browser.new_context(
                user_agent=user_agent,
                viewport={"width": 1280, "height": 800},
                locale="en-US",
                timezone_id="America/New_York", # Or randomize
            )

            page = await context.new_page()

            try:
                # 1. Go to YouTube
                logger.info("Navigating to YouTube...")
                await page.goto("https://www.youtube.com", timeout=60000)
                await page.wait_for_load_state("networkidle")

                # Handle consent popup if it appears (EU)
                try:
                    accept_button = page.get_by_text("Accept all", exact=True).or_(page.get_by_role("button", name="Accept all"))
                    if await accept_button.is_visible(timeout=5000):
                        await accept_button.click()
                        logger.info("Accepted cookies consent")
                except Exception:
                    pass

                # 2. Random Interactions
                # Scroll a bit
                logger.info("Scrolling...")
                await page.mouse.wheel(0, random.randint(500, 2000))
                await asyncio.sleep(random.uniform(2, 5))

                # Click on a video
                logger.info("Looking for a video to watch...")
                video_thumbnails = await page.locator("ytd-rich-grid-media").all()
                if video_thumbnails:
                    video = random.choice(video_thumbnails[:5]) # Pick one of the first few
                    await video.click()
                    
                    logger.info("Watching video...")
                    # Watch for 10-30 seconds
                    watch_duration = random.uniform(10, 30)
                    await asyncio.sleep(watch_duration)
                    
                    # Scroll down to comments maybe
                    await page.mouse.wheel(0, 500)
                    await asyncio.sleep(2)
                else:
                    logger.warning("No videos found on homepage.")

                # 3. Export All Cookies
                logger.info("Exporting all cookies...")
                # Get all cookies from the context (since we only visited YouTube, this is safe and complete)
                cookies = await context.cookies()
                
                if not cookies:
                    logger.error("No cookies retrieved!")
                    return False

                # Format in Netscape format for yt-dlp
                netscape_cookies = "# Netscape HTTP Cookie File\n# This file is generated by Playwright\n\n"
                
                for cookie in cookies:
                    domain = cookie.get('domain', '')
                    # Netscape format requires initial dot for domain if it's not present (sometimes)
                    # But usually Playwright returns it correctly.
                    
                    include_subdomains = "TRUE" if domain.startswith('.') else "FALSE"
                    path = cookie.get('path', '/')
                    secure = "TRUE" if cookie.get('secure', False) else "FALSE"
                    expires = int(cookie.get('expires', 0))
                    # If expires is 0 or -1, it's a session cookie. Set it to something far future or 0.
                    # yt-dlp might prefer actual expiration.
                    if expires == -1:
                        expires = 0
                        
                    name = cookie.get('name', '')
                    value = cookie.get('value', '')
                    
                    netscape_cookies += f"{domain}\t{include_subdomains}\t{path}\t{secure}\t{expires}\t{name}\t{value}\n"

                # 4. Atomic Save
                logger.info(f"Saving cookies to {COOKIES_FILE_PATH}...")
                
                # Ensure directory exists
                os.makedirs(os.path.dirname(COOKIES_FILE_PATH), exist_ok=True)
                
                # Write to temp file first
                with tempfile.NamedTemporaryFile(mode='w', delete=False, dir=os.path.dirname(COOKIES_FILE_PATH)) as tmp_file:
                    tmp_file.write(netscape_cookies)
                    tmp_file_path = tmp_file.name
                
                # Atomic move
                shutil.move(tmp_file_path, COOKIES_FILE_PATH)
                logger.info("Cookies refreshed and saved successfully.")
                return True

            except Exception as e:
                logger.error(f"Error during browser interaction: {e}")
                import traceback
                traceback.print_exc()
                return False
            finally:
                await context.close()
                await browser.close()
                self.stop_xvfb()

if __name__ == "__main__":
    refresher = CookieRefresher()
    asyncio.run(refresher.refresh())
