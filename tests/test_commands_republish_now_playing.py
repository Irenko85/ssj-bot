"""Tests that queue-manipulation commands re-publish the Now Playing message."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from cogs.music_cog import Music


# ------------------------------------------------------------------ queue --
@pytest.mark.asyncio
async def test_queue_repubishes_now_playing_when_song_is_playing():
    cog = Music.__new__(Music)
    cog.states = {}
    cog.update_activity = MagicMock()
    cog._publish_now_playing = AsyncMock()

    ctx = MagicMock()
    ctx.guild = MagicMock(id=1)
    ctx.send = AsyncMock()

    state = cog._state(ctx)
    state.actual_song = "Current Song"
    state.queue = [{"title": "Song 1"}]
    state.current_song = {"title": "Current Song"}

    await cog.queue.callback(cog, ctx)

    cog._publish_now_playing.assert_awaited_once_with(ctx, state.current_song)


@pytest.mark.asyncio
async def test_queue_does_not_repubish_when_no_song_is_playing():
    cog = Music.__new__(Music)
    cog.states = {}
    cog.update_activity = MagicMock()
    cog._publish_now_playing = AsyncMock()

    ctx = MagicMock()
    ctx.guild = MagicMock(id=1)
    ctx.send = AsyncMock()

    state = cog._state(ctx)
    state.actual_song = "Current Song"
    state.queue = [{"title": "Song 1"}]
    state.current_song = None

    await cog.queue.callback(cog, ctx)

    cog._publish_now_playing.assert_not_awaited()


# -------------------------------------------------------- remove_from_queue --
@pytest.mark.asyncio
async def test_remove_from_queue_repubishes_now_playing_when_song_is_playing():
    cog = Music.__new__(Music)
    cog.states = {}
    cog.update_activity = MagicMock()
    cog._publish_now_playing = AsyncMock()

    ctx = MagicMock()
    ctx.guild = MagicMock(id=1)
    ctx.send = AsyncMock()

    state = cog._state(ctx)
    state.queue = [{"title": "Song 1"}, {"title": "Song 2"}]
    state.current_song = {"title": "Current Song"}

    await cog.remove_from_queue.callback(cog, ctx, position=1)

    cog._publish_now_playing.assert_awaited_once_with(ctx, state.current_song)


@pytest.mark.asyncio
async def test_remove_from_queue_does_not_repubish_when_no_song_is_playing():
    cog = Music.__new__(Music)
    cog.states = {}
    cog.update_activity = MagicMock()
    cog._publish_now_playing = AsyncMock()

    ctx = MagicMock()
    ctx.guild = MagicMock(id=1)
    ctx.send = AsyncMock()

    state = cog._state(ctx)
    state.queue = [{"title": "Song 1"}, {"title": "Song 2"}]
    state.current_song = None

    await cog.remove_from_queue.callback(cog, ctx, position=1)

    cog._publish_now_playing.assert_not_awaited()


# ------------------------------------------------------------------ clear --
@pytest.mark.asyncio
async def test_clear_repubishes_now_playing_when_voice_client_is_playing():
    cog = Music.__new__(Music)
    cog.states = {}
    cog.update_activity = MagicMock()
    cog._publish_now_playing = AsyncMock()

    ctx = MagicMock()
    ctx.guild = MagicMock(id=1)
    ctx.voice_client = MagicMock()
    ctx.voice_client.is_playing.return_value = True
    ctx.send = AsyncMock()

    state = cog._state(ctx)
    state.queue = [{"title": "Song 1"}]
    state.current_song = {"title": "Current Song"}

    await cog.clear.callback(cog, ctx)

    cog._publish_now_playing.assert_awaited_once_with(ctx, state.current_song)


@pytest.mark.asyncio
async def test_clear_does_not_repubish_when_voice_client_is_not_playing():
    cog = Music.__new__(Music)
    cog.states = {}
    cog.update_activity = MagicMock()
    cog._publish_now_playing = AsyncMock()

    ctx = MagicMock()
    ctx.guild = MagicMock(id=1)
    ctx.voice_client = MagicMock()
    ctx.voice_client.is_playing.return_value = False
    ctx.send = AsyncMock()

    state = cog._state(ctx)
    state.queue = [{"title": "Song 1"}]
    state.current_song = {"title": "Current Song"}

    await cog.clear.callback(cog, ctx)

    cog._publish_now_playing.assert_not_awaited()


@pytest.mark.asyncio
async def test_clear_does_not_repubish_when_no_voice_client():
    cog = Music.__new__(Music)
    cog.states = {}
    cog.update_activity = MagicMock()
    cog._publish_now_playing = AsyncMock()

    ctx = MagicMock()
    ctx.guild = MagicMock(id=1)
    ctx.voice_client = None
    ctx.send = AsyncMock()

    state = cog._state(ctx)
    state.queue = [{"title": "Song 1"}]
    state.current_song = {"title": "Current Song"}

    await cog.clear.callback(cog, ctx)

    cog._publish_now_playing.assert_not_awaited()


# ---------------------------------------------------------------- shuffle --
@pytest.mark.asyncio
async def test_shuffle_repubishes_now_playing_when_song_is_playing():
    cog = Music.__new__(Music)
    cog.states = {}
    cog.update_activity = MagicMock()
    cog._publish_now_playing = AsyncMock()
    cog.bot = MagicMock()
    cog.bot.get_command.return_value = MagicMock()

    ctx = MagicMock()
    ctx.guild = MagicMock(id=1)
    ctx.invoke = AsyncMock()
    ctx.send = AsyncMock()

    state = cog._state(ctx)
    state.queue = [{"title": "Song 1"}, {"title": "Song 2"}]
    state.current_song = {"title": "Current Song"}

    await cog.shuffle.callback(cog, ctx)

    cog._publish_now_playing.assert_awaited_once_with(ctx, state.current_song)


@pytest.mark.asyncio
async def test_shuffle_does_not_repubish_when_no_song_is_playing():
    cog = Music.__new__(Music)
    cog.states = {}
    cog.update_activity = MagicMock()
    cog._publish_now_playing = AsyncMock()
    cog.bot = MagicMock()
    cog.bot.get_command.return_value = MagicMock()

    ctx = MagicMock()
    ctx.guild = MagicMock(id=1)
    ctx.invoke = AsyncMock()
    ctx.send = AsyncMock()

    state = cog._state(ctx)
    state.queue = [{"title": "Song 1"}, {"title": "Song 2"}]
    state.current_song = None

    await cog.shuffle.callback(cog, ctx)

    cog._publish_now_playing.assert_not_awaited()
