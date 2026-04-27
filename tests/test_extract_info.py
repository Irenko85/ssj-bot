"""Tests for Music._extract_info async helper."""
import asyncio
import threading
from unittest.mock import Mock

import pytest

from cogs.music_cog import Music


def _make_cog():
    """Instantiate Music cog with a mock bot, bypassing discord setup."""
    bot = Mock()
    return Music(bot)


@pytest.mark.asyncio
async def test_extract_info_runs_in_worker_thread():
    cog = _make_cog()
    main_thread_id = threading.get_ident()
    captured_thread_id = {}

    def fake_extract(*args, **kwargs):
        captured_thread_id["id"] = threading.get_ident()
        return {"title": "x"}

    fake_ydl = Mock()
    fake_ydl.extract_info = fake_extract

    await cog._extract_info(fake_ydl, "https://example.com")

    assert captured_thread_id["id"] != main_thread_id


@pytest.mark.asyncio
async def test_extract_info_returns_value():
    cog = _make_cog()
    fake_ydl = Mock()
    fake_ydl.extract_info = Mock(return_value={"title": "song", "url": "u"})

    result = await cog._extract_info(fake_ydl, "https://example.com")

    assert result == {"title": "song", "url": "u"}
    fake_ydl.extract_info.assert_called_once_with("https://example.com")
