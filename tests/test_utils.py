"""Tests for utils.get_video_urls_from_playlist."""
from unittest.mock import MagicMock, patch

import pytest

from utils import utils


@pytest.mark.asyncio
async def test_returns_video_urls():
    fake_info = {
        "entries": [
            {"id": "abc123"},
            {"id": "def456"},
            {"id": "ghi789"},
        ]
    }

    with patch("utils.utils.yt_dlp.YoutubeDL") as YDL:
        ydl_instance = MagicMock()
        ydl_instance.extract_info.return_value = fake_info
        YDL.return_value.__enter__.return_value = ydl_instance

        result = await utils.get_video_urls_from_playlist(
            "https://www.youtube.com/playlist?list=PLfake"
        )

    assert result == [
        "https://www.youtube.com/watch?v=abc123",
        "https://www.youtube.com/watch?v=def456",
        "https://www.youtube.com/watch?v=ghi789",
    ]


@pytest.mark.asyncio
async def test_returns_empty_on_error():
    with patch("utils.utils.yt_dlp.YoutubeDL") as YDL:
        ydl_instance = MagicMock()
        ydl_instance.extract_info.side_effect = RuntimeError("network down")
        YDL.return_value.__enter__.return_value = ydl_instance

        result = await utils.get_video_urls_from_playlist(
            "https://www.youtube.com/playlist?list=PLfake"
        )

    assert result == []
