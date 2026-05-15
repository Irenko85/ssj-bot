"""Tests for skip/pause/resume providing feedback when no-op."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from cogs.music_cog import Music


@pytest.mark.asyncio
async def test_skip_sends_feedback_when_no_voice_client():
    cog = Music.__new__(Music)
    cog.update_activity = MagicMock()

    ctx = MagicMock()
    ctx.voice_client = None
    ctx.send = AsyncMock()

    await cog.skip.callback(cog, ctx)

    ctx.send.assert_awaited_once()
    assert "embed" in ctx.send.call_args.kwargs


@pytest.mark.asyncio
async def test_skip_sends_feedback_when_not_playing():
    cog = Music.__new__(Music)
    cog.update_activity = MagicMock()

    ctx = MagicMock()
    ctx.voice_client = MagicMock()
    ctx.voice_client.playing = False
    ctx.send = AsyncMock()

    await cog.skip.callback(cog, ctx)

    ctx.send.assert_awaited_once()
    assert "embed" in ctx.send.call_args.kwargs


@pytest.mark.asyncio
async def test_pause_sends_feedback_when_no_voice_client():
    cog = Music.__new__(Music)
    cog.update_activity = MagicMock()

    ctx = MagicMock()
    ctx.voice_client = None
    ctx.send = AsyncMock()

    await cog.pause.callback(cog, ctx)

    ctx.send.assert_awaited_once()
    assert "embed" in ctx.send.call_args.kwargs


@pytest.mark.asyncio
async def test_pause_sends_feedback_when_not_playing():
    cog = Music.__new__(Music)
    cog.update_activity = MagicMock()

    ctx = MagicMock()
    ctx.voice_client = MagicMock()
    ctx.voice_client.playing = False
    ctx.send = AsyncMock()

    await cog.pause.callback(cog, ctx)

    ctx.send.assert_awaited_once()
    assert "embed" in ctx.send.call_args.kwargs


@pytest.mark.asyncio
async def test_resume_sends_feedback_when_no_voice_client():
    cog = Music.__new__(Music)
    cog.update_activity = MagicMock()

    ctx = MagicMock()
    ctx.voice_client = None
    ctx.send = AsyncMock()

    await cog.resume.callback(cog, ctx)

    ctx.send.assert_awaited_once()
    assert "embed" in ctx.send.call_args.kwargs


@pytest.mark.asyncio
async def test_resume_sends_feedback_when_player_exists():
    """Resume now always sends an info embed when a player exists."""
    cog = Music.__new__(Music)
    cog.update_activity = MagicMock()

    ctx = MagicMock()
    ctx.voice_client = MagicMock()
    ctx.voice_client.pause = AsyncMock()
    ctx.send = AsyncMock()

    await cog.resume.callback(cog, ctx)

    ctx.send.assert_awaited_once()
    assert "embed" in ctx.send.call_args.kwargs


@pytest.mark.asyncio
async def test_skip_still_works_when_playing():
    """Regression: ensure happy path is preserved."""
    cog = Music.__new__(Music)
    cog.update_activity = MagicMock()

    ctx = MagicMock()
    ctx.guild = MagicMock(id=1)
    ctx.voice_client = MagicMock()
    ctx.voice_client.playing = True
    ctx.voice_client.skip = AsyncMock()
    ctx.send = AsyncMock()

    await cog.skip.callback(cog, ctx)

    ctx.voice_client.skip.assert_awaited_once()
    ctx.send.assert_awaited_once()
    assert "embed" in ctx.send.call_args.kwargs
