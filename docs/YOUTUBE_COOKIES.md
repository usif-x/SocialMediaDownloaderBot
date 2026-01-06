# YouTube Cookie Authentication

YouTube requires authentication to download videos. This guide will help you set up cookies.

## Why Cookies Are Needed

YouTube blocks automated downloads by requiring you to "sign in to confirm you're not a bot." We solve this by using browser cookies from your logged-in YouTube session.

## Option 1: Export Cookies from Browser (Recommended)

### Using Chrome Extension

1. Install **"Get cookies.txt LOCALLY"** extension:

   - Chrome: https://chrome.google.com/webstore/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc
   - Firefox: https://addons.mozilla.org/en-US/firefox/addon/cookies-txt/

2. Go to YouTube.com and **log in** to your account

3. Click the extension icon and click **"Export"**

4. Save the file as `cookies.txt`

5. Place `cookies.txt` in your bot's root directory (same folder as `bot.py`)

### Manual Export (Alternative)

If you prefer a manual method:

```bash
# For Chrome/Chromium
python -m yt_dlp --cookies-from-browser chrome --cookies cookies.txt --skip-download "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# For Firefox
python -m yt_dlp --cookies-from-browser firefox --cookies cookies.txt --skip-download "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
```

## Option 2: Use Browser Cookies Automatically (Docker Only)

If running locally (not in Docker), the bot can use your browser cookies automatically. No setup needed!

⚠️ **Note**: This doesn't work in Docker because the container can't access your browser.

## Updating Cookies

YouTube cookies expire periodically. If you see authentication errors:

1. Log out of YouTube
2. Clear YouTube cookies
3. Log back in
4. Export new cookies using the steps above
5. Replace the old `cookies.txt` file
6. Restart the bot

## For Docker/Production

### Place cookies.txt in your project:

```
SocialMediaDownloader/
├── cookies.txt          ← Place here
├── bot.py
├── docker-compose.yml
└── ...
```

The Dockerfile already copies this file to the container.

### Verify it's working:

Check the bot logs for:

```
✓ Using cookies file for authentication
```

If you see:

```
❌ ERROR: [youtube] Sign in to confirm you're not a bot
```

Your cookies are expired or invalid - export new ones!

## Security Notes

⚠️ **Important**:

- **Never share your cookies.txt file** - it contains your login session
- Add `cookies.txt` to `.gitignore` (already done in this project)
- Cookies expire after some time (days/weeks) and need to be refreshed
- Use a dedicated YouTube account if possible

## Troubleshooting

### "Sign in to confirm you're not a bot"

- Your cookies are expired or invalid
- Export fresh cookies from your browser
- Make sure you're logged in to YouTube when exporting

### "No cookies available"

- The `cookies.txt` file is missing or in the wrong location
- In Docker, make sure the file is in the project root before building

### Cookies work locally but not in Docker

- Make sure `cookies.txt` is in the project root
- Rebuild the Docker image: `docker-compose build --no-cache`
- The Dockerfile copies `cookies.txt` during build

### Bot works for some videos but not others

- Some videos may require additional authentication
- Age-restricted content may need account-based cookies
- Private/unlisted videos need the uploader's account cookies

## Alternative: OAuth (Advanced)

For a more permanent solution, you can set up OAuth authentication:

1. Go to https://console.cloud.google.com/
2. Create a new project
3. Enable YouTube Data API v3
4. Create OAuth 2.0 credentials
5. Download credentials JSON
6. Use with yt-dlp's `--username oauth2 --password ''`

This is more complex but doesn't require cookie refreshing.
