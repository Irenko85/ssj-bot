from __future__ import annotations

import inspect
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
    now = discord.utils.utcnow().astimezone()
    return f"{BOT_LABEL} · {now.strftime('%H:%M')}"


def _extract_youtube_video_id(url: str | None) -> str | None:
    if not url:
        return None
    match = YOUTUBE_VIDEO_RE.search(url)
    if match:
        return match.group(1)
    return None


def _format_duration(seconds: int | float | None) -> str | None:
    if not seconds:
        return None
    total_seconds = int(seconds)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


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
        embed.set_image(url=f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg")
    elif song.get("thumbnail"):
        embed.set_image(url=song["thumbnail"])

    duration = _format_duration(song.get("duration"))
    if duration:
        embed.add_field(name="Duración", value=duration, inline=True)

    embed.set_footer(text=_build_footer_text())
    return embed


def build_added_to_queue_embed(song: dict, position: int) -> discord.Embed:
    embed = discord.Embed(
        title="✅ Añadido a la cola",
        description=song.get("title", "Título desconocido"),
        colour=COLOR_SUCCESS,
    )
    embed.add_field(name="Posición en cola", value=str(position), inline=True)
    thumbnail = song.get("thumbnail")
    if thumbnail:
        embed.set_thumbnail(url=thumbnail)
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
        description=f"▶ Ahora: {now_playing or 'Nada'}\n\n{queue_text}",
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


class MusicControlView(discord.ui.View):
    def __init__(self, bot, music_cog=None):
        super().__init__(timeout=None)
        self.bot = bot
        self.music_cog = music_cog or bot.get_cog("Music")

    @discord.ui.button(
        emoji="⏸",
        style=discord.ButtonStyle.secondary,
        custom_id="pause_resume",
    )
    async def pause_resume(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        voice_client = interaction.guild.voice_client if interaction.guild else None
        if not voice_client:
            await interaction.response.send_message(
                embed=build_error_embed("No hay reproducción activa."),
                ephemeral=True,
            )
            return

        if voice_client.is_paused():
            voice_client.resume()
            paused = False
            message = "Se reanudó la reproducción."
        elif voice_client.is_playing():
            voice_client.pause()
            paused = True
            message = "Se pausó la reproducción."
        else:
            await interaction.response.send_message(
                embed=build_error_embed("No hay reproducción activa."),
                ephemeral=True,
            )
            return

        self.music_cog.update_activity(interaction.guild)
        fresh_view = make_music_control_view(self.bot, music_cog=self.music_cog, paused=paused)
        await interaction.message.edit(view=fresh_view)
        await interaction.response.send_message(
            embed=build_info_embed("Control de reproducción", message),
            ephemeral=True,
        )

    @discord.ui.button(
        emoji="⏭",
        style=discord.ButtonStyle.secondary,
        custom_id="skip",
    )
    async def skip(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        voice_client = interaction.guild.voice_client if interaction.guild else None
        if not voice_client or not voice_client.is_playing():
            await interaction.response.send_message(
                embed=build_error_embed("No hay nada que skipear."),
                ephemeral=True,
            )
            return

        voice_client.stop()
        self.music_cog.update_activity(interaction.guild)
        await interaction.response.send_message(
            embed=build_info_embed("Control de reproducción", "Se skipeó la canción actual."),
            ephemeral=True,
        )

    @discord.ui.button(
        emoji="⏹",
        style=discord.ButtonStyle.secondary,
        custom_id="stop",
    )
    async def stop(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        voice_client = interaction.guild.voice_client if interaction.guild else None
        if not voice_client:
            await interaction.response.send_message(
                embed=build_error_embed("No hay reproducción activa."),
                ephemeral=True,
            )
            return

        state = self.music_cog._state(interaction.guild)
        state.queue.clear()

        if voice_client.is_playing() or voice_client.is_paused():
            voice_client.stop()
        if voice_client.is_connected():
            result = voice_client.disconnect()
            if inspect.isawaitable(result):
                await result

        fresh_view = make_music_control_view(self.bot, music_cog=self.music_cog, disabled=True)
        await interaction.message.edit(
            embed=build_info_embed("⏹ Reproducción finalizada", "La reproducción se detuvo."),
            view=fresh_view,
        )
        await interaction.response.send_message(
            embed=build_info_embed("Control de reproducción", "Se detuvo la reproducción."),
            ephemeral=True,
        )

        if interaction.guild:
            self.music_cog._cleanup_state(interaction.guild.id)

    @discord.ui.button(
        emoji="🎶",
        style=discord.ButtonStyle.secondary,
        custom_id="view_queue",
    )
    async def view_queue(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        state = self.music_cog._state(interaction.guild)

        if state.queue:
            embed = build_queue_embed(
                state.queue,
                now_playing=state.actual_song or "Nada",
            )
        else:
            embed = build_info_embed(
                "📋 Cola de reproducción",
                "La cola está vacía.",
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(
        emoji="🔀",
        style=discord.ButtonStyle.secondary,
        custom_id="shuffle",
    )
    async def shuffle(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        state = self.music_cog._state(interaction.guild)
        if len(state.queue) < 2:
            await interaction.response.send_message(
                embed=build_warning_embed("No hay canciones suficientes en la cola para mezclar."),
                ephemeral=True,
            )
            return

        import random
        random.shuffle(state.queue)
        self.music_cog.update_activity(interaction.guild)
        await interaction.response.send_message(
            embed=build_info_embed("🔀 Shuffle", "La cola fue mezclada."),
            ephemeral=True,
        )


# Stateless singleton registered with bot.add_view().  Callbacks must NOT
# mutate this instance; instead they create fresh views via the factory.
def make_music_control_view(bot, music_cog=None, *, paused=False, disabled=False):
    """Return a fresh MusicControlView with the desired visual state."""
    view = MusicControlView(bot, music_cog=music_cog)
    if paused:
        for child in view.children:
            if child.custom_id == "pause_resume":
                child.emoji = "▶️"
    if disabled:
        for child in view.children:
            child.disabled = True
    return view
