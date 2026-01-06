# Large File Upload Setup (Telethon)

This bot now supports uploading files up to **2GB** using Telethon!

## Why Telethon?

- **Bot API limit**: 50MB
- **Telethon limit**: 2GB (uses Telegram user client API)

## Setup Instructions

### 1. Get Telegram API Credentials

1. Go to https://my.telegram.org/apps
2. Log in with your phone number
3. Click "Create new application"
4. Fill in the form:
   - App title: `Your Bot Name`
   - Short name: `yourbot`
   - Platform: Choose any
5. Copy the **API ID** and **API Hash**

### 2. Update .env File

Add these lines to your `.env` file:

```env
# Telegram User Client (for large file uploads via Telethon)
TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH=abcdef1234567890abcdef1234567890
TELEGRAM_PHONE=+1234567890
```

Replace with your actual values:

- `TELEGRAM_API_ID`: The numeric API ID from my.telegram.org
- `TELEGRAM_API_HASH`: The API Hash from my.telegram.org
- `TELEGRAM_PHONE`: Your phone number with country code (e.g., +1234567890)

### 3. Install Telethon

```bash
pip install -r requirements.txt
```

### 4. Authenticate Telethon Session

Run the setup script:

```bash
python scripts/setup_telethon.py
```

This will:

1. Send a login code to your Telegram
2. Ask you to enter the code
3. If you have 2FA, ask for your password
4. Create an authenticated session file

### 5. Start Your Bot

```bash
python bot.py
```

## How It Works

- Files **under 50MB**: Sent via Bot API (fast, normal method)
- Files **50MB - 2GB**: Automatically sent via Telethon (slower but works)
- Files **over 2GB**: Rejected (Telegram's hard limit)

## Security Notes

⚠️ **Important**:

- Keep your `TELEGRAM_API_ID` and `TELEGRAM_API_HASH` secret
- The session file contains your authentication - keep it secure
- Don't share the session file or commit it to git
- Use a dedicated phone number/account if possible

## Troubleshooting

### "Telethon client not configured"

- Make sure you've added credentials to `.env`
- Run `python scripts/setup_telethon.py` to create session

### "Telethon upload failed"

- Check if session is still valid
- Re-run setup script to re-authenticate
- Check logs for specific error

### Session expires

- Run setup script again to re-authenticate
- Session files are stored in `downloads/telethon_session*`

## Without Telethon

If you don't want to set up Telethon, the bot will still work but:

- Only files under 50MB can be uploaded
- Users will see an error for larger files
- They'll need to select lower quality
