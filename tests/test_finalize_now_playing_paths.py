"""Tests verifying _finalize_now_playing is called in stop, inactivity, and empty channel paths."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cogs.music_cog import Music


@pytest.mark.asyncio
async def test_stop_disables_now_playing_buttons():
    """!stop must call _finalize_now_playing, disabling the message buttons."""
    cog = Music.__new__(Music)
    cog.bot = MagicMock()
    cog.states = {}
    cog._cleanup_state = MagicMock()

    ctx = MagicMock()
    ctx.guild = MagicMock(id=1)
    ctx.voice_client = MagicMock()
    ctx.voice_client.stop = MagicMock()
    ctx.voice_client.disconnect = AsyncMock()
    ctx.send = AsyncMock()

    state = cog._state(ctx)
    state.now_playing_message = MagicMock()
    state.now_playing_message.edit = AsyncMock()

    await cog.stop.callback(cog, ctx)

    state.now_playing_message.edit.assert_awaited_once()
    kwargs = state.now_playing_message.edit.call_args.kwargs
    assert "view" in kwargs, "edit must receive a fresh view"
    assert all(child.disabled for child in kwargs["view"].children), (
        "all buttons in the view must be disabled"
    )


@pytest.mark.asyncio
@patch("cogs.music_cog.time", return_value=1000.0)
async def test_inactivity_disconnect_disables_now_playing_buttons(mock_time):
    """Inactivity timeout must finalize the Now Playing message before cleanup."""
    cog = Music.__new__(Music)
    cog.bot = MagicMock()
    cog.states = {}

    guild_id = 1
    guild = MagicMock(id=guild_id)

    voice_client = MagicMock()
    voice_client.is_connected.return_value = True
    voice_client.is_playing.return_value = False
    voice_client.is_paused.return_value = False
    voice_client.disconnect = AsyncMock()

    member = MagicMock()
    member.bot = False
    voice_client.channel = MagicMock()
    voice_client.channel.members = [member]
    voice_client.guild = guild

    cog.bot.get_guild.return_value = guild
    cog.bot.voice_clients = [voice_client]

    state = cog._state(guild)
    state.last_activity = 699.0          # 301s before time()
    state.inactivity_warned = True
    state.inactivity_channel = MagicMock()
    state.inactivity_channel.send = AsyncMock()
    state.queue = []
    state.now_playing_message = MagicMock()
    state.now_playing_message.edit = AsyncMock()

    await cog.check_inactivity()

    state.now_playing_message.edit.assert_awaited_once()
    kwargs = state.now_playing_message.edit.call_args.kwargs
    assert "view" in kwargs
    assert all(child.disabled for child in kwargs["view"].children)


@pytest.mark.asyncio
@patch("cogs.music_cog.time", return_value=1000.0)
async def test_empty_channel_disconnect_disables_now_playing_buttons(mock_time):
    """Empty channel disconnect must finalize the Now Playing message before cleanup."""
    cog = Music.__new__(Music)
    cog.bot = MagicMock()
    cog.states = {}

    guild_id = 1
    guild = MagicMock(id=guild_id)

    voice_client = MagicMock()
    voice_client.is_connected.return_value = True
    voice_client.is_playing.return_value = False
    voice_client.is_paused.return_value = False
    voice_client.disconnect = AsyncMock()

    voice_client.channel = MagicMock()
    voice_client.channel.members = []    # no non-bot members
    voice_client.guild = guild

    cog.bot.get_guild.return_value = guild
    cog.bot.voice_clients = [voice_client]

    state = cog._state(guild)
    state.last_activity = 500.0
    state.inactivity_warned = False
    state.inactivity_channel = MagicMock()
    state.inactivity_channel.send = AsyncMock()
    state.queue = []
    state.now_playing_message = MagicMock()
    state.now_playing_message.edit = AsyncMock()

    await cog.check_inactivity()

    state.now_playing_message.edit.assert_awaited_once()
    kwargs = state.now_playing_message.edit.call_args.kwargs
    assert "view" in kwargs
    assert all(child.disabled for child in kwargs["view"].children)
