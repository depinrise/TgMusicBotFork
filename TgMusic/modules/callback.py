#  Copyright (c) 2025 AshokShau
#  Licensed under the GNU AGPL v3.0: https://www.gnu.org/licenses/agpl-3.0.html
#  Part of the TgMusicBot project. All rights reserved where applicable.
#  Modified by Devin - Major modifications and improvements

from pytdbot import Client, types

from TgMusic.core import Filter, control_buttons, chat_cache, db, call, language_manager
from TgMusic.core.admins import is_admin, load_admin_cache
from .play import _get_platform_url, play_music
from .progress_handler import _handle_play_c_data
from .utils.play_helpers import edit_text
from ..core import DownloaderWrapper


@Client.on_updateNewCallbackQuery(filters=Filter.regex(r"(c)?play_\w+"))
async def callback_query(c: Client, message: types.UpdateNewCallbackQuery) -> None:
    """Handle all playback control callback queries (skip, stop, pause, resume)."""
    data = message.payload.data.decode()
    
    # Retrieve message and user info with error handling
    get_msg = await message.getMessage()
    if isinstance(get_msg, types.Error):
        c.logger.warning(f"Failed to get message: {get_msg.message}")
        return None

    # Get user ID from the message
    if isinstance(get_msg.sender_id, types.MessageSenderUser):
        user_id = get_msg.sender_id.user_id
    else:
        c.logger.warning("Invalid sender type for callback query")
        return None
    user = await c.getUser(user_id)
    if isinstance(user, types.Error):
        c.logger.warning(f"Failed to get user info: {user.message}")
        return None

    await load_admin_cache(c, message.chat_id)
    user_name = user.first_name

    def requires_admin(action: str) -> bool:
        """Check if action requires admin privileges."""
        return action in {
            "play_skip",
            "play_stop",
            "play_pause",
            "play_resume",
            "play_close",
        }

    def requires_active_chat(action: str) -> bool:
        """Check if action requires an active playback session."""
        return action in {
            "play_skip",
            "play_stop",
            "play_pause",
            "play_resume",
            "play_timer",
        }

    async def send_response(
        msg: str, alert: bool = False, delete: bool = False, reply_markup=None
    ) -> None:
        """Helper function to send standardized responses."""
        if alert:
            user_lang = await language_manager.get_language(message.sender_user_id, message.chat_id)
            await message.answer(language_manager.get_text("callback_playback_error", user_lang, error=msg), show_alert=True)
        else:
            edit_func = (
                message.edit_message_caption
                if get_msg.caption
                else message.edit_message_text
            )
            await edit_func(msg, reply_markup=reply_markup)

        if delete:
            _del_result = await c.deleteMessages(
                message.chat_id, [message.message_id], revoke=True
            )
            if isinstance(_del_result, types.Error):
                c.logger.warning(f"Message deletion failed: {_del_result.message}")

    # Check admin permissions if required
    if requires_admin(data) and not await is_admin(message.chat_id, user_id):
        user_lang = await language_manager.get_language(user_id, message.chat_id)
        await message.answer(
            language_manager.get_text("error_admin_required", user_lang), show_alert=True
        )
        return None

    chat_id = message.chat_id
    if requires_active_chat(data) and not chat_cache.is_active(chat_id):
        user_lang = await language_manager.get_language(user_id, message.chat_id)
        return await send_response(
            language_manager.get_text("playback_stopped", user_lang), alert=True
        )

    # Handle different control actions
    if data == "play_skip":
        result = await call.play_next(chat_id)
        if isinstance(result, types.Error):
            user_lang = await language_manager.get_language(user_id, chat_id)
            return await send_response(
                language_manager.get_text("callback_playback_error", user_lang, error=result.message),
                alert=True,
            )
        user_lang = await language_manager.get_language(user_id, chat_id)
        return await send_response(language_manager.get_text("playback_skipped", user_lang), delete=True)

    if data == "play_stop":
        result = await call.end(chat_id)
        if isinstance(result, types.Error):
            user_lang = await language_manager.get_language(user_id, chat_id)
            return await send_response(
                language_manager.get_text("callback_stop_failed", user_lang, error=result.message), alert=True
            )
        user_lang = await language_manager.get_language(user_id, chat_id)
        return await send_response(
            language_manager.get_text("playback_stopped", user_lang, user=user_name)
        )

    if data == "play_pause":
        result = await call.pause(chat_id)
        if isinstance(result, types.Error):
            user_lang = await language_manager.get_language(user_id, chat_id)
            return await send_response(
                language_manager.get_text("callback_pause_failed", user_lang, error=result.message),
                alert=True,
            )
        user_lang = await language_manager.get_language(user_id, chat_id)
        markup = (
            control_buttons("pause") if await db.get_buttons_status(chat_id) else None
        )
        return await send_response(
            language_manager.get_text("playback_paused", user_lang, user=user_name),
            reply_markup=markup,
        )

    if data == "play_resume":
        result = await call.resume(chat_id)
        if isinstance(result, types.Error):
            user_lang = await language_manager.get_language(user_id, chat_id)
            return await send_response(language_manager.get_text("callback_resume_failed", user_lang, error=result.message), alert=True)
        user_lang = await language_manager.get_language(user_id, chat_id)
        markup = (
            control_buttons("resume") if await db.get_buttons_status(chat_id) else None
        )
        return await send_response(
            language_manager.get_text("playback_resumed", user_lang, user=user_name),
            reply_markup=markup,
        )

    if data == "play_close":
        delete_result = await c.deleteMessages(
            chat_id, [message.message_id], revoke=True
        )
        if isinstance(delete_result, types.Error):
            user_lang = await language_manager.get_language(user_id, chat_id)
            await message.answer(
                language_manager.get_text("callback_interface_failed", user_lang, error=delete_result.message), show_alert=True
            )
            return None
        user_lang = await language_manager.get_language(user_id, chat_id)
        await message.answer(language_manager.get_text("callback_interface_success", user_lang), show_alert=True)
        return None

    if data.startswith("play_c_"):
        return await _handle_play_c_data(data, message, chat_id, user_id, user_name, c)

    # Handle music playback requests
    try:
        _, platform, song_id = data.split("_", 2)
    except ValueError:
        c.logger.error(f"Malformed callback data received: {data}")
        user_lang = await language_manager.get_language(user_id, chat_id)
        return await send_response(language_manager.get_text("callback_invalid_request", user_lang), alert=True)

    user_lang = await language_manager.get_language(user_id, chat_id)
    await message.answer(language_manager.get_text("callback_preparing", user_lang, user=user_name), show_alert=True)
    reply = await message.edit_message_text(
        language_manager.get_text("callback_searching", user_lang, user=user_name)
    )
    if isinstance(reply, types.Error):
        c.logger.warning(f"Message edit failed: {reply.message}")
        return None

    url = _get_platform_url(platform, song_id)
    if not url:
        c.logger.error(f"Unsupported platform: {platform} | Data: {data}")
        user_lang = await language_manager.get_language(user_id, chat_id)
        await edit_text(reply, text=language_manager.get_text("callback_unsupported_platform", user_lang, platform=platform))
        return None

    song = await DownloaderWrapper(url).get_info()
    if song:
        if isinstance(song, types.Error):
            user_lang = await language_manager.get_language(user_id, chat_id)
            await edit_text(reply, text=language_manager.get_text("callback_retrieval_error", user_lang, error=song.message))
            return None

        return await play_music(c, reply, song, user_name)

    user_lang = await language_manager.get_language(user_id, chat_id)
    await edit_text(reply, text=language_manager.get_text("callback_content_not_found", user_lang))
    return None
