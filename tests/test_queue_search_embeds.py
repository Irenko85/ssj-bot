"""Tests for visual embed usage in play-internal, queue, and search flows.

RED phase — these tests assert that ctx.send uses embed=build_*_embed(...)
instead of plain text.  The current implementation uses f-strings / text only,
so every test below must FAIL.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cogs.music_cog import Music


# ------------------------------------------------------------------ Test A --
@pytest.mark.asyncio
async def test_play_internal_adds_to_queue_with_embed():
    """When a song is added while voice_client is already playing,
    ctx.send must be called with embed=build_added_to_queue_embed(...)."""
    cog = Music.__new__(Music)
    cog.states = {}
    cog.bot = MagicMock()
    cog.update_activity = MagicMock()
    cog.start_inactivity_check = MagicMock()
    cog.play_next_in_queue = AsyncMock()
    cog.join_voice_channel = AsyncMock(return_value=True)
    cog._extract_info = AsyncMock(
        return_value={
            "entries": [{"id": "abc", "title": "Test Song", "ie_key": "Youtube"}]
        }
    )
    cog._select_first_playable_candidate = AsyncMock(
        return_value={"url": "https://stream.example/audio", "title": "Test Song"}
    )
    cog._extract_http_headers = MagicMock(return_value={})

    ctx = MagicMock()
    ctx.guild = MagicMock(id=1)
    ctx.author = MagicMock()
    ctx.author.voice = MagicMock()
    ctx.author.voice.channel = MagicMock()
    ctx.voice_client = MagicMock()
    ctx.voice_client.is_connected.return_value = True
    ctx.voice_client.is_playing.return_value = True  # already playing
    ctx.send = AsyncMock()
    ctx.typing = MagicMock()
    ctx.typing.return_value.__aenter__ = AsyncMock()
    ctx.typing.return_value.__aexit__ = AsyncMock()

    with patch("cogs.music_cog.SafeYoutubeDL") as ydl_class:
        ydl_instance = MagicMock()
        ydl_class.return_value.__enter__ = MagicMock(return_value=ydl_instance)
        ydl_class.return_value.__exit__ = MagicMock(return_value=False)

        with patch("cogs.music_cog.YTDL_OPTIONS", {}):
            await cog._play_internal(ctx, "test song", silent=False)

    _, kwargs = ctx.send.call_args
    assert "embed" in kwargs, (
        "ctx.send should use embed=build_added_to_queue_embed(...), "
        "not plain text"
    )


# ------------------------------------------------------------------ Test B --
@pytest.mark.asyncio
async def test_queue_command_uses_build_queue_embed():
    """When the queue has songs, ctx.send must be called with
    embed=build_queue_embed(...), not an f-string."""
    cog = Music.__new__(Music)
    cog.states = {}
    cog.update_activity = MagicMock()

    ctx = MagicMock()
    ctx.guild = MagicMock(id=1)
    ctx.send = AsyncMock()

    state = cog._state(ctx)
    state.actual_song = "Current Song"
    state.queue = [{"title": "Song 1"}, {"title": "Song 2"}]

    await cog.queue.callback(cog, ctx)

    _, kwargs = ctx.send.call_args
    assert "embed" in kwargs, (
        "ctx.send should use embed=build_queue_embed(...), not an f-string"
    )


# ------------------------------------------------------------------ Test C --
@pytest.mark.asyncio
async def test_search_command_uses_build_search_results_embed():
    """When search returns results, ctx.send must be called with
    embed=build_search_results_embed(...)."""
    cog = Music.__new__(Music)
    cog.update_activity = MagicMock()
    cog._extract_info = AsyncMock(
        return_value={"entries": [{"title": "Result 1", "id": "abc"}]}
    )

    ctx = MagicMock()
    ctx.interaction = None
    ctx.send = AsyncMock()
    ctx.typing = MagicMock()
    ctx.typing.return_value.__aenter__ = AsyncMock()
    ctx.typing.return_value.__aexit__ = AsyncMock()
    ctx.defer = AsyncMock()

    with patch("cogs.music_cog.SafeYoutubeDL") as ydl_class:
        ydl_instance = MagicMock()
        ydl_class.return_value.__enter__ = MagicMock(return_value=ydl_instance)
        ydl_class.return_value.__exit__ = MagicMock(return_value=False)

        await cog.search.callback(cog, ctx, query="test")

    _, kwargs = ctx.send.call_args
    assert "embed" in kwargs, (
        "ctx.send should use embed=build_search_results_embed(...)"
    )


# ------------------------------------------------------------------ Test D --
@pytest.mark.asyncio
async def test_search_command_handles_extract_info_exception():
    """When _extract_info raises, ctx.send must be called with the error
    message and no UnboundLocalError must occur."""
    cog = Music.__new__(Music)
    cog.update_activity = MagicMock()
    cog._extract_info = AsyncMock(side_effect=Exception("yt-dlp error"))

    ctx = MagicMock()
    ctx.interaction = None
    ctx.send = AsyncMock()
    ctx.typing = MagicMock()
    ctx.typing.return_value.__aenter__ = AsyncMock()
    ctx.typing.return_value.__aexit__ = AsyncMock()
    ctx.defer = AsyncMock()

    with patch("cogs.music_cog.SafeYoutubeDL") as ydl_class:
        ydl_instance = MagicMock()
        ydl_class.return_value.__enter__ = MagicMock(return_value=ydl_instance)
        ydl_class.return_value.__exit__ = MagicMock(return_value=False)

        await cog.search.callback(cog, ctx, query="test")

    assert ctx.send.call_count == 1, (
        "Only one send call should happen when extract_info raises"
    )
    _, kwargs = ctx.send.call_args
    assert "embed" in kwargs, (
        "ctx.send should use embed=build_error_embed(...), not plain text"
    )
