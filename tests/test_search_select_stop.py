"""Tests for SearchSelect.callback correctly stopping the parent view."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cogs.music_cog import SearchSelect


@pytest.mark.asyncio
async def test_search_select_callback_calls_view_stop():
    """SearchSelect.callback must call self.view.stop(), not self.stop()."""
    entries = [{"title": "Song A", "id": "abc123"}]

    music_cog = MagicMock()
    music_cog._extract_info = AsyncMock(
        return_value={"url": "https://stream.url", "http_headers": {}}
    )
    music_cog._extract_http_headers = MagicMock(return_value={})
    music_cog._state = MagicMock(return_value=MagicMock(queue=[]))
    music_cog.update_activity = MagicMock()
    music_cog.join_voice_channel = AsyncMock()
    music_cog.play_next_in_queue = AsyncMock()

    ctx = MagicMock()
    ctx.voice_client = MagicMock()
    ctx.voice_client.is_connected = MagicMock(return_value=True)
    ctx.voice_client.is_playing = MagicMock(return_value=False)

    select = SearchSelect(entries, music_cog, ctx)
    select._values = ["0"]  # simulate user selection

    # Mock the parent view with a spy on stop()
    view_mock = MagicMock()
    view_mock.stop = MagicMock()
    # discord.ui.Item.view is a property; patch via __dict__ won't work,
    # so we patch the descriptor on the instance via object.__setattr__ no-op
    # and use a different approach: monkeypatch the View attribute directly.
    # discord.py exposes self.view through the parent; we set it through _view.
    # Looking at discord.py source, Item.view returns self._view (an internal).
    # Safest: patch the property at class level with mock.patch.object.
    interaction = MagicMock()
    interaction.response = MagicMock()
    interaction.response.send_message = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    interaction.message = MagicMock()
    interaction.message.delete = AsyncMock()

    with patch.object(
        type(select), "view", new_callable=lambda: property(lambda self: view_mock)
    ):
        with patch("cogs.music_cog.SafeYoutubeDL") as ydl_class:
            ydl_instance = MagicMock()
            ydl_class.return_value.__enter__ = MagicMock(return_value=ydl_instance)
            ydl_class.return_value.__exit__ = MagicMock(return_value=False)

            await select.callback(interaction)

    view_mock.stop.assert_called_once()


@pytest.mark.asyncio
async def test_search_select_callback_does_not_raise_attribute_error():
    """SearchSelect.callback must complete without AttributeError on stop()."""
    entries = [{"title": "Song A", "id": "abc123"}]

    music_cog = MagicMock()
    music_cog._extract_info = AsyncMock(
        return_value={"url": "https://stream.url", "http_headers": {}}
    )
    music_cog._extract_http_headers = MagicMock(return_value={})
    music_cog._state = MagicMock(return_value=MagicMock(queue=[]))
    music_cog.update_activity = MagicMock()
    music_cog.join_voice_channel = AsyncMock()
    music_cog.play_next_in_queue = AsyncMock()

    ctx = MagicMock()
    ctx.voice_client = MagicMock()
    ctx.voice_client.is_connected = MagicMock(return_value=True)
    ctx.voice_client.is_playing = MagicMock(return_value=False)

    select = SearchSelect(entries, music_cog, ctx)
    select._values = ["0"]

    view_mock = MagicMock()
    interaction = MagicMock()
    interaction.response = MagicMock()
    interaction.response.send_message = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    interaction.message = MagicMock()
    interaction.message.delete = AsyncMock()

    with patch.object(
        type(select), "view", new_callable=lambda: property(lambda self: view_mock)
    ):
        with patch("cogs.music_cog.SafeYoutubeDL") as ydl_class:
            ydl_instance = MagicMock()
            ydl_class.return_value.__enter__ = MagicMock(return_value=ydl_instance)
            ydl_class.return_value.__exit__ = MagicMock(return_value=False)

            # If self.stop() is still in code, this raises AttributeError.
            await select.callback(interaction)


@pytest.mark.asyncio
async def test_search_select_callback_sends_embed_on_success():
    """SearchSelect.callback must send an embed when adding song to queue."""
    entries = [{"title": "Song A", "id": "abc123"}]

    music_cog = MagicMock()
    music_cog._extract_info = AsyncMock(
        return_value={"url": "https://stream.url", "http_headers": {}}
    )
    music_cog._extract_http_headers = MagicMock(return_value={})
    music_cog._state = MagicMock(return_value=MagicMock(queue=[]))
    music_cog.update_activity = MagicMock()
    music_cog.join_voice_channel = AsyncMock()
    music_cog.play_next_in_queue = AsyncMock()

    ctx = MagicMock()
    ctx.voice_client = MagicMock()
    ctx.voice_client.is_connected = MagicMock(return_value=True)
    ctx.voice_client.is_playing = MagicMock(return_value=False)

    select = SearchSelect(entries, music_cog, ctx)
    select._values = ["0"]

    view_mock = MagicMock()
    interaction = MagicMock()
    interaction.response = MagicMock()
    interaction.response.send_message = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    interaction.message = MagicMock()
    interaction.message.delete = AsyncMock()

    with patch.object(
        type(select), "view", new_callable=lambda: property(lambda self: view_mock)
    ):
        with patch("cogs.music_cog.SafeYoutubeDL") as ydl_class:
            ydl_instance = MagicMock()
            ydl_class.return_value.__enter__ = MagicMock(return_value=ydl_instance)
            ydl_class.return_value.__exit__ = MagicMock(return_value=False)

            await select.callback(interaction)

    interaction.response.send_message.assert_awaited()
    _, kwargs = interaction.response.send_message.call_args
    assert "embed" in kwargs, "Expected embed= in response.send_message"
    embed = kwargs["embed"]
    assert hasattr(embed, "title"), "Expected an Embed object"
