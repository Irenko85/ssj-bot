"""Tests para el Music cog con Wavelink."""
import asyncio

import discord
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import wavelink


def make_bot():
    bot = MagicMock()
    bot.add_listener = MagicMock()
    return bot


def make_ctx(guild_id=123, in_voice=True):
    ctx = MagicMock()
    ctx.guild = MagicMock()
    ctx.guild.id = guild_id
    ctx.channel = MagicMock()
    ctx.channel.send = AsyncMock()
    ctx.send = AsyncMock()
    ctx.defer = AsyncMock()
    ctx.voice_client = None
    ctx.interaction = None
    if in_voice:
        ctx.author.voice = MagicMock()
        ctx.author.voice.channel = MagicMock()
        ctx.author.voice.channel.connect = AsyncMock()
    else:
        ctx.author.voice = None
    return ctx


def make_player():
    player = MagicMock(spec=wavelink.Player)
    player.playing = False
    player.paused = False
    player.current = None
    player.queue = MagicMock()
    player.queue.is_empty = True
    player.queue.count = 0
    player.play = AsyncMock()
    player.skip = AsyncMock()
    player.stop = AsyncMock()
    player.disconnect = AsyncMock()
    player.pause = AsyncMock()
    player.set_volume = AsyncMock()
    player.queue.put_wait = AsyncMock()
    player.queue.clear = MagicMock()
    player.queue.shuffle = MagicMock()
    player.queue.remove = MagicMock()
    return player


class TestMusicCogInit:
    def test_cog_has_bot_attribute(self):
        from cogs.music_cog import Music
        bot = make_bot()
        cog = Music(bot)
        assert cog.bot is bot

    def test_cog_has_channel_map(self):
        from cogs.music_cog import Music
        bot = make_bot()
        cog = Music(bot)
        assert hasattr(cog, "_text_channels")
        assert isinstance(cog._text_channels, dict)


from cogs.music_cog import Music, _track_to_song


class TestTrackToSong:
    def test_maps_all_fields(self):
        track = MagicMock(spec=wavelink.Playable)
        track.title = "Test Song"
        track.uri = "https://example.com/song"
        track.artwork = "https://example.com/thumb.jpg"
        track.length = 240000
        track.author = "Artist"
        song = _track_to_song(track)
        assert song["title"] == "Test Song"
        assert song["url"] == "https://example.com/song"
        assert song["source_url"] == "https://example.com/song"
        assert song["thumbnail"] == "https://example.com/thumb.jpg"
        assert song["duration"] == 240.0
        assert song["author"] == "Artist"

    def test_duration_none_when_no_length(self):
        track = MagicMock(spec=wavelink.Playable)
        track.title = "Test"
        track.uri = "https://example.com"
        track.artwork = None
        track.length = None
        track.author = None
        song = _track_to_song(track)
        assert song["duration"] is None


