from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from bot import on_ready, bot
from utils.ui import MusicControlView


def make_interaction():
    interaction = MagicMock()
    interaction.guild = MagicMock()
    interaction.guild.voice_client = MagicMock()
    interaction.response = MagicMock()
    interaction.response.send_message = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    interaction.message = MagicMock()
    interaction.message.edit = AsyncMock()
    return interaction


def make_music_cog():
    music_cog = MagicMock()
    music_cog._state = MagicMock(
        return_value=MagicMock(queue=[{"title": "Song 1"}], actual_song="Song 0")
    )
    music_cog.update_activity = MagicMock()
    music_cog._cleanup_state = MagicMock()
    return music_cog


def make_bot(music_cog=None):
    bot_mock = MagicMock()
    if music_cog is None:
        music_cog = make_music_cog()
    bot_mock.get_cog = MagicMock(return_value=music_cog)
    return bot_mock


def test_music_control_view_has_expected_buttons():
    view = MusicControlView(bot=make_bot())

    custom_ids = [child.custom_id for child in view.children]
    assert custom_ids == ["pause_resume", "skip", "stop", "view_queue"]


@pytest.mark.asyncio
async def test_pause_resume_button_pauses_and_flips_emoji():
    bot_mock = make_bot()
    view = MusicControlView(bot=bot_mock)
    interaction = make_interaction()
    interaction.guild.voice_client.is_paused.return_value = False
    interaction.guild.voice_client.is_playing.return_value = True

    button = next(child for child in view.children if child.custom_id == "pause_resume")
    await button.callback(interaction)

    interaction.guild.voice_client.pause.assert_called_once()
    assert str(button.emoji) == "▶️"
    interaction.response.send_message.assert_awaited_once()
    bot_mock.get_cog.return_value.update_activity.assert_called_once_with(interaction.guild)


@pytest.mark.asyncio
async def test_skip_button_skips_and_updates_activity():
    bot_mock = make_bot()
    view = MusicControlView(bot=bot_mock)
    interaction = make_interaction()
    interaction.guild.voice_client.is_playing.return_value = True

    button = next(child for child in view.children if child.custom_id == "skip")
    await button.callback(interaction)

    interaction.guild.voice_client.stop.assert_called_once()
    interaction.response.send_message.assert_awaited_once()
    bot_mock.get_cog.return_value.update_activity.assert_called_once_with(interaction.guild)


@pytest.mark.asyncio
async def test_stop_button_disables_all_buttons_and_edits_message():
    bot_mock = make_bot()
    view = MusicControlView(bot=bot_mock)
    interaction = make_interaction()
    interaction.guild.voice_client.is_connected.return_value = True
    interaction.guild.voice_client.is_playing.return_value = True

    button = next(child for child in view.children if child.custom_id == "stop")
    await button.callback(interaction)

    assert all(child.disabled for child in view.children)
    interaction.message.edit.assert_awaited_once()
    interaction.guild.voice_client.disconnect.assert_awaited_once()
    bot_mock.get_cog.return_value._cleanup_state.assert_called_once_with(interaction.guild.id)


@pytest.mark.asyncio
async def test_view_queue_button_sends_ephemeral_embed():
    bot_mock = make_bot()
    view = MusicControlView(bot=bot_mock)
    interaction = make_interaction()

    button = next(child for child in view.children if child.custom_id == "view_queue")
    await button.callback(interaction)

    _, kwargs = interaction.response.send_message.call_args
    assert kwargs["ephemeral"] is True
    assert kwargs["embed"].title == "📋 Cola de reproducción"


@pytest.mark.asyncio
async def test_button_callbacks_work_without_ctx():
    bot_mock = make_bot()
    view = MusicControlView(bot=bot_mock)
    assert view.ctx is None

    interaction = make_interaction()
    interaction.guild.voice_client.is_paused.return_value = False
    interaction.guild.voice_client.is_playing.return_value = True

    button = next(child for child in view.children if child.custom_id == "pause_resume")
    await button.callback(interaction)

    interaction.guild.voice_client.pause.assert_called_once()
    bot_mock.get_cog.return_value.update_activity.assert_called_once_with(interaction.guild)


@pytest.mark.asyncio
async def test_bot_add_view_called_during_startup():
    original_user = bot._connection.user
    original_guilds = bot._connection._guilds
    bot._connection.user = MagicMock(name="TestBot")
    bot._connection._guilds = {}
    try:
        with patch.object(bot, "add_view") as mock_add_view, \
             patch("bot._sync_app_commands", new_callable=AsyncMock), \
             patch.object(bot, "get_cog", return_value=make_music_cog()):
            await on_ready()

        mock_add_view.assert_called_once()
        view = mock_add_view.call_args[0][0]
        assert isinstance(view, MusicControlView)
        assert view.ctx is None
    finally:
        bot._connection.user = original_user
        bot._connection._guilds = original_guilds
