from __future__ import annotations

import math
import re

import discord

COLOR_PRIMARY = 0x6C3483
COLOR_SUCCESS = 0x2980B9
COLOR_ERROR = 0x922B21
COLOR_WARNING = 0xCA6F1E
COLOR_INFO = 0x2C3E50

BOT_LABEL = "SSJ Bot"
YOUTUBE_VIDEO_RE = re.compile(
    r"(?:youtube\.com/watch\?v=|youtu\.be/)([A-Za-z0-9_-]{11})"
)


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


def _build_footer_text() -> str:
    return f"{BOT_LABEL} · {discord.utils.utcnow().strftime('%H:%M')}"


def _extract_youtube_video_id(url: str | None) -> str | None:
    if not url:
        return None
    match = YOUTUBE_VIDEO_RE.search(url)
    if match:
        return match.group(1)
    return None


def build_now_playing_embed(song: dict) -> discord.Embed:
    title = song.get("title", "Título desconocido")
    source_url = song.get("source_url") or song.get("webpage_url") or song.get("url")

    embed = discord.Embed(
        title="🎵 Ahora reproduciendo",
        description=f"**{title}**",
        colour=COLOR_PRIMARY,
    )

    video_id = _extract_youtube_video_id(source_url)
    if video_id:
        embed.set_thumbnail(url=f"https://img.youtube.com/vi/{video_id}/0.jpg")

    duration = song.get("duration")
    if duration:
        embed.add_field(name="Duración", value=str(duration), inline=True)

    embed.set_footer(text=_build_footer_text())
    return embed


def build_added_to_queue_embed(song: dict, position: int) -> discord.Embed:
    embed = discord.Embed(
        title="✅ Añadido a la cola",
        description=song.get("title", "Título desconocido"),
        colour=COLOR_SUCCESS,
    )
    embed.add_field(name="Posición en cola", value=str(position), inline=True)
    return embed


def build_queue_embed(
    songs: list,
    now_playing: str,
    page: int = 1,
    page_size: int = 10,
) -> discord.Embed:
    total = len(songs)
    total_pages = max(1, math.ceil(total / page_size))
    page = max(1, min(page, total_pages))

    start = (page - 1) * page_size
    end = start + page_size
    visible_songs = songs[start:end]

    if visible_songs:
        lines = [
            f"{start + index + 1}. {song['title']}"
            for index, song in enumerate(visible_songs)
        ]
        queue_text = "\n".join(lines)
    else:
        queue_text = "No hay canciones en cola."

    embed = discord.Embed(
        title="📋 Cola de reproducción",
        description=f"▶ Ahora: {now_playing}\n\n{queue_text}",
        colour=COLOR_SUCCESS,
    )
    embed.set_footer(text=f"Página {page}/{total_pages} · {total} canciones en cola")
    return embed


def build_search_results_embed(results: list) -> discord.Embed:
    if results:
        lines = [
            f"{index + 1}. {result['title']}"
            for index, result in enumerate(results)
        ]
        description = "\n".join(lines)
    else:
        description = "No se encontraron resultados."

    return discord.Embed(
        title="🔍 Resultados de búsqueda",
        description=description,
        colour=COLOR_PRIMARY,
    )
