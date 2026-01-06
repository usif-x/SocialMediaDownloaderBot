#!/usr/bin/env python3
"""
YouTube OAuth2 Setup Script

This script helps you authenticate with YouTube using OAuth2.
OAuth2 tokens are more reliable than cookies and don't expire quickly.

Run this script ONCE on your local machine, then copy the oauth2.json to your server.
"""

import os
import subprocess
import sys


def main():
    print("=" * 60)
    print("YouTube OAuth2 Setup")
    print("=" * 60)
    print()
    print("This will authenticate yt-dlp with your Google account.")
    print("The token will be saved and can be used on your server.")
    print()
    print("Steps:")
    print("1. A browser will open asking you to log in to Google")
    print("2. Grant permission to yt-dlp")
    print("3. The token will be saved to oauth2.json")
    print()
    input("Press Enter to continue...")

    # Run yt-dlp with OAuth2 to trigger authentication
    cmd = [
        "yt-dlp",
        "--username",
        "oauth2",
        "--password",
        "",
        "--cache-dir",
        ".",
        "-F",  # Just list formats, don't download
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",  # Any video
    ]

    print()
    print("Running yt-dlp OAuth2 authentication...")
    print()

    try:
        result = subprocess.run(cmd, capture_output=False)

        if result.returncode == 0:
            print()
            print("=" * 60)
            print("✅ OAuth2 setup complete!")
            print("=" * 60)
            print()
            print("The OAuth2 token has been cached by yt-dlp.")
            print()
            print("For your Docker/Coolify deployment:")
            print()
            print("1. Find the token file (usually in ~/.cache/yt-dlp/youtube-oauth2/)")
            print("2. Copy it to your project as 'oauth2.json'")
            print("3. Update docker-compose.yml to mount it:")
            print()
            print("   volumes:")
            print("     - ./oauth2.json:/app/oauth2.json:ro")
            print()
        else:
            print()
            print("❌ OAuth2 setup may have failed. Check the output above.")

    except FileNotFoundError:
        print("❌ yt-dlp not found. Install it with: pip install yt-dlp")
        sys.exit(1)


if __name__ == "__main__":
    main()
