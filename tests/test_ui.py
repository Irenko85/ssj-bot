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
