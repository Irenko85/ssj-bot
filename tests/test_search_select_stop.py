"""Tests for SearchSelect.callback correctly stopping the parent view."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cogs.music_cog import Music, SearchSelect


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
    music_cog.join_voice_channel = AsyncMock(return_value=True)
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
    interaction.response.defer = AsyncMock()
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
    music_cog.join_voice_channel = AsyncMock(return_value=True)
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
    interaction.response.defer = AsyncMock()
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
    music_cog.join_voice_channel = AsyncMock(return_value=True)
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
    interaction.response.defer = AsyncMock()
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

    interaction.followup.send.assert_awaited()
    _, kwargs = interaction.followup.send.call_args
    assert "embed" in kwargs, "Expected embed= in followup.send"
    embed = kwargs["embed"]
    assert "Añadido a la cola" in embed.title, f"Expected success title, got: {embed.title}"
    assert "Song A" in embed.description, f"Expected song title in description, got: {embed.description}"


@pytest.mark.asyncio
async def test_search_select_callback_without_user_in_voice_channel_sends_error_embed_song_not_added():
    """When the user is not in a voice channel, SearchSelect.callback must send
    an error embed (via join_voice_channel) and must NOT add the song to the queue."""
    entries = [{"title": "Song A", "id": "abc123"}]
    queue = []

    music_cog = MagicMock()
    music_cog._extract_info = AsyncMock(
        return_value={"url": "https://stream.url", "http_headers": {}}
    )
    music_cog._extract_http_headers = MagicMock(return_value={})
    music_cog._state = MagicMock(return_value=MagicMock(queue=queue))
    music_cog.update_activity = MagicMock()
    music_cog.play_next_in_queue = AsyncMock()

    # Use the real join_voice_channel to verify the actual error-embed path.
    real_cog = Music.__new__(Music)
    real_cog.update_activity = MagicMock()
    music_cog.join_voice_channel = real_cog.join_voice_channel

    ctx = MagicMock()
    ctx.author.voice = None  # user not in a voice channel
    ctx.send = AsyncMock()

    select = SearchSelect(entries, music_cog, ctx)
    select._values = ["0"]

    view_mock = MagicMock()
    interaction = MagicMock()
    interaction.response = MagicMock()
    interaction.response.defer = AsyncMock()
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

    # join_voice_channel sends the error embed via ctx.send
    ctx.send.assert_awaited_once()
    assert "embed" in ctx.send.call_args.kwargs
    embed = ctx.send.call_args.kwargs["embed"]
    assert "canal de voz" in embed.description.lower()

    # Song must NOT be added to queue
    assert len(queue) == 0

    # Success embed must NOT be sent
    interaction.followup.send.assert_not_awaited()

    # Playback must NOT start
    music_cog.play_next_in_queue.assert_not_awaited()