class TestPlayCommand:
    @pytest.mark.asyncio
    async def test_play_defers_before_connecting_to_voice(self):
        bot = make_bot()
        cog = Music(bot)
        ctx = make_ctx()
        player = make_player()
        player.channel = ctx.author.voice.channel
        defer_completed = asyncio.Event()

        async def defer():
            defer_completed.set()

        async def connect(*, cls):
            assert defer_completed.is_set(), "voice connection started before defer completed"
            return player

        ctx.defer = AsyncMock(side_effect=defer)
        ctx.author.voice.channel.connect = AsyncMock(side_effect=connect)

        with patch.object(Music, "_is_lavalink_available", return_value=True), \
             patch.object(Music, "_search", new_callable=AsyncMock, return_value=None):
            await cog.play.callback(cog, ctx, query="test song")

        ctx.defer.assert_awaited_once()
        ctx.author.voice.channel.connect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_play_no_voice_channel(self):
        bot = make_bot()
        cog = Music(bot)
        ctx = make_ctx(in_voice=False)
        with patch.object(Music, "_is_lavalink_available", return_value=True):
            await cog.play.callback(cog, ctx, query="test song")
        ctx.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_play_no_results(self):
        bot = make_bot()
        cog = Music(bot)
        ctx = make_ctx()
        player = make_player()
        player.channel = ctx.author.voice.channel
        ctx.author.voice.channel.connect = AsyncMock(return_value=player)
        with patch.object(Music, "_is_lavalink_available", return_value=True), \
             patch.object(Music, "_search", new_callable=AsyncMock, return_value=None):
            await cog.play.callback(cog, ctx, query="xxxxxxxxxnonexistentxxxxxxxx")
        ctx.send.assert_called()

    @pytest.mark.asyncio
    async def test_play_single_track_plays_immediately(self):
        bot = make_bot()
        cog = Music(bot)
        ctx = make_ctx()
        player = make_player()
        player.channel = ctx.author.voice.channel
        ctx.author.voice.channel.connect = AsyncMock(return_value=player)
        track = MagicMock(spec=wavelink.Playable)
        track.title = "Test Song"
        track.uri = "https://example.com"
        track.artwork = None
        track.length = 180000
        track.author = "Artist"
        with patch.object(Music, "_is_lavalink_available", return_value=True), \
             patch.object(Music, "_search", new_callable=AsyncMock, return_value=[track]):
            await cog.play.callback(cog, ctx, query="test song")
        player.play.assert_called_once_with(track)
        ctx.channel.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_play_queues_when_already_playing(self):
        bot = make_bot()
        cog = Music(bot)
        ctx = make_ctx()
        player = make_player()
        player.playing = True
        player.queue.is_empty = False
        player.queue.count = 1
        player.channel = ctx.author.voice.channel
        ctx.voice_client = player
        track = MagicMock(spec=wavelink.Playable)
        track.title = "Queued Song"
        track.uri = "https://example.com"
        track.artwork = None
        track.length = 180000
        track.author = "Artist"
        with patch.object(Music, "_is_lavalink_available", return_value=True), \
             patch.object(Music, "_search", new_callable=AsyncMock, return_value=[track]):
            await cog.play.callback(cog, ctx, query="queued song")
        player.queue.put_wait.assert_called_once_with(track)
        player.play.assert_not_called()

    @pytest.mark.asyncio
    async def test_play_immediate_publishes_to_channel(self):
        bot = make_bot()
        cog = Music(bot)
        ctx = make_ctx()
        player = make_player()
        player.channel = ctx.author.voice.channel
        ctx.author.voice.channel.connect = AsyncMock(return_value=player)

        original_message = MagicMock()
        original_message.edit = AsyncMock()

        interaction = MagicMock()
        interaction.response = MagicMock()
        interaction.response.is_done = MagicMock(return_value=True)
        interaction.edit_original_response = AsyncMock(side_effect=RuntimeError("boom"))
        interaction.original_response = AsyncMock(return_value=original_message)
        ctx.interaction = interaction

        track = MagicMock(spec=wavelink.Playable)
        track.title = "Test Song"
        track.uri = "https://example.com"
        track.artwork = None
        track.length = 180000
        track.author = "Artist"

        with patch.object(Music, "_is_lavalink_available", return_value=True), \
             patch.object(Music, "_search", new_callable=AsyncMock, return_value=[track]):
            await cog.play.callback(cog, ctx, query="test song")

        ctx.channel.send.assert_awaited_once()


class TestSkipCommand:
    @pytest.mark.asyncio
    async def test_skip_when_not_playing(self):
        bot = make_bot()
        cog = Music(bot)
        ctx = make_ctx()
        ctx.voice_client = None
        await cog.skip.callback(cog, ctx)
        ctx.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_skip_when_playing(self):
        bot = make_bot()
        cog = Music(bot)
        ctx = make_ctx()
        player = make_player()
        player.playing = True
        ctx.voice_client = player
        await cog.skip.callback(cog, ctx)
        player.skip.assert_called_once()


