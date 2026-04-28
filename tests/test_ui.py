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
    assert embed.thumbnail.url == "https://img.youtube.com/vi/YnL70cee6qo/0.jpg"
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
