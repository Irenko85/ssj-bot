import discord

from utils.ui import (
    COLOR_ERROR,
    COLOR_INFO,
    COLOR_WARNING,
    build_error_embed,
    build_info_embed,
    build_warning_embed,
)


def test_build_error_embed_uses_error_palette():
    embed = build_error_embed("Boom")

    assert isinstance(embed, discord.Embed)
    assert embed.title == "❌ Error"
    assert embed.description == "Boom"
    assert embed.colour.value == COLOR_ERROR


def test_build_warning_embed_uses_warning_palette():
    embed = build_warning_embed("Atento")

    assert embed.title == "⚠️ Aviso"
    assert embed.description == "Atento"
    assert embed.colour.value == COLOR_WARNING


def test_build_info_embed_uses_custom_title():
    embed = build_info_embed("Cola", "Sin canciones")

    assert embed.title == "Cola"
    assert embed.description == "Sin canciones"
    assert embed.colour.value == COLOR_INFO


from utils.ui import COLOR_PRIMARY, build_now_playing_embed


def test_build_now_playing_embed_adds_youtube_thumbnail():
    embed = build_now_playing_embed(
        {
            "title": "Cha-La Head-Cha-La",
            "source_url": "https://www.youtube.com/watch?v=YnL70cee6qo",
        }
    )

    assert embed.title == "🎵 Ahora reproduciendo"
    assert embed.description == "**Cha-La Head-Cha-La**"
    assert embed.colour.value == COLOR_PRIMARY
    assert embed.thumbnail.url == "https://i.ytimg.com/vi/YnL70cee6qo/maxresdefault.jpg"
    assert embed.footer.text.startswith("SSJ Bot · ")


def test_build_now_playing_embed_ignores_url_without_video_id():
    embed = build_now_playing_embed(
        {
            "title": "Unknown",
            "source_url": "https://www.youtube.com/watch",
        }
    )

    assert embed.title == "🎵 Ahora reproduciendo"
    assert embed.thumbnail.url is None


def test_build_now_playing_embed_ignores_soundcloud_url():
    embed = build_now_playing_embed(
        {
            "title": "Sound",
            "source_url": "https://soundcloud.com/artist/song",
        }
    )

    assert embed.title == "🎵 Ahora reproduciendo"
    assert embed.thumbnail.url is None


from utils.ui import COLOR_SUCCESS, build_added_to_queue_embed


def test_build_added_to_queue_embed_shows_position():
    embed = build_added_to_queue_embed({"title": "Limit Break x Survivor"}, position=3)

    assert embed.title == "✅ Añadido a la cola"
    assert embed.description == "Limit Break x Survivor"
    assert embed.colour.value == COLOR_SUCCESS
    assert len(embed.fields) == 1
    assert embed.fields[0].name == "Posición en cola"
    assert embed.fields[0].value == "3"


def test_build_now_playing_embed_uses_explicit_thumbnail_and_duration():
    embed = build_now_playing_embed(
        {
            "title": "Cha-La Head-Cha-La",
            "thumbnail": "https://cdn.example/thumb.jpg",
            "duration": 213,
        }
    )
    assert embed.title == "🎵 Ahora reproduciendo"
    assert embed.thumbnail.url == "https://cdn.example/thumb.jpg"
    assert len(embed.fields) == 1
    assert embed.fields[0].name == "Duración"
    assert embed.fields[0].value == "3:33"


def test_format_duration_under_one_hour():
    song = {"title": "Tema", "duration": 95}
    embed = build_now_playing_embed(song)
    assert embed.fields[0].value == "1:35"


def test_format_duration_exact_minutes():
    song = {"title": "Tema", "duration": 240}
    embed = build_now_playing_embed(song)
    assert embed.fields[0].value == "4:00"


def test_format_duration_over_one_hour():
    song = {"title": "Tema", "duration": 3735}
    embed = build_now_playing_embed(song)
    assert embed.fields[0].value == "1:02:15"


def test_build_added_to_queue_embed_sets_thumbnail_when_present():
    embed = build_added_to_queue_embed(
        {
            "title": "Limit Break x Survivor",
            "thumbnail": "https://cdn.example/queue-thumb.jpg",
        },
        position=3,
    )
    assert embed.title == "✅ Añadido a la cola"
    assert embed.description == "Limit Break x Survivor"
    assert embed.thumbnail.url == "https://cdn.example/queue-thumb.jpg"


def test_build_added_to_queue_embed_skips_thumbnail_when_missing():
    embed = build_added_to_queue_embed(
        {"title": "Limit Break x Survivor"},
        position=3,
    )
    assert embed.title == "✅ Añadido a la cola"
    assert embed.thumbnail.url is None


from utils.ui import build_queue_embed


def test_build_queue_embed_handles_empty_queue():
    embed = build_queue_embed([], now_playing="Nada")

    assert embed.title == "📋 Cola de reproducción"
    assert "▶ Ahora: Nada" in embed.description
    assert "No hay canciones en cola." in embed.description
    assert embed.footer.text == "Página 1/1 · 0 canciones en cola"


def test_build_queue_embed_renders_single_song():
    embed = build_queue_embed(
        [{"title": "Dan Dan Kokoro Hikareteku"}],
        now_playing="Cha-La Head-Cha-La",
    )

    assert "▶ Ahora: Cha-La Head-Cha-La" in embed.description
    assert "1. Dan Dan Kokoro Hikareteku" in embed.description
    assert embed.footer.text == "Página 1/1 · 1 canciones en cola"


def test_build_queue_embed_replaces_none_now_playing():
    embed = build_queue_embed([], now_playing=None)

    assert "▶ Ahora: Nada" in embed.description
    assert "None" not in embed.description


def test_build_queue_embed_paginates_results():
    songs = [{"title": f"Song {i}"} for i in range(1, 16)]

    embed = build_queue_embed(songs, now_playing="Song 0", page=2, page_size=10)

    assert "11. Song 11" in embed.description
    assert "15. Song 15" in embed.description
    assert "10. Song 10" not in embed.description
    assert embed.footer.text == "Página 2/2 · 15 canciones en cola"


from utils.ui import build_search_results_embed


def test_build_search_results_embed_lists_titles():
    embed = build_search_results_embed(
        [
            {"title": "Blue Bird"},
            {"title": "Silhouette"},
            {"title": "Haruka Kanata"},
        ]
    )

    assert embed.title == "🔍 Resultados de búsqueda"
    assert "1. Blue Bird" in embed.description
    assert "2. Silhouette" in embed.description
    assert "3. Haruka Kanata" in embed.description


def test_build_search_results_embed_handles_empty_list():
    embed = build_search_results_embed([])

    assert embed.title == "🔍 Resultados de búsqueda"
    assert embed.description == "No se encontraron resultados."


import re


def test_footer_text_format():
    from utils.ui import _build_footer_text, BOT_LABEL

    footer = _build_footer_text()
    assert BOT_LABEL in footer
    assert re.search(r"\d{2}:\d{2}", footer)
