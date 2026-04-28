"""Tests for now-playing visual message flow (embed + MusicControlView)."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cogs.music_cog import Music
from utils.ui import MusicControlView


@pytest.mark.asyncio
async def test_play_next_sends_now_playing_message_when_missing():
    cog = Music.__new__(Music)
    cog.bot = MagicMock()
    cog.bot.loop = MagicMock()
    cog.states = {}
    cog.update_activity = MagicMock()

    ctx = MagicMock()
    ctx.guild = MagicMock(id=1)
    ctx.voice_client = MagicMock()
    ctx.voice_client.is_connected.return_value = True
    ctx.voice_client.play = MagicMock()
    ctx.send = AsyncMock(return_value=MagicMock())

    state = cog._state(ctx)
    state.queue = [
        {
            "title": "Cha-La Head-Cha-La",
            "url": "https://stream.example/audio",
            "source_url": "https://www.youtube.com/watch?v=YnL70cee6qo",
            "headers": {},
        }
    ]

    with patch("cogs.music_cog.discord.FFmpegOpusAudio", return_value=MagicMock()):
        await cog.play_next_in_queue(ctx)

    _, kwargs = ctx.send.call_args
    assert kwargs["embed"].title == "🎵 Ahora reproduciendo"
    assert isinstance(kwargs["view"], MusicControlView)
    assert state.now_playing_message is ctx.send.return_value


@pytest.mark.asyncio
async def test_play_next_deletes_existing_now_playing_message():
    cog = Music.__new__(Music)
    cog.bot = MagicMock()
    cog.bot.loop = MagicMock()
    cog.states = {}
    cog.update_activity = MagicMock()

    ctx = MagicMock()
    ctx.guild = MagicMock(id=1)
    ctx.voice_client = MagicMock()
    ctx.voice_client.is_connected.return_value = True
    ctx.voice_client.play = MagicMock()
    ctx.send = AsyncMock(return_value=MagicMock())

    state = cog._state(ctx)
    old_message = MagicMock()
    old_message.delete = AsyncMock()
    state.now_playing_message = old_message
    state.queue = [
        {
            "title": "Dan Dan Kokoro Hikareteku",
            "url": "https://stream.example/audio-2",
            "source_url": "https://www.youtube.com/watch?v=5LVcwPrfNo4",
            "headers": {},
        }
    ]

    with patch("cogs.music_cog.discord.FFmpegOpusAudio", return_value=MagicMock()):
        await cog.play_next_in_queue(ctx)

    old_message.delete.assert_awaited_once()
    ctx.send.assert_awaited_once()
    assert state.now_playing_message is ctx.send.return_value


@pytest.mark.asyncio
async def test_publish_now_playing_deletes_previous_message_and_sends_new_one():
    cog = Music.__new__(Music)
    cog.bot = MagicMock()
    cog.bot.loop = MagicMock()
    cog.states = {}

    ctx = MagicMock()
    ctx.guild = MagicMock(id=1)

    first_message = MagicMock()
    first_message.delete = AsyncMock()

    second_message = MagicMock()
    ctx.send = AsyncMock(return_value=second_message)

    state = cog._state(ctx)
    state.now_playing_message = first_message

    song = {
        "title": "Dan Dan Kokoro Hikareteku",
        "url": "https://stream.example/audio-2",
        "thumbnail": "https://cdn.example/np-thumb.jpg",
        "duration": 245,
        "webpage_url": "https://www.youtube.com/watch?v=5LVcwPrfNo4",
        "headers": {},
    }

    result = await cog._publish_now_playing(ctx, song)

    first_message.delete.assert_awaited_once()
    ctx.send.assert_awaited_once()
    assert state.now_playing_message is second_message
    assert result is second_message
