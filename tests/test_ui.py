import discord

from utils.ui import COLOR_ERROR, build_error_embed


def test_build_error_embed_uses_error_palette():
    embed = build_error_embed("Boom")

    assert isinstance(embed, discord.Embed)
    assert embed.title == "❌ Error"
    assert embed.description == "Boom"
    assert embed.colour.value == COLOR_ERROR
