import logging
from telegram import Update
from telegram.ext import ContextTypes
from scripts.cookie_refresher import CookieRefresher

logger = logging.getLogger(__name__)

async def refresh_cookies_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Refreshes YouTube cookies immediately"""
    user_id = update.effective_user.id
    
    # Simple admin check - you might want to replace this with a proper admin list check
    # For now, allowing anyone to trigger it or you can add a check against specific IDs
    # if str(user_id) not in settings.ADMIN_IDS:
    #     return

    status_message = await update.message.reply_text("🍪 Starting cookie refresh... This may take a minute.")
    
    try:
        refresher = CookieRefresher()
        success = await refresher.refresh()
        
        if success:
            await status_message.edit_text("✅ Cookies refreshed successfully!")
        else:
            await status_message.edit_text("❌ Failed to refresh cookies. Check logs for details.")
            
    except Exception as e:
        logger.error(f"Error in refresh_cookies_command: {e}")
        await status_message.edit_text(f"❌ An error occurred: {str(e)}")