class TestStopCommand:
    @pytest.mark.asyncio
    async def test_stop_disconnects_and_clears_queue(self):
        bot = make_bot()
        cog = Music(bot)
        ctx = make_ctx()
        player = make_player()
        ctx.voice_client = player
        cog._text_channels[123] = ctx.channel
        await cog.stop.callback(cog, ctx)
        player.queue.clear.assert_called_once()
        player.stop.assert_called_once()
        player.disconnect.assert_called_once()
        assert 123 not in cog._text_channels


class TestVolumeCommand:
    @pytest.mark.asyncio
    async def test_volume_invalid_range(self):
        bot = make_bot()
        cog = Music(bot)
        ctx = make_ctx()
        player = make_player()
        ctx.voice_client = player
        await cog.volume.callback(cog, ctx, level=150)
        player.set_volume.assert_not_called()

    @pytest.mark.asyncio
    async def test_volume_valid(self):
        bot = make_bot()
        cog = Music(bot)
        ctx = make_ctx()
        player = make_player()
        ctx.voice_client = player
        await cog.volume.callback(cog, ctx, level=75)
        player.set_volume.assert_called_once_with(75)


class TestSearch:
    @pytest.mark.asyncio
    async def test_search_returns_ytm_results_directly(self):
        ytm_track = MagicMock(spec=wavelink.Playable)
        ytm_track.title = "YTM Track"

        async def mock_search(query, source=None):
            if source == wavelink.TrackSource.YouTubeMusic:
                return [ytm_track]
            return []

        with patch("wavelink.Playable.search", side_effect=mock_search):
            result = await Music._search("test query")
        assert result == [ytm_track]

    @pytest.mark.asyncio
    async def test_search_falls_back_to_youtube(self):
        yt_track = MagicMock(spec=wavelink.Playable)
        yt_track.title = "YT Track"

        async def mock_search(query, source=None):
            if source == wavelink.TrackSource.YouTubeMusic:
                return []
            if source == wavelink.TrackSource.YouTube:
                return [yt_track]
            return []

        with patch("wavelink.Playable.search", side_effect=mock_search):
            result = await Music._search("test query")
        assert result == [yt_track]

    @pytest.mark.asyncio
    async def test_search_falls_back_to_soundcloud(self):
        sc_track = MagicMock()
        sc_track.title = "SC Track"
        sc_track.uri = "https://soundcloud.com/artist/full-track"

        async def mock_search(query, source=None):
            if source == wavelink.TrackSource.YouTubeMusic:
                return []
            if source == wavelink.TrackSource.YouTube:
                return []
            if source == wavelink.TrackSource.SoundCloud:
                return [sc_track]
            return []

        with patch("wavelink.Playable.search", side_effect=mock_search):
            result = await Music._search("test query")
        assert result == [sc_track]

    @pytest.mark.asyncio
    async def test_search_filters_soundcloud_previews(self):
        preview_track = MagicMock()
        preview_track.title = "Preview"
        preview_track.uri = "https://soundcloud.com/artist/track/preview/123"
        full_track = MagicMock()
        full_track.title = "Full"
        full_track.uri = "https://soundcloud.com/artist/track"

        async def mock_search(query, source=None):
            if source == wavelink.TrackSource.YouTubeMusic:
                return []
            if source == wavelink.TrackSource.YouTube:
                return []
            if source == wavelink.TrackSource.SoundCloud:
                return [preview_track, full_track]
            return []

        with patch("wavelink.Playable.search", side_effect=mock_search):
            result = await Music._search("test query")
        assert result == [full_track]

    @pytest.mark.asyncio
    async def test_search_returns_none_when_all_soundcloud_are_previews(self):
        preview_track = MagicMock()
        preview_track.title = "Preview"
        preview_track.uri = "https://soundcloud.com/artist/track/preview/123"

        async def mock_search(query, source=None):
            if source == wavelink.TrackSource.YouTubeMusic:
                return []
            if source == wavelink.TrackSource.YouTube:
                return []
            if source == wavelink.TrackSource.SoundCloud:
                return [preview_track]
            return []

        with patch("wavelink.Playable.search", side_effect=mock_search):
            result = await Music._search("test query")
        assert result is None

    @pytest.mark.asyncio
    async def test_search_returns_none_when_all_sources_fail(self):
        async def mock_search(query, source=None):
            return []

        with patch("wavelink.Playable.search", side_effect=mock_search):
            result = await Music._search("test query")
        assert result is None

    @pytest.mark.asyncio
    async def test_search_soundcloud_playlist_no_previews(self):
        track1 = MagicMock()
        track1.uri = "https://soundcloud.com/artist/track1"
        track2 = MagicMock()
        track2.uri = "https://soundcloud.com/artist/track2"
        playlist = MagicMock(spec=wavelink.Playlist)
        playlist.tracks = [track1, track2]
        playlist.__len__.return_value = 2

        async def mock_search(query, source=None):
            if source == wavelink.TrackSource.YouTubeMusic:
                return []
            if source == wavelink.TrackSource.YouTube:
                return []
            if source == wavelink.TrackSource.SoundCloud:
                return playlist
            return []

        with patch("wavelink.Playable.search", side_effect=mock_search):
            result = await Music._search("test query")
        assert result is playlist
        assert result.tracks == [track1, track2]

    @pytest.mark.asyncio
    async def test_search_soundcloud_playlist_all_previews_returns_none(self):
        track1 = MagicMock()
        track1.uri = "https://soundcloud.com/artist/track1/preview/123"
        track2 = MagicMock()
        track2.uri = "https://soundcloud.com/artist/track2/preview/hls"
        playlist = MagicMock(spec=wavelink.Playlist)
        playlist.tracks = [track1, track2]
        playlist.__len__.return_value = 2

        async def mock_search(query, source=None):
            if source == wavelink.TrackSource.YouTubeMusic:
                return []
            if source == wavelink.TrackSource.YouTube:
                return []
            if source == wavelink.TrackSource.SoundCloud:
                return playlist
            return []

        with patch("wavelink.Playable.search", side_effect=mock_search):
            result = await Music._search("test query")
        assert result is None

    @pytest.mark.asyncio
    async def test_search_soundcloud_playlist_mixed_previews(self):
        preview_track = MagicMock()
        preview_track.uri = "https://soundcloud.com/artist/track/preview/123"
        full_track1 = MagicMock()
        full_track1.uri = "https://soundcloud.com/artist/track1"
        full_track2 = MagicMock()
        full_track2.uri = "https://soundcloud.com/artist/track2"
        playlist = MagicMock(spec=wavelink.Playlist)
        playlist.tracks = [preview_track, full_track1, full_track2]
        playlist.__len__.return_value = 3

        async def mock_search(query, source=None):
            if source == wavelink.TrackSource.YouTubeMusic:
                return []
            if source == wavelink.TrackSource.YouTube:
                return []
            if source == wavelink.TrackSource.SoundCloud:
                return playlist
            return []

        with patch("wavelink.Playable.search", side_effect=mock_search):
            result = await Music._search("test query")
        assert result is playlist
        assert result.tracks == [full_track1, full_track2]

    @pytest.mark.asyncio
    async def test_search_circuit_breaks_on_ytm(self):
        ytm_track = MagicMock(spec=wavelink.Playable)
        ytm_track.title = "YTM Track"

        async def mock_search(query, source=None):
            if source == wavelink.TrackSource.YouTubeMusic:
                return [ytm_track]
            return []

        with patch("wavelink.Playable.search", side_effect=mock_search) as mock_search_fn:
            result = await Music._search("test query")

        assert result == [ytm_track]
        assert mock_search_fn.call_count == 1

    @pytest.mark.asyncio
    async def test_search_circuit_breaks_on_yt(self):
        yt_track = MagicMock(spec=wavelink.Playable)
        yt_track.title = "YT Track"

        async def mock_search(query, source=None):
            if source == wavelink.TrackSource.YouTubeMusic:
                return []
            if source == wavelink.TrackSource.YouTube:
                return [yt_track]
            return []

        with patch("wavelink.Playable.search", side_effect=mock_search) as mock_search_fn:
            result = await Music._search("test query")

        assert result == [yt_track]
        assert mock_search_fn.call_count == 2

    @pytest.mark.parametrize(
        "uri,should_filter",
        [
            ("https://soundcloud.com/artist/track/preview/hls", True),
            ("https://soundcloud.com/artist/track/preview/123", True),
            (None, False),
        ],
    )
    @pytest.mark.asyncio
    async def test_search_filters_preview_uri_variants(self, uri, should_filter):
        track = MagicMock()
        track.title = "Track"
        track.uri = uri

        async def mock_search(query, source=None):
            if source in (wavelink.TrackSource.YouTubeMusic, wavelink.TrackSource.YouTube):
                return []
            if source == wavelink.TrackSource.SoundCloud:
                return [track]
            return []

        with patch("wavelink.Playable.search", side_effect=mock_search):
            result = await Music._search("test query")

        if should_filter:
            assert result is None
        else:
            assert result == [track]


