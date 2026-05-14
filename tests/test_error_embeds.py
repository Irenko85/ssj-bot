"""Tests verifying error and warning messages use embeds instead of plain text.

Phase RED — current code sends plain text; these tests assert embed= is used,
so they MUST fail until music_cog.py is updated to use build_error_embed,
build_warning_embed, or build_info_embed.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cogs.music_cog import Music


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _assert_sent_error_embed(send_mock):
    """Assert that send was called with an error embed (title='❌ Error')."""
    send_mock.assert_awaited_once()
    kwargs = send_mock.call_args.kwargs
    assert "embed" in kwargs, (
        f"Expected embed= in send, got args={send_mock.call_args.args!r}"
    )
    embed = kwargs["embed"]
    assert embed.title == "\u274c Error", (
        f"Expected error embed title '\u274c Error', got {embed.title!r}"
    )


def _assert_sent_warning_or_info_embed(send_mock):
    """Assert that send was called with an embed (not plain text)."""
    send_mock.assert_awaited_once()
    kwargs = send_mock.call_args.kwargs
    assert "embed" in kwargs, (
        f"Expected embed= in send, got args={send_mock.call_args.args!r}"
    )


# ---------------------------------------------------------------------------
# Test C — Warning "no hay nada reproduciendo" (skip / pause sin música)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_skip_no_voice_client_sends_warning_embed():
    """!skip sin voice_client → debe enviar embed de aviso."""
    cog = Music.__new__(Music)
    cog.update_activity = MagicMock()

    ctx = MagicMock()
    ctx.voice_client = None
    ctx.send = AsyncMock()

    await cog.skip.callback(cog, ctx)

    _assert_sent_warning_or_info_embed(ctx.send)


@pytest.mark.asyncio
async def test_skip_not_playing_sends_warning_embed():
    """!skip con voice_client pero sin reproducción → embed de aviso."""
    cog = Music.__new__(Music)
    cog.update_activity = MagicMock()

    ctx = MagicMock()
    ctx.voice_client = MagicMock()
    ctx.voice_client.playing = False
    ctx.send = AsyncMock()

    await cog.skip.callback(cog, ctx)

    _assert_sent_warning_or_info_embed(ctx.send)


@pytest.mark.asyncio
async def test_pause_no_voice_client_sends_warning_embed():
    """!pause sin voice_client → debe enviar embed de aviso."""
    cog = Music.__new__(Music)
    cog.update_activity = MagicMock()

    ctx = MagicMock()
    ctx.voice_client = None
    ctx.send = AsyncMock()

    await cog.pause.callback(cog, ctx)

    _assert_sent_warning_or_info_embed(ctx.send)


@pytest.mark.asyncio
async def test_pause_not_playing_sends_warning_embed():
    """!pause con voice_client pero sin reproducción → embed de aviso."""
    cog = Music.__new__(Music)
    cog.update_activity = MagicMock()

    ctx = MagicMock()
    ctx.voice_client = MagicMock()
    ctx.voice_client.playing = False
    ctx.send = AsyncMock()

    await cog.pause.callback(cog, ctx)

    _assert_sent_warning_or_info_embed(ctx.send)


# ---------------------------------------------------------------------------
# Extras — otros casos de texto plano que deberían ser embeds
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stop_happy_path_uses_info_embed():
    """!stop exitoso debe usar embed (info), no texto plano."""
    cog = Music.__new__(Music)
    cog._text_channels = {}

    ctx = MagicMock()
    ctx.guild = MagicMock(id=1)
    ctx.voice_client = MagicMock()
    ctx.voice_client.stop = AsyncMock()
    ctx.voice_client.disconnect = AsyncMock()
    ctx.send = AsyncMock()

    await cog.stop.callback(cog, ctx)

    ctx.send.assert_awaited_once()
    kwargs = ctx.send.call_args.kwargs
    assert "embed" in kwargs, (
        f"Expected embed= in stop, got args={ctx.send.call_args.args!r}"
    )
    # The embed doesn't have to be an error embed here; just not plain text
    assert hasattr(kwargs["embed"], "title"), "stop message should be an Embed"


@pytest.mark.asyncio
async def test_resume_no_voice_client_sends_warning_embed():
    """!resume sin voice_client → debe enviar embed de aviso."""
    cog = Music.__new__(Music)
    cog.update_activity = MagicMock()

    ctx = MagicMock()
    ctx.voice_client = None
    ctx.send = AsyncMock()

    await cog.resume.callback(cog, ctx)

    _assert_sent_warning_or_info_embed(ctx.send)


@pytest.mark.asyncio
async def test_resume_with_player_sends_info_embed():
    """!resume con player existente → debe enviar embed de info."""
    cog = Music.__new__(Music)
    cog.update_activity = MagicMock()

    ctx = MagicMock()
    ctx.voice_client = MagicMock()
    ctx.voice_client.pause = AsyncMock()
    ctx.send = AsyncMock()

    await cog.resume.callback(cog, ctx)

    _assert_sent_warning_or_info_embed(ctx.send)
