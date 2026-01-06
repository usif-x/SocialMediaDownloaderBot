# Storage Channel Setup for Large Files

To send large files (>50MB) from the **bot** (not your personal account), you need a storage channel.

## Why a Storage Channel?

1. Telethon uploads file to channel (supports 2GB)
2. Bot copies message from channel to user
3. User receives from **BOT**, not your account! ✅

## Setup Steps

### 1. Create a Private Channel

1. Open Telegram
2. Create New Channel
3. Name it: `Bot File Storage` (or any name)
4. Make it **Private**
5. Skip adding members

### 2. Add Bot as Admin

1. Go to channel settings
2. Click "Administrators"
3. Click "Add Administrator"
4. Search for your bot (`@your_bot_username`)
5. Give permissions:
   - ✅ Post Messages
   - ✅ Delete Messages
   - (Others optional)
6. Save

### 3. Get Channel ID

**Method 1: Using Bot**

1. Forward any message from the channel to `@userinfobot`
2. It will show the channel ID (format: `-100xxxxxxxxxx`)

**Method 2: Using Web**

1. Open channel in Telegram Web
2. URL will be: `https://web.telegram.org/k/#-xxxxxxxxx`
3. Add `-100` before the number: `-100xxxxxxxxx`

### 4. Update .env File

Add the channel ID to your `.env`:

```env
STORAGE_CHANNEL_ID=-1001234567890
```

**Important:** Include the minus sign and `-100` prefix!

### 5. Update docker-compose.yml (if using Docker)

```yaml
environment:
  - STORAGE_CHANNEL_ID=${STORAGE_CHANNEL_ID}
```

### 6. Restart Bot

```bash
# If running locally
python bot.py

# If using Docker
docker-compose restart
```

## Verification

Test with a large file (>50MB):

1. Send YouTube link to bot
2. Select 1080p quality
3. Bot should:
   - Upload to storage channel via Telethon
   - Copy from channel to you via Bot API
   - You receive from **THE BOT** ✅

## Troubleshooting

### "Failed to access storage channel"

- Make sure channel ID is correct (with `-100` prefix)
- Verify bot is admin in the channel
- Check STORAGE_CHANNEL_ID in .env

### "Make sure the bot is admin in the storage channel"

- Bot needs to be administrator
- Bot needs "Post Messages" permission
- Try removing and re-adding bot as admin

### File appears from your account, not bot

- STORAGE_CHANNEL_ID not set or incorrect
- Bot not admin in channel
- Check logs for specific error

## How It Works

```
[Large File >50MB]
    ↓
1. Telethon uploads to Storage Channel (2GB limit)
    ↓
2. Bot copies message from channel (using file_id)
    ↓
3. User receives from BOT (not your account!)
```

## Security

- Keep channel **Private**
- Only bot and you should be members
- Don't share channel invite link
- Files in channel can be deleted automatically if needed