class TestPublishNowPlaying:
    @pytest.mark.asyncio
    async def test_publish_sends_new_message_when_no_previous(self):
        bot = make_bot()
        cog = Music(bot)
        channel = MagicMock()
        channel.guild = MagicMock()
        channel.guild.id = 123
        channel.send = AsyncMock(return_value=MagicMock())
        song = {"title": "Song", "url": "https://example.com"}

        with patch("cogs.music_cog.build_now_playing_embed", return_value=MagicMock()), \
             patch("cogs.music_cog.make_music_control_view", return_value=MagicMock()):
            await cog._publish_now_playing(channel, song)

        channel.send.assert_awaited_once()
        assert 123 in cog._now_playing_messages
        assert cog._now_playing_messages[123] is channel.send.return_value

    @pytest.mark.asyncio
    async def test_publish_deletes_previous_message(self):
        bot = make_bot()
        cog = Music(bot)
        old_msg = MagicMock()
        old_msg.delete = AsyncMock()
        cog._now_playing_messages[123] = old_msg

        channel = MagicMock()
        channel.guild = MagicMock()
        channel.guild.id = 123
        channel.send = AsyncMock(return_value=MagicMock())
        song = {"title": "Song", "url": "https://example.com"}

        with patch("cogs.music_cog.build_now_playing_embed", return_value=MagicMock()), \
             patch("cogs.music_cog.make_music_control_view", return_value=MagicMock()):
            await cog._publish_now_playing(channel, song)

        old_msg.delete.assert_awaited_once()
        channel.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_publish_ignores_not_found_on_delete(self):
        bot = make_bot()
        cog = Music(bot)
        old_msg = MagicMock()
        old_msg.delete = AsyncMock(side_effect=discord.NotFound(MagicMock(), "not found"))
        cog._now_playing_messages[123] = old_msg

        channel = MagicMock()
        channel.guild = MagicMock()
        channel.guild.id = 123
        channel.send = AsyncMock(return_value=MagicMock())
        song = {"title": "Song", "url": "https://example.com"}

        with patch("cogs.music_cog.build_now_playing_embed", return_value=MagicMock()), \
             patch("cogs.music_cog.make_music_control_view", return_value=MagicMock()):
            await cog._publish_now_playing(channel, song)

        old_msg.delete.assert_awaited_once()
        channel.send.assert_awaited_once()
        assert 123 in cog._now_playing_messages

    @pytest.mark.asyncio
    async def test_publish_aborts_on_http_exception(self):
        bot = make_bot()
        cog = Music(bot)
        old_msg = MagicMock()
        old_msg.delete = AsyncMock(side_effect=discord.HTTPException(MagicMock(), "http error"))
        cog._now_playing_messages[123] = old_msg

        channel = MagicMock()
        channel.guild = MagicMock()
        channel.guild.id = 123
        channel.send = AsyncMock(return_value=MagicMock())
        song = {"title": "Song", "url": "https://example.com"}

        with patch("cogs.music_cog.build_now_playing_embed", return_value=MagicMock()), \
             patch("cogs.music_cog.make_music_control_view", return_value=MagicMock()):
            await cog._publish_now_playing(channel, song)

        old_msg.delete.assert_awaited_once()
        channel.send.assert_not_awaited()
        assert 123 not in cog._now_playing_messages

    @pytest.mark.asyncio
    async def test_publish_uses_lock_per_guild(self):
        bot = make_bot()
        cog = Music(bot)
        channel = MagicMock()
        channel.guild = MagicMock()
        channel.guild.id = 456
        channel.send = AsyncMock(return_value=MagicMock())
        song = {"title": "Song", "url": "https://example.com"}

        with patch("cogs.music_cog.build_now_playing_embed", return_value=MagicMock()), \
             patch("cogs.music_cog.make_music_control_view", return_value=MagicMock()):
            await cog._publish_now_playing(channel, song)

        assert 456 in cog._now_playing_locks
        assert isinstance(cog._now_playing_locks[456], asyncio.Lock)

    @pytest.mark.asyncio
    async def test_publish_now_playing_does_not_mark_guild_as_just_published(self):
        bot = make_bot()
        cog = Music(bot)
        channel = MagicMock()
        channel.guild = MagicMock()
        channel.guild.id = 123
        channel.send = AsyncMock(return_value=MagicMock())
        song = {"title": "Song", "url": "https://example.com"}

        with patch("cogs.music_cog.build_now_playing_embed", return_value=MagicMock()), \
             patch("cogs.music_cog.make_music_control_view", return_value=MagicMock()):
            await cog._publish_now_playing(channel, song)

        assert 123 not in cog._np_just_published


