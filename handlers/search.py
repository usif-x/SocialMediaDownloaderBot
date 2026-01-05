import asyncio
import logging
from uuid import uuid4

from telegram import InlineQueryResultArticle, InputTextMessageContent, Update
from telegram.ext import ContextTypes

from utils import VideoDownloader

logger = logging.getLogger(__name__)


async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline queries for YouTube search"""
    query_text = update.inline_query.query.strip()

    if not query_text:
        # Show help message when no query
        return

    logger.info(f"Inline query from {update.inline_query.from_user.id}: {query_text}")

    # Perform YouTube search
    downloader = VideoDownloader()
    loop = asyncio.get_event_loop()
    results = await loop.run_in_executor(
        None, lambda: downloader.search_youtube(query_text, limit=10)
    )

    if not results:
        # Return empty results
        await update.inline_query.answer([])
        return

    # Create inline query results
    inline_results = []
    for video in results[:10]:
        # Create result for each video
        result = InlineQueryResultArticle(
            id=str(uuid4()),
            title=video["title"],
            description=f"👤 {video['channel']} • ⏱ {video['duration']} • 👁 {video['views']}",
            thumbnail_url=video["thumbnail"],
            input_message_content=InputTextMessageContent(message_text=video["url"]),
        )
        inline_results.append(result)

    # Answer the inline query
    await update.inline_query.answer(inline_results, cache_time=300, is_personal=True)
