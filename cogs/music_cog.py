"""Music cog — Wavelink 3.x + Lavalink 4."""
from __future__ import annotations

import asyncio
import logging
import math
import os
import random
from contextlib import suppress

import discord
import wavelink
from discord.ext import commands

from utils.ui import (
    QueuePaginationView,
    build_added_to_queue_embed,
    build_error_embed,
    build_info_embed,
    build_now_playing_embed,
    build_queue_embed,
    build_search_results_embed,
    build_warning_embed,
    make_music_control_view,
)

logger = logging.getLogger(__name__)


def _track_to_song(track: wavelink.Playable) -> dict:
    """Convierte un wavelink.Playable al dict que esperan los embeds de utils/ui.py."""
    return {
        "title": track.title,
        "url": track.uri,
        "source_url": track.uri,
        "webpage_url": track.uri,
        "thumbnail": track.artwork,
        "duration": track.length / 1000 if track.length else None,
        "author": track.author,
    }


def _is_track_unavailable(exception: dict | str | None) -> bool:
    """Detecta si la excepción de Wavelink indica que la canción no está disponible."""
    if not exception:
        return False
    msg = exception.get("message", "") if isinstance(exception, dict) else str(exception)
    msg_lower = str(msg).lower()
    patterns = [
        "all clients failed",
        "this video is not available",
        "requires login",
    ]
    return any(p in msg_lower for p in patterns)


class _PlayerStateAdapter:
    """Minimal adapter to satisfy MusicControlView's _state() API."""
    def __init__(self, player: wavelink.Player | None):
        self._player = player

    @property
    def queue(self) -> "_QueueAdapter":
        return _QueueAdapter(self._player)

    @property
    def actual_song(self) -> str | None:
        if self._player and self._player.current:
            return self._player.current.title
        return None


class _QueueAdapter:
    """Adapts wavelink.Queue to list-like interface for MusicControlView."""
    def __init__(self, player: wavelink.Player | None):
        self._player = player

    def __len__(self):
        if self._player is None:
            return 0
        return self._player.queue.count

    def __iter__(self):
        if self._player is None:
            return iter([])
        return iter(self._player.queue)

    def clear(self):
        if self._player:
            self._player.queue.clear()


class _FixedPlayer(wavelink.Player):
    """Wavelink 3.4.1 no envía channelId a Lavalink 4.x. Este parche lo agrega."""

    async def on_voice_state_update(self, data, /) -> None:  # type: ignore[override]
        channel_id = data["channel_id"]
        if not channel_id:
            await self._destroy()
            return
        self._connected = True
        self._voice_state["voice"]["session_id"] = data["session_id"]
        self._voice_state["voice"]["channel_id"] = channel_id  # guardamos para el PATCH
        self.channel = self.client.get_channel(int(channel_id))  # type: ignore

    async def _dispatch_voice_update(self) -> None:
        assert self.guild is not None
        data = self._voice_state["voice"]
        session_id = data.get("session_id")
        token = data.get("token")
        endpoint = data.get("endpoint")
        channel_id = data.get("channel_id")

        if not session_id or not token or not endpoint:
            return

        voice_payload: dict = {
            "sessionId": session_id,
            "token": token,
            "endpoint": endpoint,
        }
        if channel_id:
            voice_payload["channelId"] = str(channel_id)

        request = {"voice": voice_payload}
        try:
            await self.node._update_player(self.guild.id, data=request)
        except Exception:
            self._connection_event.set()
            await self.disconnect()
            return
        self._connection_event.set()