class TestCogAfterInvoke:
    @pytest.mark.asyncio
    async def test_after_invoke_publishes_when_song_playing(self):
        bot = make_bot()
        cog = Music(bot)
        ctx = make_ctx()
        player = make_player()
        track = MagicMock(spec=wavelink.Playable)
        track.title = "Playing Song"
        track.uri = "https://example.com"
        track.artwork = None
        track.length = 180000
        track.author = "Artist"
        player.current = track
        ctx.voice_client = player

        with patch.object(cog, "_publish_now_playing", new_callable=AsyncMock) as mock_publish:
            await cog.cog_after_invoke(ctx)

        mock_publish.assert_awaited_once()
        args = mock_publish.await_args
        assert args[0][0] is ctx.channel
        assert args[0][1]["title"] == "Playing Song"

    @pytest.mark.asyncio
    async def test_after_invoke_skips_when_no_guild(self):
        bot = make_bot()
        cog = Music(bot)
        ctx = make_ctx()
        ctx.guild = None

        with patch.object(cog, "_publish_now_playing", new_callable=AsyncMock) as mock_publish:
            await cog.cog_after_invoke(ctx)

        mock_publish.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_after_invoke_skips_when_no_player(self):
        bot = make_bot()
        cog = Music(bot)
        ctx = make_ctx()
        ctx.voice_client = None

        with patch.object(cog, "_publish_now_playing", new_callable=AsyncMock) as mock_publish:
            await cog.cog_after_invoke(ctx)

        mock_publish.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_after_invoke_skips_when_nothing_playing(self):
        bot = make_bot()
        cog = Music(bot)
        ctx = make_ctx()
        player = make_player()
        player.current = None
        ctx.voice_client = player

        with patch.object(cog, "_publish_now_playing", new_callable=AsyncMock) as mock_publish:
            await cog.cog_after_invoke(ctx)

        mock_publish.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_after_invoke_syncs_text_channel(self):
        bot = make_bot()
        cog = Music(bot)
        ctx = make_ctx()
        player = make_player()
        track = MagicMock(spec=wavelink.Playable)
        track.title = "Playing Song"
        track.uri = "https://example.com"
        track.artwork = None
        track.length = 180000
        track.author = "Artist"
        player.current = track
        ctx.voice_client = player

        with patch.object(cog, "_publish_now_playing", new_callable=AsyncMock):
            await cog.cog_after_invoke(ctx)

        assert cog._text_channels.get(ctx.guild.id) is ctx.channel

    @pytest.mark.asyncio
    async def test_after_invoke_skips_on_skip_command(self):
        bot = make_bot()
        cog = Music(bot)
        ctx = make_ctx()
        ctx.command.name = "skip"
        player = make_player()
        track = MagicMock(spec=wavelink.Playable)
        track.title = "Playing Song"
        track.uri = "https://example.com"
        track.artwork = None
        track.length = 180000
        track.author = "Artist"
        player.current = track
        ctx.voice_client = player

        with patch.object(cog, "_publish_now_playing", new_callable=AsyncMock) as mock_publish:
            await cog.cog_after_invoke(ctx)

        mock_publish.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_after_invoke_skips_if_just_published(self):
        bot = make_bot()
        cog = Music(bot)
        ctx = make_ctx()
        guild_id = ctx.guild.id
        cog._np_just_published.add(guild_id)
        player = make_player()
        track = MagicMock(spec=wavelink.Playable)
        track.title = "Playing Song"
        track.uri = "https://example.com"
        track.artwork = None
        track.length = 180000
        track.author = "Artist"
        player.current = track
        ctx.voice_client = player

        with patch.object(cog, "_publish_now_playing", new_callable=AsyncMock) as mock_publish:
            await cog.cog_after_invoke(ctx)

        mock_publish.assert_not_awaited()
        assert guild_id not in cog._np_just_published

    @pytest.mark.asyncio
    async def test_after_invoke_republishes_on_consecutive_commands(self):
        bot = make_bot()
        cog = Music(bot)
        ctx = make_ctx()
        player = make_player()
        track = MagicMock(spec=wavelink.Playable)
        track.title = "Playing Song"
        track.uri = "https://example.com"
        track.artwork = None
        track.length = 180000
        track.author = "Artist"
        player.current = track
        ctx.voice_client = player

        with patch.object(cog, "_publish_now_playing", new_callable=AsyncMock) as mock_publish:
            await cog.cog_after_invoke(ctx)
            await cog.cog_after_invoke(ctx)

        assert mock_publish.call_count == 2

    @pytest.mark.asyncio
    async def test_after_invoke_republishes_after_track_start(self):
        bot = make_bot()
        cog = Music(bot)
        channel = MagicMock()
        cog._text_channels[123] = channel

        payload = MagicMock()
        payload.player = MagicMock()
        payload.player.guild.id = 123
        payload.track = MagicMock(spec=wavelink.Playable)
        payload.track.title = "Track Song"
        payload.track.uri = "https://example.com/track"
        payload.track.artwork = None
        payload.track.length = 180000
        payload.track.author = "Artist"

        ctx = make_ctx()
        player = make_player()
        track = MagicMock(spec=wavelink.Playable)
        track.title = "Playing Song"
        track.uri = "https://example.com/song"
        track.artwork = None
        track.length = 180000
        track.author = "Artist"
        player.current = track
        ctx.voice_client = player

        with patch.object(cog, "_publish_now_playing", new_callable=AsyncMock) as mock_publish:
            await cog.on_wavelink_track_start(payload)
            await cog.cog_after_invoke(ctx)

        assert mock_publish.call_count == 2
