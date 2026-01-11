import asyncio
import json
import logging
from uuid import uuid4

from telegram import InlineQueryResultArticle, InputTextMessageContent, Update
from telegram.ext import ContextTypes

from utils import VideoDownloader

logger = logging.getLogger(__name__)


async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline queries for YouTube search"""
    query_text = (update.inline_query.query or "").strip()

    if not query_text:
        return

    logger.info(f"Inline query from {update.inline_query.from_user.id}: {query_text}")

    # Determine requested page from offset. offset is a string; we use it as last_page_index.
    # If offset == '' -> page 1. If offset == '1' -> next page will be 2.
    offset = update.inline_query.offset or ""
    try:
        page = int(offset) + 1 if offset else 1
    except Exception:
        page = 1

    # Call the scripts/youtube_search.py to get the requested page (10 results per page)
    import subprocess
    import sys

    cmd = [sys.executable, "scripts/youtube_search.py", query_text, "--page", str(page)]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            logger.error(f"youtube_search error: {stderr.decode()}")
            await update.inline_query.answer([], is_personal=True)
            return

        data = json.loads(stdout.decode())
    except Exception as e:
        logger.exception("Failed to run youtube_search script")
        await update.inline_query.answer([], is_personal=True)
        return

    results = data.get("results", [])

    inline_results = []
    for video in results[:10]:
        description = f"🕔 {video.get('time','')} • 👁 {video.get('views','')}"
        result = InlineQueryResultArticle(
            id=str(uuid4()),
            title=video.get("title", "Untitled"),
            description=description,
            thumbnail_url=video.get("image") or video.get("thumbnail") or None,
            input_message_content=InputTextMessageContent(
                message_text=video.get("url", "")
            ),
        )
        inline_results.append(result)

    # If we received a full page, indicate there's a next page by setting next_offset
    next_offset = ""
    if len(results) >= 10:
        # next_offset stored as string of current page so bot will compute page+1
        next_offset = str(page)

        from telegram.error import BadRequest

        try:
            await update.inline_query.answer(
                inline_results,
                cache_time=300,
                is_personal=True,
                next_offset=next_offset,
            )
        except BadRequest as e:
            # Common benign error when the inline query is too old or client timed out.
            # Log and ignore to avoid crashing the bot.
            logger.debug(f"Ignored BadRequest answering inline query: {e}")
    await update.inline_query.answer(
        inline_results, cache_time=300, is_personal=True, next_offset=next_offset
    )