class Music(commands.Cog):
    """Cog de música usando Wavelink + Lavalink."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._text_channels: dict[int, discord.TextChannel] = {}
        self._now_playing_messages: dict[int, discord.Message] = {}
        self._now_playing_locks: dict[int, asyncio.Lock] = {}
        self._np_just_published: set[int] = set()

    # ── Compatibility shims for MusicControlView ──────────────────────────

    def _state(self, ctx_or_guild) -> _PlayerStateAdapter:
        """Compatibility shim for MusicControlView. Returns adapter over wavelink.Player."""
        guild = ctx_or_guild.guild if hasattr(ctx_or_guild, "guild") else ctx_or_guild
        if guild is None:
            return _PlayerStateAdapter(None)
        player = discord.utils.get(self.bot.voice_clients, guild=guild)
        return _PlayerStateAdapter(player)

    def _cleanup_state(self, guild_id: int) -> None:
        """Compatibility shim for MusicControlView."""
        self._text_channels.pop(guild_id, None)
        getattr(self, "_now_playing_messages", {}).pop(guild_id, None)
        getattr(self, "_now_playing_locks", {}).pop(guild_id, None)
        getattr(self, "_np_just_published", set()).discard(guild_id)

    def update_activity(self, ctx_or_guild) -> None:
        """Compatibility shim for MusicControlView. No-op in wavelink."""
        pass

    # ── Internal helpers ────────────────────────────────────────────────────

    def _get_text_channel(self, guild_id: int) -> discord.TextChannel | None:
        return self._text_channels.get(guild_id)

    def _set_text_channel(self, ctx: commands.Context) -> None:
        if ctx.guild:
            self._text_channels[ctx.guild.id] = ctx.channel

    def _get_np_lock(self, guild_id: int) -> asyncio.Lock:
        if guild_id not in self._now_playing_locks:
            self._now_playing_locks[guild_id] = asyncio.Lock()
        return self._now_playing_locks[guild_id]

    async def _publish_now_playing(self, channel: discord.TextChannel, song: dict) -> None:
        """Publica o actualiza el mensaje de now-playing en el canal, asegurando solo uno visible."""
        guild_id = channel.guild.id
        lock = self._get_np_lock(guild_id)
        async with lock:
            old_msg = self._now_playing_messages.get(guild_id)
            if old_msg is not None:
                try:
                    await old_msg.delete()
                except discord.NotFound:
                    pass
                except discord.HTTPException:
                    logger.warning("No se pudo borrar el NP anterior para guild %s; se omite envío", guild_id)
                    self._now_playing_messages.pop(guild_id, None)
                    return
            embed = build_now_playing_embed(song)
            view = make_music_control_view(self.bot, music_cog=self)
            new_msg = await channel.send(embed=embed, view=view)
            self._now_playing_messages[guild_id] = new_msg
            # NOTE: NO agregamos guild_id a _np_just_published aquí
            # porque este método también es llamado por on_wavelink_track_start
            # y por cog_after_invoke. Cada caller gestiona el flag según corresponda.

    async def _respond(
        self,
        ctx: commands.Context,
        *,
        embed: discord.Embed,
        view: discord.ui.View | None = None,
        ephemeral: bool = False,
    ):
        interaction = ctx.interaction
        if interaction is None:
            return await ctx.send(embed=embed, view=view)

        if not interaction.response.is_done():
            return await interaction.response.send_message(embed=embed, view=view, ephemeral=ephemeral)

        try:
            return await interaction.edit_original_response(embed=embed, view=view)
        except Exception:
            logger.exception("No pude editar la respuesta original de la interacción")

        with suppress(Exception):
            original = await interaction.original_response()
            return await original.edit(embed=embed, view=view)

        return await interaction.followup.send(embed=embed, view=view, ephemeral=ephemeral, wait=True)

    @staticmethod
    def _is_lavalink_available() -> bool:
        try:
            node = wavelink.Pool.get_node()
            return node is not None and node.status == wavelink.NodeStatus.CONNECTED
        except Exception:
            return False

    async def _get_player(self, ctx: commands.Context) -> wavelink.Player | None:
        return ctx.voice_client  # type: ignore

    async def _ensure_connected(self, ctx: commands.Context) -> wavelink.Player | None:
        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.send(embed=build_error_embed("Debés estar en un canal de voz primero."))
            return None
        player: wavelink.Player | None = ctx.voice_client  # type: ignore
        if player is None:
            try:
                player = await ctx.author.voice.channel.connect(cls=_FixedPlayer)
            except discord.ClientException:
                await ctx.send(embed=build_error_embed("No pude conectarme al canal de voz."))
                return None
        if player.channel != ctx.author.voice.channel:
            await ctx.send(embed=build_error_embed("Ya estoy en otro canal de voz."))
            return None
        return player

    async def cog_check(self, ctx: commands.Context) -> bool:
        if ctx.guild is None:
            await ctx.send(embed=build_error_embed("Los comandos de música solo funcionan en servidores."))
            return False
        return True

    async def cog_after_invoke(self, ctx: commands.Context) -> None:
        """Re-publica el now-playing al fondo del canal después de cada comando."""
        if ctx.guild is None:
            return

        # Issue 2: skip ya gatilla on_wavelink_track_start, no republicar el track viejo
        if ctx.command and ctx.command.name == "skip":
            self._np_just_published.discard(ctx.guild.id)  # limpiar flag stale
            return

        # Issue 1: si el comando ya publicó (play path inmediato, nowplaying), no duplicar
        if ctx.guild.id in self._np_just_published:
            self._np_just_published.discard(ctx.guild.id)
            return

        player: wavelink.Player | None = ctx.voice_client  # type: ignore
        if player is None or player.current is None:
            return
        channel = ctx.channel
        self._text_channels[ctx.guild.id] = channel  # sync active channel
        song = _track_to_song(player.current)
        await self._publish_now_playing(channel, song)

    # ── Wavelink events ────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, payload: wavelink.NodeReadyEventPayload) -> None:
        if payload.resumed:
            logger.info(f"Lavalink node reconnected (session resumed): {payload.node!r}")
            return
        logger.warning(f"Lavalink node reconnected (new session), disconnecting active players")
        for player in list(self.bot.voice_clients):
            if not isinstance(player, wavelink.Player):
                continue
            player.queue.clear()
            await player.disconnect()
            guild_id = player.guild.id
            self._text_channels.pop(guild_id, None)
            getattr(self, "_now_playing_messages", {}).pop(guild_id, None)
            getattr(self, "_now_playing_locks", {}).pop(guild_id, None)
            getattr(self, "_np_just_published", set()).discard(guild_id)

    @commands.Cog.listener()
    async def on_wavelink_track_start(self, payload: wavelink.TrackStartEventPayload) -> None:
        player = payload.player
        if player is None:
            return
        channel = self._get_text_channel(player.guild.id)
        if channel is None:
            return
        song = _track_to_song(payload.track)
        await self._publish_now_playing(channel, song)

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload: wavelink.TrackEndEventPayload) -> None:
        player = payload.player
        if player is None:
            return
        if not player.queue.is_empty:
            next_track = player.queue.get()
            await player.play(next_track)

    @commands.Cog.listener()
    async def on_wavelink_track_exception(self, payload: wavelink.TrackExceptionEventPayload) -> None:
        player = payload.player
        if player is None:
            return

        channel = self._get_text_channel(player.guild.id)

        if _is_track_unavailable(payload.exception):
            logger.warning(f"Track unavailable, skipping: {payload.exception}")
            if channel:
                await channel.send(embed=build_info_embed("⏭️ Canción saltada", "Canción no disponible, saltando..."))
        else:
            logger.error(f"Track exception: {payload.exception}")
            if channel:
                msg = payload.exception.get("message", "Error desconocido") if isinstance(payload.exception, dict) else str(payload.exception)
                await channel.send(embed=build_error_embed(f"Error al reproducir la canción: {msg}"))

        if not player.queue.is_empty:
            next_track = player.queue.get()
            await player.play(next_track)

    @commands.Cog.listener()
    async def on_wavelink_inactive_player(self, player: wavelink.Player) -> None:
        channel = self._get_text_channel(player.guild.id)
        if channel:
            await channel.send(embed=build_info_embed("Desconectado", "Sin actividad por inactividad."))
        await player.disconnect()
        self._text_channels.pop(player.guild.id, None)
        getattr(self, "_now_playing_messages", {}).pop(player.guild.id, None)
        getattr(self, "_now_playing_locks", {}).pop(player.guild.id, None)
        getattr(self, "_np_just_published", set()).discard(player.guild.id)

    # ── Search helper ────────────────────────────────────────────────────────

    @staticmethod
    async def _search(query: str) -> list[wavelink.Playable] | wavelink.Playlist | None:
        tracks: wavelink.Search = await wavelink.Playable.search(
            query, source=wavelink.TrackSource.YouTubeMusic
        )
        if tracks:
            return tracks
        tracks = await wavelink.Playable.search(
            query, source=wavelink.TrackSource.SoundCloud
        )
        return tracks if tracks else None

    # ── Comandos slash ───────────────────────────────────────────────────────

    @commands.hybrid_command(name="play", description="Reproduce una canción o la añade a la cola.")
    async def play(self, ctx: commands.Context, *, query: str) -> None:
        if not self._is_lavalink_available():
            await ctx.send(embed=build_error_embed("El sistema de música no está disponible ahora."))
            return
        self._set_text_channel(ctx)
        player = await self._ensure_connected(ctx)
        if player is None:
            return
        await ctx.defer()
        if query.startswith("http"):
            tracks: wavelink.Search = await wavelink.Playable.search(query)
        else:
            tracks = await self._search(query)
        if not tracks:
            await self._respond(ctx, embed=build_warning_embed("No se encontraron resultados."))
            return
        if isinstance(tracks, wavelink.Playlist):
            for track in tracks.tracks:
                await player.queue.put_wait(track)
            await self._respond(
                ctx,
                embed=build_info_embed("✅ Playlist añadida", f"**{tracks.name}** — {len(tracks.tracks)} canciones añadidas a la cola."),
            )
            if not player.playing and not player.paused and not player.queue.is_empty:
                next_track = player.queue.get()
                await player.play(next_track)
        else:
            track = tracks[0]
            if player.current is not None or player.playing or player.paused or not player.queue.is_empty:
                await player.queue.put_wait(track)
                song = _track_to_song(track)
                await self._respond(ctx, embed=build_added_to_queue_embed(song, player.queue.count))
            else:
                await player.play(track)
                song = _track_to_song(track)
                self._np_just_published.add(ctx.guild.id)
                await self._publish_now_playing(ctx.channel, song)
                if ctx.interaction:
                    try:
                        await ctx.interaction.delete_original_response()
                    except (discord.NotFound, discord.HTTPException, TypeError):
                        pass

    @commands.hybrid_command(name="search", description="Busca canciones y muestra resultados para elegir.")
    async def search(self, ctx: commands.Context, *, query: str) -> None:
        if not self._is_lavalink_available():
            await ctx.send(embed=build_error_embed("El sistema de música no está disponible ahora."))
            return
        self._set_text_channel(ctx)
        await ctx.defer(ephemeral=True)
        tracks = await self._search(query)
        if not tracks or isinstance(tracks, wavelink.Playlist):
            await ctx.send(embed=build_warning_embed("No se encontraron resultados."), ephemeral=True)
            return
        results = tracks[:5]
        result_dicts = [_track_to_song(t) for t in results]
        embed = build_search_results_embed(result_dicts)
        view = SearchSelectView(results, player_cog=self, ctx=ctx)
        await ctx.send(embed=embed, view=view, ephemeral=True)

    @commands.hybrid_command(name="skip", description="Salta la canción actual.")
    async def skip(self, ctx: commands.Context) -> None:
        player = await self._get_player(ctx)
        if player is None or not player.playing:
            await ctx.send(embed=build_warning_embed("No hay nada reproduciéndose."))
            return
        await player.skip()
        await ctx.send(embed=build_info_embed("⏭ Saltado", "Canción saltada."))

    @commands.hybrid_command(name="stop", description="Detiene la reproducción y desconecta el bot.")
    async def stop(self, ctx: commands.Context) -> None:
        player = await self._get_player(ctx)
        if player is None:
            await ctx.send(embed=build_warning_embed("No estoy en un canal de voz."))
            return
        player.queue.clear()
        await player.stop()
        await player.disconnect()
        self._text_channels.pop(ctx.guild.id, None)
        getattr(self, "_now_playing_messages", {}).pop(ctx.guild.id, None)
        getattr(self, "_now_playing_locks", {}).pop(ctx.guild.id, None)
        getattr(self, "_np_just_published", set()).discard(ctx.guild.id)
        await ctx.send(embed=build_info_embed("⏹ Detenido", "Reproducción detenida y cola vaciada."))

    @commands.hybrid_command(name="pause", description="Pausa la reproducción.")
    async def pause(self, ctx: commands.Context) -> None:
        player = await self._get_player(ctx)
        if player is None or not player.playing:
            await ctx.send(embed=build_warning_embed("No hay nada reproduciéndose."))
            return
        await player.pause(True)
        await ctx.send(embed=build_info_embed("⏸ Pausado", "Reproducción pausada."))

    @commands.hybrid_command(name="resume", description="Reanuda la reproducción.")
    async def resume(self, ctx: commands.Context) -> None:
        player = await self._get_player(ctx)
        if player is None:
            await ctx.send(embed=build_warning_embed("No estoy en un canal de voz."))
            return
        await player.pause(False)
        await ctx.send(embed=build_info_embed("▶️ Reanudado", "Reproducción reanudada."))

    @commands.hybrid_command(name="queue", description="Muestra la cola de reproducción.")
    async def queue(self, ctx: commands.Context) -> None:
        player = await self._get_player(ctx)
        if player is None or (player.queue.is_empty and not player.playing):
            await ctx.send(embed=build_warning_embed("La cola está vacía."))
            return
        now_playing = player.current.title if player.current else "Nada"
        queue_songs = [_track_to_song(t) for t in player.queue]
        view = QueuePaginationView(queue_songs, now_playing)
        embed = build_queue_embed(queue_songs, now_playing)
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg

    @commands.hybrid_command(name="nowplaying", description="Muestra la canción actual.")
    async def nowplaying(self, ctx: commands.Context) -> None:
        player = await self._get_player(ctx)
        if player is None or not player.current:
            await ctx.send(embed=build_warning_embed("No hay nada reproduciéndose."))
            return
        song = _track_to_song(player.current)
        self._np_just_published.add(ctx.guild.id)
        await self._publish_now_playing(ctx.channel, song)

    @commands.hybrid_command(name="shuffle", description="Mezcla la cola de reproducción.")
    async def shuffle(self, ctx: commands.Context) -> None:
        player = await self._get_player(ctx)
        if player is None or player.queue.is_empty:
            await ctx.send(embed=build_warning_embed("La cola está vacía."))
            return
        player.queue.shuffle()
        await ctx.send(embed=build_info_embed("🔀 Mezclado", "Cola mezclada aleatoriamente."))

    @commands.hybrid_command(name="remove", description="Elimina una canción de la cola por posición.")
    async def remove(self, ctx: commands.Context, position: int) -> None:
        player = await self._get_player(ctx)
        if player is None or player.queue.is_empty:
            await ctx.send(embed=build_warning_embed("La cola está vacía."))
            return
        queue_list = list(player.queue)
        if position < 1 or position > len(queue_list):
            await ctx.send(embed=build_error_embed(f"Posición inválida. La cola tiene {len(queue_list)} canción(es)."))
            return
        track = queue_list[position - 1]
        player.queue.remove(track)
        await ctx.send(embed=build_info_embed("🗑 Eliminado", f"**{track.title}** eliminado de la cola."))

    @commands.hybrid_command(name="volume", description="Ajusta el volumen (0-100).")
    async def volume(self, ctx: commands.Context, level: int) -> None:
        player = await self._get_player(ctx)
        if player is None:
            await ctx.send(embed=build_warning_embed("No estoy en un canal de voz."))
            return
        if not 0 <= level <= 100:
            await ctx.send(embed=build_error_embed("El volumen debe estar entre 0 y 100."))
            return
        await player.set_volume(level)
        await ctx.send(embed=build_info_embed("🔊 Volumen", f"Volumen ajustado a **{level}%**."))

    @commands.hybrid_command(name="dbz", description="Reproduce la playlist de Dragon Ball Z")
    async def dbz(self, ctx: commands.Context) -> None:
        DBZ_PLAYLIST_URL = "https://www.youtube.com/playlist?list=PLy0A50xAkMqRZLl2JDYG9R1vdBaVnJhM"
        if not self._is_lavalink_available():
            await ctx.send(embed=build_error_embed("El sistema de música no está disponible ahora."))
            return
        self._set_text_channel(ctx)
        player = await self._ensure_connected(ctx)
        if player is None:
            return
        await ctx.defer()
        tracks: wavelink.Search = await wavelink.Playable.search(DBZ_PLAYLIST_URL)
        if not tracks:
            await self._respond(ctx, embed=build_error_embed("No se pudo cargar la playlist de DBZ."))
            return
        if isinstance(tracks, wavelink.Playlist):
            track_list = list(tracks.tracks)
            random.shuffle(track_list)
            for track in track_list:
                await player.queue.put_wait(track)
            await self._respond(ctx, embed=build_info_embed("🐉 Dragon Ball Z", f"Playlist añadida con {len(track_list)} canciones."))
        else:
            random.shuffle(tracks)
            for track in tracks:
                await player.queue.put_wait(track)
            await self._respond(ctx, embed=build_info_embed("🐉 Dragon Ball Z", f"Añadidas {len(tracks)} canciones."))
        if not player.playing and not player.paused:
            next_track = player.queue.get()
            await player.play(next_track)

    @commands.hybrid_command(name="anime", description="Reproduce la playlist de Anime")
    async def anime(self, ctx: commands.Context) -> None:
        ANIME_PLAYLIST_URL = "https://www.youtube.com/playlist?list=PLHPZvFJe7-ufMte_SHOhl1qncTTzjpkO7"
        if not self._is_lavalink_available():
            await ctx.send(embed=build_error_embed("El sistema de música no está disponible ahora."))
            return
        self._set_text_channel(ctx)
        player = await self._ensure_connected(ctx)
        if player is None:
            return
        await ctx.defer()
        tracks: wavelink.Search = await wavelink.Playable.search(ANIME_PLAYLIST_URL)
        if not tracks:
            await self._respond(ctx, embed=build_error_embed("No se pudo cargar la playlist de Anime."))
            return
        if isinstance(tracks, wavelink.Playlist):
            track_list = list(tracks.tracks)
            random.shuffle(track_list)
            for track in track_list:
                await player.queue.put_wait(track)
            await self._respond(ctx, embed=build_info_embed("🎌 Anime", f"Playlist añadida con {len(track_list)} canciones."))
        else:
            random.shuffle(tracks)
            for track in tracks:
                await player.queue.put_wait(track)
            await self._respond(ctx, embed=build_info_embed("🎌 Anime", f"Añadidas {len(tracks)} canciones."))
        if not player.playing and not player.paused:
            next_track = player.queue.get()
            await player.play(next_track)

    @commands.hybrid_command(name="coin", description="Lanza una moneda.")
    async def coin(self, ctx: commands.Context) -> None:
        result = random.choice(["Cara", "Sello"])
        await ctx.send(embed=build_info_embed("🪙 Moneda", f"Resultado: **{result}**"))


# ── Search select view ────────────────────────────────────────────────────────

class SearchSelectView(discord.ui.View):
    def __init__(self, tracks: list[wavelink.Playable], player_cog: Music, ctx: commands.Context) -> None:
        super().__init__(timeout=60)
        self.tracks = tracks
        self.player_cog = player_cog
        self.ctx = ctx
        self.add_item(SearchSelect(tracks, player_cog, ctx))


class SearchSelect(discord.ui.Select):
    def __init__(self, tracks: list[wavelink.Playable], player_cog: Music, ctx: commands.Context) -> None:
        self.tracks = tracks
        self.player_cog = player_cog
        self.ctx = ctx
        options = [
            discord.SelectOption(label=t.title[:100], description=(t.author or "")[:100], value=str(i))
            for i, t in enumerate(tracks)
        ]
        super().__init__(placeholder="Elige una canción…", options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        idx = int(self.values[0])
        track = self.tracks[idx]
        player = await self.player_cog._ensure_connected(self.ctx)
        if player is None:
            await interaction.response.send_message(embed=build_error_embed("No pude conectarme al canal de voz."), ephemeral=True)
            return
        if player.current is not None or player.playing or player.paused or not player.queue.is_empty:
            await player.queue.put_wait(track)
            song = _track_to_song(track)
            await interaction.response.send_message(embed=build_added_to_queue_embed(song, player.queue.count))
        else:
            await player.play(track)
            await interaction.response.send_message(embed=build_info_embed("▶️ Reproduciendo", f"**{track.title}**"))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Music(bot))
