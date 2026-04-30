from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yt_dlp

from cogs.music_cog import Music, TrackUnavailableError
from utils.ui import QueuePaginationView


def _make_typing_ctx():
    typing_ctx = MagicMock()
    typing_ctx.__aenter__ = AsyncMock()
    typing_ctx.__aexit__ = AsyncMock(return_value=False)
    return typing_ctx


@pytest.mark.asyncio
async def test_play_internal_reraises_track_unavailable_when_silent():
    cog = Music.__new__(Music)
    cog.bot = MagicMock()
    cog.states = {}
    cog.join_voice_channel = AsyncMock(return_value=True)
    cog.start_inactivity_check = MagicMock()
    cog._extract_info = AsyncMock(
        side_effect=yt_dlp.utils.DownloadError("This video is not available")
    )

    ctx = MagicMock()
    ctx.guild = MagicMock(id=1)
    ctx.voice_client = MagicMock()
    ctx.voice_client.is_connected.return_value = True
    ctx.voice_client.is_playing.return_value = False
    ctx.typing = MagicMock(return_value=_make_typing_ctx())
    ctx.send = AsyncMock()

    with patch("cogs.music_cog.SafeYoutubeDL") as ydl_class:
        ydl_class.return_value.__enter__ = MagicMock(return_value=MagicMock(params={}))
        ydl_class.return_value.__exit__ = MagicMock(return_value=False)
        with pytest.raises(TrackUnavailableError):
            await cog._play_internal(
                ctx,
                "https://www.youtube.com/watch?v=YnL70cee6qo",
                silent=True,
            )


@pytest.mark.asyncio
async def test_play_internal_reraises_other_errors_when_silent():
    cog = Music.__new__(Music)
    cog.bot = MagicMock()
    cog.states = {}
    cog.join_voice_channel = AsyncMock(return_value=True)
    cog.start_inactivity_check = MagicMock()
    cog._extract_info = AsyncMock(side_effect=RuntimeError("extract failed"))

    ctx = MagicMock()
    ctx.guild = MagicMock(id=1)
    ctx.voice_client = MagicMock()
    ctx.voice_client.is_connected.return_value = True
    ctx.voice_client.is_playing.return_value = False
    ctx.typing = MagicMock(return_value=_make_typing_ctx())
    ctx.send = AsyncMock()

    with patch("cogs.music_cog.SafeYoutubeDL") as ydl_class:
        ydl_class.return_value.__enter__ = MagicMock(return_value=MagicMock(params={}))
        ydl_class.return_value.__exit__ = MagicMock(return_value=False)
        with pytest.raises(RuntimeError):
            await cog._play_internal(
                ctx,
                "https://www.youtube.com/watch?v=YnL70cee6qo",
                silent=True,
            )


@pytest.mark.asyncio
async def test_play_playlist_reports_failures_and_avoids_success_when_none_added():
    cog = Music.__new__(Music)
    cog.states = {}
    cog.join_voice_channel = AsyncMock(return_value=True)
    cog.start_inactivity_check = MagicMock()
    _extract_results = iter([
        TrackUnavailableError("track-1", "no disponible"),
        RuntimeError("error generico muy largo " + "x" * 120),
    ])
    cog._extract_track_info = AsyncMock(
        side_effect=lambda _opts, _url: next(_extract_results)
    )

    ctx = MagicMock()
    ctx.guild = MagicMock(id=1)
    ctx.send = AsyncMock()

    with patch(
        "cogs.music_cog.utils.get_video_urls_from_playlist",
        new=AsyncMock(return_value=["u1", "u2"]),
    ):
        await cog.play_playlist(ctx, "https://example.com/list")

    embeds = [call.kwargs["embed"] for call in ctx.send.await_args_list]
    titles = [embed.title for embed in embeds]

    assert "⚠️ Canciones no añadidas" in titles
    assert "⚠️ Errores al procesar playlist" in titles
    assert "Playlist añadida" not in titles
    assert "⚠️ Aviso" in titles

    skipped_embed = next(e for e in embeds if e.title == "⚠️ Canciones no añadidas")
    assert all(len(line) <= 80 for line in skipped_embed.description.split("\n"))


def test_queue_pagination_view_recalculates_total_pages_dynamically():
    queue = [{"title": f"Song {i}"} for i in range(11)]
    view = QueuePaginationView(queue, now_playing="Song 0")
    view.current_page = 2

    del queue[3:]
    view._update_buttons()

    assert view.current_page == 1
    assert view.next_button.disabled is True


@pytest.mark.asyncio
async def test_queue_pagination_view_on_timeout_disables_buttons():
    queue = [{"title": "Song 1"}, {"title": "Song 2"}]
    view = QueuePaginationView(queue, now_playing="Song 0")

    await view.on_timeout()

    assert all(child.disabled for child in view.children)
