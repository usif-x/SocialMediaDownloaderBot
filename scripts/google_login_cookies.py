#!/usr/bin/env python3
"""
YouTube Cookie Refresher with Google Login

This version actually logs in to Google to get authenticated cookies.
Run this manually when cookies expire (every few hours).

IMPORTANT:
- This requires your Google credentials
- Google may ask for 2FA
- Better to use OAuth2 instead (see setup_youtube_oauth.py)
"""

import asyncio
import logging
import os
import sys
import tempfile
from pathlib import Path

from playwright.async_api import async_playwright

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def login_and_get_cookies(
    email: str,
    password: str,
    cookies_file: str = "cookies.txt",
    headless: bool = False,
):
    """
    Log in to Google and extract YouTube cookies.

    Args:
        email: Google email address
        password: Google password
        cookies_file: Output file path
        headless: Run browser without UI
    """
    logger.info("Starting Google login...")

    async with async_playwright() as p:
        # Use non-headless for login (Google blocks headless)
        browser = await p.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )

        context = await browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )

        page = await context.new_page()

        try:
            # Go to YouTube sign in
            logger.info("Navigating to YouTube login...")
            await page.goto(
                "https://accounts.google.com/signin/v2/identifier?service=youtube"
            )

            # Wait for email input
            await page.wait_for_selector('input[type="email"]', timeout=10000)

            # Enter email
            logger.info("Entering email...")
            await page.fill('input[type="email"]', email)
            await page.click('button:has-text("Next")')

            # Wait for password input
            await page.wait_for_selector('input[type="password"]', timeout=30000)
            await asyncio.sleep(2)

            # Enter password
            logger.info("Entering password...")
            await page.fill('input[type="password"]', password)
            await page.click('button:has-text("Next")')

            # Wait for login to complete (may need 2FA)
            logger.info("Waiting for login to complete...")
            logger.info("⚠️  If 2FA is required, complete it manually in the browser")

            # Wait until we reach YouTube
            try:
                await page.wait_for_url("**/youtube.com/**", timeout=120000)
                logger.info("✅ Successfully logged in to YouTube!")
            except Exception:
                # Check if we need 2FA
                if "challenge" in page.url or "signin" in page.url:
                    logger.warning("⚠️  2FA or additional verification required!")
                    logger.warning("Please complete the verification in the browser...")
                    input("Press Enter after completing verification...")

            # Navigate to YouTube to get all cookies
            await page.goto("https://www.youtube.com")
            await asyncio.sleep(3)

            # Get cookies
            cookies = await context.cookies()

            # Filter for YouTube/Google cookies
            youtube_cookies = [
                c
                for c in cookies
                if any(
                    d in c.get("domain", "")
                    for d in ["youtube.com", "google.com", "googlevideo.com"]
                )
            ]

            logger.info(f"Got {len(youtube_cookies)} cookies")

            # Log important cookies
            important = [
                "LOGIN_INFO",
                "SID",
                "HSID",
                "SSID",
                "APISID",
                "SAPISID",
                "VISITOR_INFO1_LIVE",
                "YSC",
                "__Secure-3PSID",
            ]
            found = [c["name"] for c in youtube_cookies if c["name"] in important]
            logger.info(f"Important cookies found: {', '.join(found)}")

            # Convert to Netscape format
            lines = [
                "# Netscape HTTP Cookie File",
                "# https://curl.haxx.se/rfc/cookie_spec.html",
                "# This is a generated file! Do not edit.",
                "",
            ]

            for c in youtube_cookies:
                domain = c.get("domain", "")
                flag = "TRUE" if domain.startswith(".") else "FALSE"
                path = c.get("path", "/")
                secure = "TRUE" if c.get("secure", False) else "FALSE"
                expires = int(c.get("expires", 0))
                name = c.get("name", "")
                value = c.get("value", "")

                lines.append(
                    f"{domain}\t{flag}\t{path}\t{secure}\t{expires}\t{name}\t{value}"
                )

            # Save cookies
            cookies_path = Path(cookies_file)
            cookies_path.parent.mkdir(parents=True, exist_ok=True)

            with open(cookies_path, "w") as f:
                f.write("\n".join(lines) + "\n")

            logger.info(f"✅ Cookies saved to {cookies_file}")

        except Exception as e:
            logger.error(f"Error during login: {e}")
            raise

        finally:
            await browser.close()


async def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Login to Google and get YouTube cookies"
    )
    parser.add_argument("--email", required=True, help="Google email address")
    parser.add_argument("--password", required=True, help="Google password")
    parser.add_argument(
        "--cookies-file", default="cookies.txt", help="Output cookies file"
    )
    parser.add_argument(
        "--headless", action="store_true", help="Run headless (may not work)"
    )

    args = parser.parse_args()

    await login_and_get_cookies(
        email=args.email,
        password=args.password,
        cookies_file=args.cookies_file,
        headless=args.headless,
    )


if __name__ == "__main__":
    asyncio.run(main())
