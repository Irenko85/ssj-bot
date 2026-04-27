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
async def test_other_errors_are_reraised():
    """Non-CommandNotFound errors should propagate."""
    ctx = MagicMock()
    ctx.send = AsyncMock()
    error = commands.CommandInvokeError(RuntimeError("boom"))

    with pytest.raises(commands.CommandInvokeError):
        await handle_command_error(ctx, error)
