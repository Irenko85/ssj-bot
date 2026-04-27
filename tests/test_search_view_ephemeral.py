"""Tests for SearchView being ephemeral when invoked via slash."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cogs.music_cog import Music


@pytest.mark.asyncio
async def test_search_sends_ephemeral_view_when_invoked_via_slash():
    """When ctx.interaction is set (slash invocation), the view is ephemeral."""
    cog = Music.__new__(Music)
    cog.update_activity = MagicMock()
    cog._extract_info = AsyncMock(
        return_value={"entries": [{"title": "T", "id": "x"}]}
    )

    ctx = MagicMock()
    ctx.interaction = MagicMock()  # slash invocation
    ctx.send = AsyncMock()
    ctx.typing = MagicMock()
    ctx.typing.return_value.__aenter__ = AsyncMock()
    ctx.typing.return_value.__aexit__ = AsyncMock()
    ctx.defer = AsyncMock()

    await cog.search.callback(cog, ctx, query="d4vd")

    assert ctx.send.await_count == 1
    _, kwargs = ctx.send.call_args
    assert kwargs.get("ephemeral") is True


@pytest.mark.asyncio
async def test_search_sends_public_view_when_invoked_via_mention():
    """When ctx.interaction is None (mention invocation), the view is public."""
    cog = Music.__new__(Music)
    cog.update_activity = MagicMock()
    cog._extract_info = AsyncMock(
        return_value={"entries": [{"title": "T", "id": "x"}]}
    )

    ctx = MagicMock()
    ctx.interaction = None  # mention invocation
    ctx.send = AsyncMock()
    ctx.typing = MagicMock()
    ctx.typing.return_value.__aenter__ = AsyncMock()
    ctx.typing.return_value.__aexit__ = AsyncMock()
    ctx.defer = AsyncMock()

    await cog.search.callback(cog, ctx, query="d4vd")

    assert ctx.send.await_count == 1
    _, kwargs = ctx.send.call_args
    assert kwargs.get("ephemeral") is False
