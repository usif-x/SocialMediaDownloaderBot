"""
YouTube Cookie Refresher using Playwright with persistent browser profile.
This module maintains session continuity and better anti-detection.
"""

import asyncio
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

# Path must match where downloader.py expects it
COOKIES_FILE_PATH = "/app/cookies.txt"
# Persistent browser profile directory
BROWSER_PROFILE_DIR = "/app/browser_profile"


class CookieRefresher:
    def __init__(self):
        self.xvfb_process = None
        # Ensure profile directory exists
        os.makedirs(BROWSER_PROFILE_DIR, exist_ok=True)

    def start_xvfb(self):
        """Start Xvfb if on Linux"""
        if platform.system() == "Linux":
            logger.info("Starting Xvfb...")
            if os.environ.get("DISPLAY"):
                logger.info(f"DISPLAY already set: {os.environ['DISPLAY']}")
                return

            display_num = 99
            os.environ["DISPLAY"] = f":{display_num}"
            
            xvfb_cmd = ["Xvfb", f":{display_num}", "-screen", "0", "1920x1080x24", "-ac"]
            try:
                self.xvfb_process = subprocess.Popen(
                    xvfb_cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                logger.info(f"Xvfb started on :{display_num}")
                time.sleep(2)
            except FileNotFoundError:
                logger.error("Xvfb not found.")
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
        
        if "DISPLAY" in os.environ:
            del os.environ["DISPLAY"]

    async def refresh(self):
        """Refreshes YouTube cookies using persistent browser profile"""
        logger.info("Starting cookie refresh process...")
        self.start_xvfb()

        async with async_playwright() as p:
            try:
                # Use persistent context to maintain browser fingerprint and cookies
                # This is crucial - YouTube tracks browser fingerprints
                context = await p.chromium.launch_persistent_context(
                    user_data_dir=BROWSER_PROFILE_DIR,
                    headless=False,
                    viewport={"width": 1920, "height": 1080},
                    locale="en-US",
                    timezone_id="America/New_York",
                    args=[
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-blink-features=AutomationControlled",
                        "--disable-dev-shm-usage",
                        "--disable-accelerated-2d-canvas",
                        "--no-first-run",
                        "--no-zygote",
                        "--disable-gpu",
                        # Anti-detection flags
                        "--disable-features=IsolateOrigins,site-per-process",
                        "--disable-site-isolation-trials",
                    ],
                    ignore_default_args=["--enable-automation"],
                )

                # Remove webdriver property to avoid detection
                page = context.pages[0] if context.pages else await context.new_page()
                
                await page.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                    
                    // Override the plugins property
                    Object.defineProperty(navigator, 'plugins', {
                        get: () => [1, 2, 3, 4, 5]
                    });
                    
                    // Override languages
                    Object.defineProperty(navigator, 'languages', {
                        get: () => ['en-US', 'en']
                    });
                    
                    // Override platform
                    Object.defineProperty(navigator, 'platform', {
                        get: () => 'Win32'
                    });
                """)

                # Navigate to YouTube
                logger.info("Navigating to YouTube...")
                await page.goto("https://www.youtube.com", timeout=60000, wait_until="domcontentloaded")
                await asyncio.sleep(random.uniform(3, 5))

                # Handle consent popup
                try:
                    consent_buttons = [
                        page.get_by_role("button", name="Accept all"),
                        page.get_by_role("button", name="Accept"),
                        page.locator("button:has-text('Accept all')"),
                        page.locator("[aria-label='Accept all']"),
                    ]
                    for btn in consent_buttons:
                        try:
                            if await btn.is_visible(timeout=2000):
                                await btn.click()
                                logger.info("Accepted cookies consent")
                                await asyncio.sleep(2)
                                break
                        except:
                            continue
                except Exception:
                    pass

                # Human-like scrolling
                logger.info("Performing human-like actions...")
                for _ in range(random.randint(2, 4)):
                    await page.mouse.wheel(0, random.randint(200, 600))
                    await asyncio.sleep(random.uniform(0.5, 1.5))

                # Watch a video
                fallback_videos = [
                    "https://www.youtube.com/watch?v=jNQXAC9IVRw",
                    "https://www.youtube.com/watch?v=9bZkp7q19f0",
                    "https://www.youtube.com/watch?v=kJQP7kiw5Fk",
                    "https://www.youtube.com/watch?v=JGwWNGJdvx8",
                    "https://www.youtube.com/watch?v=aqz-KE-bpKQ",
                    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                ]

                logger.info("Navigating to a video...")
                video_url = random.choice(fallback_videos)
                await page.goto(video_url, timeout=60000, wait_until="domcontentloaded")
                await asyncio.sleep(random.uniform(2, 4))

                # Try to click play if video is paused
                try:
                    play_button = page.locator(".ytp-play-button")
                    if await play_button.is_visible(timeout=3000):
                        state = await play_button.get_attribute("data-title-no-tooltip")
                        if state and "Play" in state:
                            await play_button.click()
                            logger.info("Clicked play button")
                except:
                    pass

                # Watch for random duration
                watch_duration = random.uniform(15, 35)
                logger.info(f"Watching video for {watch_duration:.0f} seconds...")
                await asyncio.sleep(watch_duration)

                # More scrolling
                for _ in range(random.randint(1, 3)):
                    await page.mouse.wheel(0, random.randint(100, 400))
                    await asyncio.sleep(random.uniform(0.3, 1))

                # Export cookies
                logger.info("Exporting cookies...")
                cookies = await context.cookies()
                
                if not cookies:
                    logger.error("No cookies retrieved!")
                    return False

                # Auth cookies to preserve from existing file
                AUTH_COOKIES_TO_PRESERVE = {
                    "LOGIN_INFO", "__Secure-3PSID", "__Secure-3PAPISID",
                    "__Secure-1PSID", "__Secure-1PAPISID", "__Secure-1PSIDTS",
                    "__Secure-3PSIDTS", "__Secure-3PSIDCC", "__Secure-1PSIDCC",
                    "SID", "HSID", "SSID", "APISID", "SAPISID", "NID",
                }
                
                # Cookies that should ALWAYS be updated from browser
                ALWAYS_UPDATE_COOKIES = {
                    "VISITOR_INFO1_LIVE", "VISITOR_PRIVACY_METADATA", "YSC",
                    "PREF", "GPS", "SOCS", "__Secure-ROLLOUT_TOKEN",
                }

                # Parse existing cookies
                existing_cookies = {}
                if os.path.exists(COOKIES_FILE_PATH):
                    try:
                        with open(COOKIES_FILE_PATH, 'r') as f:
                            for line in f:
                                line = line.strip()
                                if not line or line.startswith('#'):
                                    continue
                                parts = line.split('\t')
                                if len(parts) >= 7:
                                    existing_cookies[parts[5]] = {
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

                # Build new cookies dict
                new_cookies = {}
                for cookie in cookies:
                    domain = cookie.get('domain', '')
                    if not domain.endswith('youtube.com') and not domain.endswith('google.com'):
                        continue  # Skip non-YouTube cookies
                        
                    include_subdomains = "TRUE" if domain.startswith('.') else "FALSE"
                    path = cookie.get('path', '/')
                    secure = "TRUE" if cookie.get('secure', False) else "FALSE"
                    expires = int(cookie.get('expires', 0))
                    if expires == -1:
                        # Session cookie - set expiry to 1 year from now
                        expires = int(time.time()) + 365 * 24 * 60 * 60
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

                # Merge cookies
                merged_cookies = existing_cookies.copy()
                
                for name, cookie_data in new_cookies.items():
                    # Always update these critical session cookies
                    if name in ALWAYS_UPDATE_COOKIES:
                        merged_cookies[name] = cookie_data
                        logger.info(f"Updated session cookie: {name}")
                    # Preserve auth cookies from existing
                    elif name in AUTH_COOKIES_TO_PRESERVE:
                        if name in existing_cookies:
                            logger.info(f"Preserved auth cookie: {name}")
                            continue
                        else:
                            # Auth cookie not in existing, add it
                            merged_cookies[name] = cookie_data
                    else:
                        # For other cookies, update with new values
                        merged_cookies[name] = cookie_data

                # Build final Netscape format
                netscape_cookies = "# Netscape HTTP Cookie File\n# Merged: Auth preserved, session refreshed\n\n"
                
                for name, c in merged_cookies.items():
                    netscape_cookies += f"{c['domain']}\t{c['include_subdomains']}\t{c['path']}\t{c['secure']}\t{c['expires']}\t{c['name']}\t{c['value']}\n"

                logger.info(f"Total cookies: {len(merged_cookies)}")
                
                # Atomic save
                os.makedirs(os.path.dirname(COOKIES_FILE_PATH) or '.', exist_ok=True)
                with tempfile.NamedTemporaryFile(mode='w', delete=False, dir=os.path.dirname(COOKIES_FILE_PATH) or '.') as tmp_file:
                    tmp_file.write(netscape_cookies)
                    tmp_file_path = tmp_file.name
                
                shutil.move(tmp_file_path, COOKIES_FILE_PATH)
                logger.info("Cookies merged and saved successfully.")
                return True

            except Exception as e:
                logger.error(f"Error during browser interaction: {e}")
                import traceback
                traceback.print_exc()
                return False
            finally:
                try:
                    await context.close()
                except:
                    pass
                self.stop_xvfb()


if __name__ == "__main__":
    refresher = CookieRefresher()
    asyncio.run(refresher.refresh())
