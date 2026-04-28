from __future__ import annotations

import discord

COLOR_PRIMARY = 0x6C3483
COLOR_SUCCESS = 0x2980B9
COLOR_ERROR = 0x922B21
COLOR_WARNING = 0xCA6F1E
COLOR_INFO = 0x2C3E50


def build_error_embed(message: str) -> discord.Embed:
    return discord.Embed(
        title="❌ Error",
        description=message,
        colour=COLOR_ERROR,
    )


def build_warning_embed(message: str) -> discord.Embed:
    return discord.Embed(
        title="⚠️ Aviso",
        description=message,
        colour=COLOR_WARNING,
    )


def build_info_embed(title: str, message: str) -> discord.Embed:
    return discord.Embed(
        title=title,
        description=message,
        colour=COLOR_INFO,
    )
