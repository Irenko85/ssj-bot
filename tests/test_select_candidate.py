import pytest
from unittest.mock import AsyncMock, MagicMock
import yt_dlp
from cogs.music_cog import Music


@pytest.mark.asyncio
async def test_skips_unavailable_and_returns_next():
    bot = MagicMock()
    music = Music(bot)
    music._extract_info = AsyncMock(
        side_effect=[
            yt_dlp.utils.DownloadError("Video unavailable"),
            {"url": "https://ok", "title": "OK"},
        ]
    )
    ydl = MagicMock()
    entries = [{"id": "BAD"}, {"id": "GOOD"}]

    result = await music._select_first_playable_candidate(ydl, entries)

    assert result == {"url": "https://ok", "title": "OK"}
    assert music._extract_info.call_count == 2
