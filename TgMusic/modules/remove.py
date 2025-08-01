#  Copyright (c) 2025 AshokShau
#  Licensed under the GNU AGPL v3.0: https://www.gnu.org/licenses/agpl-3.0.html
#  Part of the TgMusicBot project. All rights reserved where applicable.
#  Modified by Devin - Major modifications and improvements

from pytdbot import Client, types

from TgMusic.core import Filter, language_manager, chat_cache
from TgMusic.core.admins import is_admin
from .utils.play_helpers import extract_argument


@Client.on_message(filters=Filter.command("remove"))
async def remove_song(c: Client, msg: types.Message) -> None:
    """Remove a specific track from the playback queue."""
    chat_id = msg.chat_id
    if chat_id > 0:
        return None

    args = extract_argument(msg.text, enforce_digit=True)

    if not await is_admin(chat_id, msg.from_id):
        await msg.reply_text("⛔ Administrator privileges required.")
        return None

    if not chat_cache.is_active(chat_id):
        await msg.reply_text("⏸ No active playback session.")
        return None

    if not args:
        await msg.reply_text(
            "ℹ️ <b>Usage:</b> <code>/remove [track_number]</code>\n"
            "Example: <code>/remove 3</code>"
        )
        return None

    try:
        track_num = int(args)
    except ValueError:
        user_lang = await language_manager.get_language(msg.from_id, msg.chat_id)
        await msg.reply_text(language_manager.get_text("remove_invalid_number", user_lang))
        return None

    _queue = chat_cache.get_queue(chat_id)

    if not _queue:
        await msg.reply_text("📭 The queue is currently empty.")
        return None

    if track_num <= 0 or track_num > len(_queue):
        user_lang = await language_manager.get_language(msg.from_id, msg.chat_id)
        await msg.reply_text(
            language_manager.get_text("remove_range_error", user_lang, count=len(_queue))
        )
        return None

    removed_track = chat_cache.remove_track(chat_id, track_num)
    user_lang = await language_manager.get_language(msg.from_id, msg.chat_id)
    reply = await msg.reply_text(
        language_manager.get_text("remove_success", user_lang, track=removed_track.name[:45], user=await msg.mention())
    )

    if isinstance(reply, types.Error):
        c.logger.warning(f"Error sending reply: {reply.message}")
    return None
