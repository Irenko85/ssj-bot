from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from bot import bot
from utils.ui import MusicControlView, make_music_control_view


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


def test_factory_returns_fresh_instance():
    bot_mock = make_bot()
    v1 = make_music_control_view(bot_mock)
    v2 = make_music_control_view(bot_mock)
    assert v1 is not v2
    assert isinstance(v1, MusicControlView)
    assert isinstance(v2, MusicControlView)


def test_factory_sets_paused_state():
    bot_mock = make_bot()
    view = make_music_control_view(bot_mock, paused=True)
    pause_button = next(child for child in view.children if child.custom_id == "pause_resume")
    assert str(pause_button.emoji) == "▶️"


def test_factory_sets_disabled_state():
    bot_mock = make_bot()
    view = make_music_control_view(bot_mock, disabled=True)
    assert all(child.disabled for child in view.children)


@pytest.mark.asyncio
async def test_pause_resume_button_pauses_and_edits_message_with_fresh_view():
    bot_mock = make_bot()
    view = MusicControlView(bot=bot_mock)
    interaction = make_interaction()
    interaction.guild.voice_client.is_paused.return_value = False
    interaction.guild.voice_client.is_playing.return_value = True

    button = next(child for child in view.children if child.custom_id == "pause_resume")
    await button.callback(interaction)

    interaction.guild.voice_client.pause.assert_called_once()
    # Singleton must NOT be mutated
    assert str(button.emoji) == "⏸"
    interaction.message.edit.assert_awaited_once()
    interaction.response.send_message.assert_awaited_once()
    bot_mock.get_cog.return_value.update_activity.assert_called_once_with(interaction.guild)

    # The fresh view passed to edit must have the paused emoji
    _, kwargs = interaction.message.edit.call_args
    fresh_view = kwargs["view"]
    pause_button = next(
        child for child in fresh_view.children if child.custom_id == "pause_resume"
    )
    assert str(pause_button.emoji) == "▶️"


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

    # Singleton must NOT be mutated
    assert not any(child.disabled for child in view.children)
    interaction.message.edit.assert_awaited_once()
    interaction.guild.voice_client.disconnect.assert_awaited_once()
    bot_mock.get_cog.return_value._cleanup_state.assert_called_once_with(interaction.guild.id)

    # The fresh view passed to edit must have all buttons disabled
    _, kwargs = interaction.message.edit.call_args
    fresh_view = kwargs["view"]
    assert all(child.disabled for child in fresh_view.children)


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

    interaction = make_interaction()
    interaction.guild.voice_client.is_paused.return_value = False
    interaction.guild.voice_client.is_playing.return_value = True

    button = next(child for child in view.children if child.custom_id == "pause_resume")
    await button.callback(interaction)

    interaction.guild.voice_client.pause.assert_called_once()
    bot_mock.get_cog.return_value.update_activity.assert_called_once_with(interaction.guild)


@pytest.mark.asyncio
async def test_bot_add_view_called_during_setup_hook():
    with patch.object(bot, "add_view") as mock_add_view, \
         patch.object(bot, "get_cog", return_value=make_music_cog()):
        await bot.setup_hook()

    mock_add_view.assert_called_once()
    view = mock_add_view.call_args[0][0]
    assert isinstance(view, MusicControlView)
