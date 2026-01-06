#!/usr/bin/env python3
"""
Setup script for Telethon client authentication and storage channel creation.
This needs to be run once to create a session for uploading large files.
"""

import asyncio
import os
import re
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from telethon.tl.functions.channels import CreateChannelRequest, EditAdminRequest
from telethon.tl.types import ChatAdminRights

from config.settings import settings


def update_env_file(key, value):
    """Update or add a key-value pair in .env file"""
    env_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"
    )

    # Read existing content
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            lines = f.readlines()
    else:
        lines = []

    # Check if key exists
    key_exists = False
    new_lines = []
    for line in lines:
        if line.strip().startswith(f"{key}="):
            new_lines.append(f"{key}={value}\n")
            key_exists = True
        else:
            new_lines.append(line)

    # Add key if it doesn't exist
    if not key_exists:
        new_lines.append(f"{key}={value}\n")

    # Write back
    with open(env_path, "w") as f:
        f.writelines(new_lines)


async def setup_telethon():
    """Setup Telethon client and create authenticated session"""

    print("=" * 60)
    print("Telethon Automated Setup - Large File Upload Support")
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

    if not settings.TELEGRAM_BOT_TOKEN:
        print("❌ Missing bot token!")
        print("Add TELEGRAM_BOT_TOKEN to .env")
        return

    print(f"✓ API ID: {settings.TELEGRAM_API_ID}")
    print(f"✓ Phone: {settings.TELEGRAM_PHONE}")
    print(f"✓ Bot Token: {settings.TELEGRAM_BOT_TOKEN[:20]}...")
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
        print("✅ Authentication Complete!")
        print("=" * 60)
        print(f"Logged in as: {me.first_name} {me.last_name or ''}")
        print(f"Username: @{me.username}" if me.username else "No username")
        print(f"Phone: {me.phone}")
        print()

        # Now create storage channel
        print("=" * 60)
        print("📁 Creating Storage Channel")
        print("=" * 60)
        print()

        channel_title = "Bot File Storage"
        channel_about = "Private storage channel for bot large file uploads"

        print(f"Creating private channel: {channel_title}")

        # Create channel
        result = await client(
            CreateChannelRequest(
                title=channel_title,
                about=channel_about,
                megagroup=False,  # Channel, not supergroup
            )
        )

        channel = result.chats[0]
        channel_id = int(f"-100{channel.id}")

        print(f"✓ Channel created! ID: {channel_id}")
        print()

        # Get bot entity
        print("Adding bot as administrator...")
        bot_username = settings.TELEGRAM_BOT_TOKEN.split(":")[0]

        try:
            # Get bot entity
            bot = await client.get_entity(f"@{bot_username}")

            # Admin rights for the bot
            admin_rights = ChatAdminRights(
                post_messages=True,
                edit_messages=True,
                delete_messages=True,
                invite_users=True,
                pin_messages=True,
                manage_call=False,
                ban_users=False,
                add_admins=False,
                change_info=False,
            )

            # Add bot as admin
            await client(
                EditAdminRequest(
                    channel=channel, user_id=bot, admin_rights=admin_rights, rank="Bot"
                )
            )

            print(f"✓ Bot added as administrator!")
            print()

        except Exception as e:
            print(f"⚠️  Could not add bot automatically: {e}")
            print()
            print("Please manually:")
            print(f"1. Open the channel: {channel_title}")
            print("2. Add your bot as administrator")
            print("3. Give it 'Post Messages' permission")
            print()

        # Update .env file
        print("Updating .env file with STORAGE_CHANNEL_ID...")
        update_env_file("STORAGE_CHANNEL_ID", str(channel_id))
        print(f"✓ STORAGE_CHANNEL_ID={channel_id} added to .env")
        print()

        print("=" * 60)
        print("✅ Complete Setup Finished!")
        print("=" * 60)
        print()
        print("Summary:")
        print(f"  • Session saved to: {session_path}")
        print(f"  • Storage Channel ID: {channel_id}")
        print(f"  • Channel Name: {channel_title}")
        print()
        print("Your bot can now:")
        print("  • Upload files up to 2GB")
        print("  • Send files from the bot (not your account)")
        print()
        print("🚀 Restart your bot to apply changes!")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()

    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(setup_telethon())
