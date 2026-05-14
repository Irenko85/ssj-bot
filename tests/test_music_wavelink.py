"""Tests para el Music cog con Wavelink."""
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
    ctx.send = AsyncMock()
    ctx.defer = AsyncMock()
    ctx.voice_client = None
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


class TestSoundCloudFallback:
    @pytest.mark.asyncio
    async def test_search_falls_back_to_soundcloud(self):
        sc_track = MagicMock(spec=wavelink.Playable)
        sc_track.title = "SC Track"
        async def mock_search(query, source=None):
            if source == wavelink.TrackSource.YouTubeMusic:
                return []
            if source == wavelink.TrackSource.SoundCloud:
                return [sc_track]
            return []
        with patch("wavelink.Playable.search", side_effect=mock_search):
            result = await Music._search("test query")
        assert result == [sc_track]

    @pytest.mark.asyncio
    async def test_search_returns_none_when_both_fail(self):
        async def mock_search(query, source=None):
            return []
        with patch("wavelink.Playable.search", side_effect=mock_search):
            result = await Music._search("test query")
        assert result is None
