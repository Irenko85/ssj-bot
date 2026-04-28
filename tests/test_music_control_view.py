from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

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


def make_ctx():
    ctx = MagicMock()
    ctx.guild = MagicMock(id=1)
    ctx.interaction = MagicMock()
    return ctx


def make_music_cog():
    music_cog = MagicMock()
    music_cog._state = MagicMock(
        return_value=MagicMock(queue=[{"title": "Song 1"}], actual_song="Song 0")
    )
    music_cog.update_activity = MagicMock()
    music_cog._cleanup_state = MagicMock()
    return music_cog


def test_music_control_view_has_expected_buttons():
    view = MusicControlView(make_music_cog(), make_ctx())

    custom_ids = [child.custom_id for child in view.children]
    assert custom_ids == ["pause_resume", "skip", "stop", "view_queue"]


@pytest.mark.asyncio
async def test_pause_resume_button_pauses_and_flips_emoji():
    view = MusicControlView(make_music_cog(), make_ctx())
    interaction = make_interaction()
    interaction.guild.voice_client.is_paused.return_value = False
    interaction.guild.voice_client.is_playing.return_value = True

    button = next(child for child in view.children if child.custom_id == "pause_resume")
    await button.callback(interaction)

    interaction.guild.voice_client.pause.assert_called_once()
    assert str(button.emoji) == "▶️"
    interaction.response.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_stop_button_disables_all_buttons_and_edits_message():
    view = MusicControlView(make_music_cog(), make_ctx())
    interaction = make_interaction()
    interaction.guild.voice_client.is_connected.return_value = True
    interaction.guild.voice_client.is_playing.return_value = True

    button = next(child for child in view.children if child.custom_id == "stop")
    await button.callback(interaction)

    assert all(child.disabled for child in view.children)
    interaction.message.edit.assert_awaited_once()
    interaction.guild.voice_client.disconnect.assert_awaited_once()


@pytest.mark.asyncio
async def test_view_queue_button_sends_ephemeral_embed():
    view = MusicControlView(make_music_cog(), make_ctx())
    interaction = make_interaction()

    button = next(child for child in view.children if child.custom_id == "view_queue")
    await button.callback(interaction)

    _, kwargs = interaction.response.send_message.call_args
    assert kwargs["ephemeral"] is True
    assert kwargs["embed"].title == "📋 Cola de reproducción"
