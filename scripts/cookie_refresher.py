
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

# Path must match where downloader.py expects it: /app/cookies.txt (same level as bot.py)
# The downloader uses: os.path.join(os.path.dirname(self.download_path), "cookies.txt")
# where download_path is typically /app/downloads, so dirname is /app
COOKIES_FILE_PATH = "/app/cookies.txt"

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

                # 3. Random Interactions
                # Scroll a bit
                logger.info("Scrolling...")
                await page.mouse.wheel(0, random.randint(500, 2000))
                await asyncio.sleep(random.uniform(2, 5))

                # Click on a video or visit a random one
                logger.info("Looking for a video to watch...")
                
                # List of fallback videos (popular/safe content) to ensure we always watch something
                fallback_videos = [
                    "https://www.youtube.com/watch?v=jNQXAC9IVRw", # Me at the zoo
                    "https://www.youtube.com/watch?v=LXb3EKWsInQ", # Costa Rica 4K
                    "https://www.youtube.com/watch?v=9bZkp7q19f0", # PSY - GANGNAM STYLE
                    "https://www.youtube.com/watch?v=kJQP7kiw5Fk", # Despacito
                    "https://www.youtube.com/watch?v=JGwWNGJdvx8", # Ed Sheeran - Shape of You
                    "https://www.youtube.com/watch?v=aqz-KE-bpKQ", # Big Buck Bunny 60fps 4K
                ]

                video_thumbnails = await page.locator("ytd-rich-grid-media").all()
                
                # 50% chance to just go to a direct link anyway, or if no thumbnails found
                if not video_thumbnails or random.random() > 0.5:
                    logger.info("Navigating to a random fallback video...")
                    video_url = random.choice(fallback_videos)
                    await page.goto(video_url, timeout=60000)
                    await page.wait_for_load_state("networkidle")
                else:
                    logger.info("Clicking a homepage video...")
                    video = random.choice(video_thumbnails[:5]) # Pick one of the first few
                    
                    # Ensure it's clickable
                    if await video.is_visible():
                        await video.click()
                    else:
                        logger.warning("Homepage video not visible, using fallback.")
                        await page.goto(random.choice(fallback_videos))

                logger.info("Watching video...")
                # Watch for 10-30 seconds
                watch_duration = random.uniform(10, 30)
                await asyncio.sleep(watch_duration)
                
                # Scroll down to comments maybe
                await page.mouse.wheel(0, 500)
                await asyncio.sleep(2)

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

                # 4. Merge with existing cookies
                logger.info(f"Merging cookies with existing file: {COOKIES_FILE_PATH}...")
                
                # Auth cookies to PRESERVE from existing file (these are from logged-in account)
                AUTH_COOKIES_TO_PRESERVE = {
                    "LOGIN_INFO",
                    "__Secure-3PSID",
                    "__Secure-3PAPISID", 
                    "__Secure-1PSID",
                    "__Secure-1PAPISID",
                    "__Secure-1PSIDTS",
                    "__Secure-3PSIDTS",
                    "__Secure-3PSIDCC",
                    "__Secure-1PSIDCC",
                    "SID",
                    "HSID",
                    "SSID",
                    "APISID",
                    "SAPISID",
                    "NID",
                    # Session login info cookies
                    "ST-sbra4i",
                    "ST-183jmdn",
                }
                
                # Parse existing cookies from file
                existing_cookies = {}
                if os.path.exists(COOKIES_FILE_PATH):
                    try:
                        with open(COOKIES_FILE_PATH, 'r') as f:
                            existing_content = f.read()
                            logger.info(f"--- EXISTING COOKIES ({len(existing_content)} chars) ---\n{existing_content}\n-----------------------------------")
                            
                            for line in existing_content.splitlines():
                                line = line.strip()
                                if not line or line.startswith('#'):
                                    continue
                                parts = line.split('\t')
                                if len(parts) >= 7:
                                    cookie_name = parts[5]
                                    existing_cookies[cookie_name] = {
                                        'domain': parts[0],
                                        'include_subdomains': parts[1],
                                        'path': parts[2],
                                        'secure': parts[3],
                                        'expires': parts[4],
                                        'name': parts[5],
                                        'value': parts[6],
                                    }
                    except Exception as e:
                        logger.error(f"Failed to read existing cookies: {e}")

                # Parse new cookies from browser
                new_cookies = {}
                for cookie in cookies:
                    domain = cookie.get('domain', '')
                    include_subdomains = "TRUE" if domain.startswith('.') else "FALSE"
                    path = cookie.get('path', '/')
                    secure = "TRUE" if cookie.get('secure', False) else "FALSE"
                    expires = int(cookie.get('expires', 0))
                    if expires == -1:
                        expires = 0
                    name = cookie.get('name', '')
                    value = cookie.get('value', '')
                    
                    new_cookies[name] = {
                        'domain': domain,
                        'include_subdomains': include_subdomains,
                        'path': path,
                        'secure': secure,
                        'expires': str(expires),
                        'name': name,
                        'value': value,
                    }

                # Merge: Start with existing cookies, then update with new ones (except auth cookies)
                merged_cookies = existing_cookies.copy()
                
                for name, cookie_data in new_cookies.items():
                    if name in AUTH_COOKIES_TO_PRESERVE:
                        # Keep the existing auth cookie if it exists
                        if name in existing_cookies:
                            logger.info(f"Preserving auth cookie: {name}")
                            continue
                    # Update/add non-auth cookies
                    merged_cookies[name] = cookie_data
                
                # Build final Netscape format
                netscape_cookies = "# Netscape HTTP Cookie File\n# Merged: Auth cookies preserved, session cookies refreshed\n\n"
                
                for name, c in merged_cookies.items():
                    netscape_cookies += f"{c['domain']}\t{c['include_subdomains']}\t{c['path']}\t{c['secure']}\t{c['expires']}\t{c['name']}\t{c['value']}\n"

                # Log merged cookies
                logger.info(f"--- MERGED COOKIES ({len(netscape_cookies)} chars) ---\n{netscape_cookies}\n-----------------------------------")
                
                # Ensure directory exists
                os.makedirs(os.path.dirname(COOKIES_FILE_PATH) or '.', exist_ok=True)
                
                # Write to temp file first
                with tempfile.NamedTemporaryFile(mode='w', delete=False, dir=os.path.dirname(COOKIES_FILE_PATH) or '.') as tmp_file:
                    tmp_file.write(netscape_cookies)
                    tmp_file_path = tmp_file.name
                
                # Atomic move
                shutil.move(tmp_file_path, COOKIES_FILE_PATH)
                logger.info("Cookies merged and saved successfully.")
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
