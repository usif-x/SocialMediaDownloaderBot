#!/usr/bin/env python3
"""
Setup script for Telethon client authentication.
This needs to be run once to create a session for uploading large files.
"""

import asyncio
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

from config.settings import settings


async def setup_telethon():
    """Setup Telethon client and create authenticated session"""

    print("=" * 60)
    print("Telethon Setup - Large File Upload Support")
    print("=" * 60)
    print()

    # Check if credentials are in .env
    if not settings.TELEGRAM_API_ID or not settings.TELEGRAM_API_HASH:
        print("❌ Missing Telegram API credentials!")
        print()
        print("To enable large file uploads (50MB - 2GB), you need:")
        print("1. Go to https://my.telegram.org/apps")
        print("2. Log in with your phone number")
        print("3. Create a new application")
        print("4. Copy the API ID and API Hash")
        print()
        print("Then add to your .env file:")
        print("TELEGRAM_API_ID=your_api_id")
        print("TELEGRAM_API_HASH=your_api_hash")
        print("TELEGRAM_PHONE=your_phone_number_with_country_code")
        print()
        print("Example:")
        print("TELEGRAM_API_ID=12345678")
        print("TELEGRAM_API_HASH=abcdef1234567890abcdef1234567890")
        print("TELEGRAM_PHONE=+1234567890")
        return

    if not settings.TELEGRAM_PHONE:
        print("❌ Missing phone number!")
        print("Add TELEGRAM_PHONE to .env (with country code, e.g., +1234567890)")
        return

    print(f"✓ API ID: {settings.TELEGRAM_API_ID}")
    print(f"✓ Phone: {settings.TELEGRAM_PHONE}")
    print()

    # Create session
    session_path = os.path.join(settings.TEMP_DOWNLOAD_PATH, "telethon_session")
    os.makedirs(settings.TEMP_DOWNLOAD_PATH, exist_ok=True)

    print("Creating Telethon client...")
    client = TelegramClient(
        session_path,
        settings.TELEGRAM_API_ID,
        settings.TELEGRAM_API_HASH,
    )

    try:
        await client.connect()
        print("✓ Connected to Telegram")
        print()

        if not await client.is_user_authorized():
            print("📱 Sending authentication code to your phone...")
            await client.send_code_request(settings.TELEGRAM_PHONE)
            print()

            # Get code from user
            code = input("Enter the code you received: ").strip()

            try:
                await client.sign_in(settings.TELEGRAM_PHONE, code)
                print("✓ Successfully authenticated!")

            except SessionPasswordNeededError:
                # 2FA enabled
                print()
                print("🔐 Two-factor authentication is enabled on your account.")
                password = input("Enter your 2FA password: ").strip()
                await client.sign_in(password=password)
                print("✓ Successfully authenticated with 2FA!")
        else:
            print("✓ Already authenticated!")

        # Test the session
        me = await client.get_me()
        print()
        print("=" * 60)
        print("✅ Setup Complete!")
        print("=" * 60)
        print(f"Logged in as: {me.first_name} {me.last_name or ''}")
        print(f"Username: @{me.username}" if me.username else "No username")
        print(f"Phone: {me.phone}")
        print()
        print("Your bot can now upload files up to 2GB!")
        print("Session saved to:", session_path)

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()

    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(setup_telethon())
