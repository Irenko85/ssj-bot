"""Tests for global on_command_error handler silencing CommandNotFound."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from discord.ext import commands

from bot import handle_command_error


@pytest.mark.asyncio
async def test_command_not_found_is_silenced():
    """CommandNotFound should be ignored (no raise, no send)."""
    ctx = MagicMock()
    ctx.send = AsyncMock()
    error = commands.CommandNotFound('Command "d" is not found')

    # Should not raise
    await handle_command_error(ctx, error)

    ctx.send.assert_not_called()


@pytest.mark.asyncio
async def test_command_invoke_error_sends_embed():
    """CommandInvokeError should send an error embed instead of propagating."""
    ctx = MagicMock()
    ctx.send = AsyncMock()
    error = commands.CommandInvokeError(RuntimeError("boom"))

    await handle_command_error(ctx, error)

    ctx.send.assert_called_once()
    _, kwargs = ctx.send.call_args
    assert "embed" in kwargs
