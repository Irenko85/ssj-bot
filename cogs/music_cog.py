import asyncio
import contextlib
import discord
import math
import yt_dlp
import random
import os
import logging
import tempfile
import traceback
import shutil
import urllib.parse
from time import time
from utils import utils
from discord.ext import commands, tasks
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
    COLOR_WARNING,
)

# Configure logger
logger = logging.getLogger(__name__)

DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
FFMPEG_BEFORE_OPTIONS = (
    "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -nostdin"
)
FFMPEG_OPTIONS = {
    "before_options": FFMPEG_BEFORE_OPTIONS,
    "options": "-vn -b:a 192k",
}
YTDL_OPTIONS = {
    "format": "bestaudio[ext=webm]/bestaudio[ext=m4a]/bestaudio[ext=mp3]/bestaudio/best",
    "noplaylists": True,
    "quiet": True,
    "no_warnings": True,
    "playlist_items": "1",
    "extractor_args": {"youtube": {"player_client": ["tv", "ios", "android", "web"]}},
    "user_agent": DEFAULT_UA,
    "referer": "https://www.youtube.com/",
    "http_chunk_size": 10485760,
    "headers": {
        "User-Agent": DEFAULT_UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "en-US,en;q=0.9,es;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Sec-Ch-Ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Cache-Control": "max-age=0",
    },
}


class TrackUnavailableError(Exception):
    def __init__(self, track_id: str, reason: str):
        self.track_id = track_id
        self.reason = reason
        super().__init__(reason)


class SafeYoutubeDL(yt_dlp.YoutubeDL):
    """Wrapper that prevents cookie saving errors on read-only filesystems"""

    def close(self):
        try:
            super().close()
        except OSError as e:
            if "Read-only file system" in str(e):
                logger.debug("Ignoring read-only filesystem error when saving cookies")
            else:
                raise


_cookies_file = os.getenv("YTDL_COOKIES")
if _cookies_file:
    if os.path.exists(_cookies_file):
        logger.info(f"Loading cookies from: {_cookies_file}")
        # Copy to a writable temp location so yt-dlp can update them
        _tmp_cookies = os.path.join(tempfile.gettempdir(), "ssj_cookies.txt")
        try:
            shutil.copy(_cookies_file, _tmp_cookies)
            try:
                os.chmod(_tmp_cookies, 0o644)
            except OSError:
                pass
            YTDL_OPTIONS["cookiefile"] = _tmp_cookies
            logger.info(f"Cookies copied to writable location: {_tmp_cookies}")
        except Exception as e:
            logger.error(f"Failed to copy cookies to temp dir: {e}")
            logger.error(traceback.format_exc())
            logger.warning("Proceeding without cookies due to copy failure")
    else:
        logger.error(f"Cookies file not found: {_cookies_file}")
else:
    _cookies_from_browser = os.getenv("YTDL_COOKIES_FROM_BROWSER")
    if _cookies_from_browser:
        logger.info(f"Using cookies from browser: {_cookies_from_browser}")
        # Typical values: chrome, edge, brave, firefox
        YTDL_OPTIONS["cookiesfrombrowser"] = (_cookies_from_browser,)
    else:
        logger.warning("No cookies configured. YouTube may require authentication.")

DBZ_PLAYLIST_URL = "https://www.youtube.com/watch_videos?video_ids=YnL70cee6qo,5LVcwPrfNo4,GHja1cUmgsc,k6r8-AhAwmQ,4EPnL5oVnaw,9NXIo6PIb5I,lB3GO22VUPs,VfjKh7pqXNo,buaoMjom9XQ,Ecfux9RTmbY,UFjw-gSLy1w,GHIfsW3SPVk,OB0QCHxzl1s,3aevyrmqbY0,pYnLO7MVKno,uC8sc0cQa9M,8m3fIsHdKg8,y7RLCzAZFtU"
ANIME_PLAYLIST_URL = "https://www.youtube.com/playlist?list=PLHPZvFJe7-ufMte_SHOhl1qncTTzjpkO7&jct=DyxeqvyCylM2t3X00gNa8g"


class GuildState:
    """Per-guild music state. One instance per Discord server."""

    __slots__ = (
        "queue",
        "actual_song",
        "current_song",
        "last_activity",
        "inactivity_warned",
        "inactivity_channel",
        "now_playing_message",
        "_skip_republish",
    )

    def __init__(self) -> None:
        self.queue: list[dict] = []
        self.actual_song: str | None = None
        self.current_song: dict | None = None
        self.last_activity: float = time()
        self.inactivity_warned: bool = False
        self.inactivity_channel: discord.TextChannel | None = None
        self.now_playing_message: discord.Message | None = None
        self._skip_republish: bool = False


class Music(commands.Cog):
    EXTRACT_TIMEOUT_SECONDS = 30

    def __init__(self, bot):
        self.bot = bot
        self.states: dict[int, GuildState] = {}

    @staticmethod
    def _is_unavailable_error(error_msg: str) -> bool:
        keywords = [
            "Music Premium",
            "Premium",
            "not available",
            "unavailable",
            "Private video",
            "This video has been removed",
            "members only",
        ]
        lower = error_msg.lower()
        return any(keyword.lower() in lower for keyword in keywords)

    @staticmethod
    def _map_unavailable_reason(error_msg: str) -> str:
        lower = error_msg.lower()
        if "music premium" in lower or "premium" in lower:
            return "solo disponible para Premium"
        if "private video" in lower:
            return "video privado"
        if "not available" in lower or "unavailable" in lower:
            return "no disponible"
        if "members only" in lower:
            return "solo para miembros"
        if "removed" in lower or "this video has been removed" in lower:
            return "video eliminado"
        return error_msg[:60]

    @staticmethod
    def _extract_video_id(url: str) -> str:
        if "youtube.com/watch?v=" in url:
            parsed = urllib.parse.urlparse(url)
            return urllib.parse.parse_qs(parsed.query).get("v", [url])[0]
        if "youtu.be/" in url:
            return url.split("youtu.be/")[-1].split("?")[0]
        return url

    async def _extract_info(self, ydl, *args, **kwargs):
        """Run blocking ydl.extract_info in a worker thread, with timeout."""
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(ydl.extract_info, *args, **kwargs),
                timeout=self.EXTRACT_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.warning(
                f"extract_info timed out after {self.EXTRACT_TIMEOUT_SECONDS}s"
            )
            raise

    async def _extract_track_info(self, ydl_opts: dict, url: str):
        """Extract metadata for a single URL. Returns the info dict on success,
        or a TrackUnavailableError/Exception instance as a value on failure."""
        try:
            with SafeYoutubeDL(ydl_opts) as ydl:
                try:
                    info = await self._extract_info(ydl, url, download=False)
                    headers = self._extract_http_headers(info, ydl)
                except yt_dlp.utils.DownloadError as e:
                    if "Requested format is not available" in str(e):
                        fallback_opts = ydl_opts.copy()
                        fallback_opts["format"] = "best"
                        try:
                            with SafeYoutubeDL(fallback_opts) as ydl_fb:
                                info = await self._extract_info(
                                    ydl_fb, url, download=False
                                )
                                headers = self._extract_http_headers(info, ydl_fb)
                        except yt_dlp.utils.DownloadError as e2:
                            if self._is_unavailable_error(str(e2)):
                                reason_raw = str(e2)
                                mapped_reason = self._map_unavailable_reason(reason_raw)
                                video_id = self._extract_video_id(url)
                                return TrackUnavailableError(video_id, mapped_reason)
                            return e2
                    elif self._is_unavailable_error(str(e)):
                        reason_raw = str(e)
                        mapped_reason = self._map_unavailable_reason(reason_raw)
                        video_id = self._extract_video_id(url)
                        return TrackUnavailableError(video_id, mapped_reason)
                    else:
                        return e
                info["_precomputed_headers"] = headers
                return info
        except Exception as e:
            return e

    async def _enqueue_from_info(self, ctx, info: dict, silent: bool = False):
        """Build a song dict from already-extracted info and append to queue."""
        url = info["url"]
        title = info.get("title", "Título no encontrado")
        headers = info.get("_precomputed_headers")
        if headers is None:
            headers = self._extract_http_headers(info, None)
        song = {
            "title": title,
            "url": url,
            "headers": headers,
            "thumbnail": info.get("thumbnail"),
            "duration": info.get("duration"),
            "webpage_url": info.get("webpage_url"),
        }
        self._state(ctx).queue.append(song)
        if not silent:
            await ctx.send(
                embed=build_added_to_queue_embed(song, len(self._state(ctx).queue))
            )

    async def _select_first_playable_candidate(self, ydl, entries):
        """Iterate ytsearch entries and return info for the first candidate
        that extracts without DownloadError. Returns None if all fail or no
        entry has a usable id."""
        for entry in entries:
            video_id = entry.get("id") or entry.get("url")
            if not video_id:
                continue
            candidate_url = f"https://www.youtube.com/watch?v={video_id}"
            try:
                return await self._extract_info(
                    ydl, candidate_url, download=False
                )
            except yt_dlp.utils.DownloadError as e:
                reason = str(e)[:200]
                logger.warning(
                    f"Candidato {video_id} no disponible, probando otro: {reason}"
                )
                continue
        return None

    def _state(self, ctx_or_guild) -> GuildState:
        """Return (or create) the GuildState for the relevant guild."""
        guild = (
            ctx_or_guild.guild
            if hasattr(ctx_or_guild, "guild")
            else ctx_or_guild
        )
        return self.states.setdefault(guild.id, GuildState())

    def _cleanup_state(self, guild_id: int) -> None:
        """Drop the state for a guild. Idempotent."""
        self.states.pop(guild_id, None)

    async def cog_check(self, ctx) -> bool:
        """Reject any music command issued outside a guild (e.g. DMs)."""
        if ctx.guild is None:
            await ctx.send(embed=build_error_embed("Los comandos de música solo funcionan en servidores."))
            return False
        return True

    async def cog_after_invoke(self, ctx):
        """Re-publish the Now Playing embed at the bottom of the chat after any command."""
        s = self._state(ctx)
        if s._skip_republish:
            s._skip_republish = False
            return
        if s.current_song:
            try:
                await self._publish_now_playing(ctx, s.current_song)
            except discord.errors.DiscordServerError as e:
                logger.warning(
                    f"Discord API error al enviar embed de Now Playing: {type(e).__name__}: {e}"
                )

    def update_activity(self, ctx_or_guild) -> None:
        """Refresh the activity timestamp for the guild from `ctx_or_guild`."""
        s = self._state(ctx_or_guild)
        s.last_activity = time()
        s.inactivity_warned = False

    def _build_before_options(self, headers: dict | None) -> str:
        """Build ffmpeg options including headers if they exist."""
        before = FFMPEG_BEFORE_OPTIONS
        if headers:
            normalized = {
                str(k).title(): v for k, v in headers.items() if v is not None
            }
            user_agent = normalized.pop("User-Agent", None) or DEFAULT_UA
            referer = normalized.pop("Referer", None)
            esc = lambda v: str(v).replace('"', '\\"')

            if user_agent:
                before = f'{before} -user_agent "{esc(user_agent)}"'
            if referer:
                before = f'{before} -referer "{esc(referer)}"'

            if normalized:
                # ffmpeg expects headers separated by CRLF and with trailing CRLF
                header_lines = "".join(f"{k}: {v}\r\n" for k, v in normalized.items())
                header_lines = header_lines.replace('"', '\\"')
                before = f'{before} -headers "{header_lines}"'
        else:
            before = f'{before} -user_agent "{DEFAULT_UA}"'
        return before

    def _extract_http_headers(
        self, info: dict, ydl: yt_dlp.YoutubeDL | None
    ) -> dict | None:
        """Extract HTTP headers from multiple sources in priority order."""
        # Header sources in priority order
        sources = [
            info.get("http_headers"),
            next(
                (
                    fmt.get("http_headers")
                    for fmt in info.get("requested_formats", []) or []
                    if fmt.get("http_headers")
                ),
                None,
            ),
            next(
                (
                    fmt.get("http_headers")
                    for fmt in info.get("formats", []) or []
                    if fmt.get("http_headers")
                ),
                None,
            ),
            ydl.params.get("http_headers") if ydl else None,
        ]

        # Return the first non-null header
        return next((h for h in sources if h), None)

    async def _send_embed(self, ctx, embed, *, ephemeral: bool = False):
        """Helper para enviar embeds respetando el modo ephemeral."""
        if ephemeral and ctx.interaction is not None:
            return await ctx.send(embed=embed, ephemeral=True)
        return await ctx.send(embed=embed)

    async def _publish_now_playing(self, ctx, song: dict):
        """Envía el mensaje de Now Playing con embed + botones, siempre al final del chat."""
        s = self._state(ctx)
        embed = build_now_playing_embed(song)
        view = make_music_control_view(self.bot, music_cog=self)

        if s.now_playing_message is not None:
            try:
                await s.now_playing_message.delete()
            except Exception:
                pass
            s.now_playing_message = None

        s.now_playing_message = await ctx.send(embed=embed, view=view)
        return s.now_playing_message

    async def _finalize_now_playing(self, ctx, message: str):
        """Deshabilita los botones del mensaje Now Playing cuando termina la reproducción."""
        s = self._state(ctx)
        s.actual_song = None
        s.current_song = None

        if s.now_playing_message is None:
            return

        view = make_music_control_view(self.bot, music_cog=self, disabled=True)

        try:
            await s.now_playing_message.edit(
                embed=build_info_embed("⏹ Reproducción finalizada", message),
                view=view,
            )
        except Exception:
            pass

    async def play_next_in_queue(self, ctx):
        s = self._state(ctx)
        logger.debug(
            f"play_next_in_queue llamado en guild={ctx.guild.id}, canciones en cola: {len(s.queue)}"
        )

        if len(s.queue) == 0:
            await self._finalize_now_playing(ctx, "La cola terminó.")
            return

        # Verify that voice_client is available and connected
        if not ctx.voice_client or not ctx.voice_client.is_connected():
            logger.error("voice_client no está conectado en play_next_in_queue")
            await ctx.send(embed=build_error_embed("El bot no está conectado a un canal de voz."))
            return

        s.actual_song = s.queue[0]["title"]
        song = s.queue.pop(0)
        s.current_song = song
        logger.info(
            "starting playback in guild %s: %r",
            ctx.guild.id if ctx.guild else None, s.actual_song,
        )
        url = song["url"]
        logger.debug(f"Preparando reproducción: {song['title']}")
        logger.debug(
            f"URL de audio: {url[:100]}..."
        )  # Show only the first 100 characters

        try:
            logger.debug("Creando FFmpegOpusAudio source...")
            before_options = self._build_before_options(song.get("headers"))
            source = discord.FFmpegOpusAudio(
                url,
                before_options=before_options,
                options=FFMPEG_OPTIONS["options"],
            )
            logger.debug("Source creado exitosamente")

            logger.debug("Iniciando reproducción...")
            ctx.voice_client.play(
                source,
                after=lambda e: self.bot.loop.create_task(
                    self._after_play(ctx, e, song["title"])
                ),
            )
            logger.debug("Reproducción iniciada")
            self.update_activity(ctx)  # Update activity when playing
        except Exception as e:
            logger.error(
                f"Exception en play_next_in_queue: {type(e).__name__}: {e}"
            )
            logger.error(traceback.format_exc())
            await self._send_embed(
                ctx,
                build_error_embed(
                    f"Error al reproducir **{song['title']}**. Intentando con la siguiente canción..."
                ),
            )
            # Try to play the next song
            await self.play_next_in_queue(ctx)
            return

        s._skip_republish = True
        try:
            await self._publish_now_playing(ctx, song)
        except discord.errors.DiscordServerError as e:
            logger.warning(
                f"Discord API error al enviar embed de Now Playing: {type(e).__name__}: {e}"
            )
        finally:
            s._skip_republish = False

    async def _after_play(self, ctx, error, song_title):
        """Callback que se ejecuta después de que termina una canción"""
        if error:
            logger.error(f"Error durante la reproducción de '{song_title}': {error}")
        else:
            logger.debug(f"Canción '{song_title}' terminó correctamente")
        await self.play_next_in_queue(ctx)

    async def join_voice_channel(self, ctx):
        try:
            if ctx.author.voice:
                channel = ctx.author.voice.channel
                logger.debug(f"Canal objetivo: {channel.name}")
                logger.debug(f"ctx.voice_client actual: {ctx.voice_client}")

                if ctx.voice_client is None or not ctx.voice_client.is_connected():
                    logger.debug(f"Conectando al canal de voz: {channel.name}")
                    try:
                        voice_client = await channel.connect(
                            timeout=10.0, reconnect=True
                        )
                        logger.debug(
                            f"Conexión establecida. voice_client: {voice_client}"
                        )
                    except asyncio.TimeoutError:
                        logger.error("Timeout al conectar al canal de voz")
                        await ctx.send(
                            embed=build_error_embed("Tiempo de espera agotado al conectar al canal de voz.")
                        )
                        return False
                    except Exception as e:
                        logger.error(f"Error al conectar: {type(e).__name__}: {e}")
                        logger.error(traceback.format_exc())
                        await ctx.send(embed=build_error_embed(f"Error al conectar al canal de voz: {e}"))
                        return False

                    # Add a small delay to ensure the connection is ready
                    await asyncio.sleep(0.5)
                    logger.debug(
                        f"Conectado exitosamente. voice_client: {ctx.voice_client}"
                    )
                    logger.debug(f"is_connected: {ctx.voice_client.is_connected()}")
                    self.update_activity(ctx)  # Update activity when connecting
                elif ctx.voice_client.channel != channel:
                    logger.debug(f"Moviendo al canal de voz: {channel.name}")
                    await ctx.voice_client.move_to(channel)
                    await asyncio.sleep(0.5)
                    self.update_activity(ctx)  # Update activity when moving
                else:
                    logger.debug(f"Ya está conectado al canal: {channel.name}")

                logger.debug("join_voice_channel completado exitosamente")
                return True
            else:
                logger.debug("El usuario no está en un canal de voz")
                await ctx.send(
                    embed=build_error_embed("Necesitas estar en un canal de voz para usar este comando.")
                )
                return False
        except Exception as e:
            logger.error(f"Exception en join_voice_channel: {type(e).__name__}: {e}")
            logger.error(traceback.format_exc())
            await ctx.send(embed=build_error_embed("Error inesperado al unirse al canal de voz."))
            return False

    async def play_playlist(self, ctx, playlist_url: str, shuffle: bool = False):
        if not await self.join_voice_channel(ctx):
            return

        video_urls = await utils.get_video_urls_from_playlist(playlist_url)
        if not video_urls:
            await ctx.send(embed=build_error_embed("No se pudo cargar la playlist."))
            return

        if shuffle:
            random.shuffle(video_urls)

        # FASE 1: parallel extraction with semaphore
        sem = asyncio.Semaphore(3)

        async def extract_one(url):
            async with sem:
                ydl_opts = YTDL_OPTIONS.copy()
                if not hasattr(self, '_verbose_logged'):
                    ydl_opts['verbose'] = True
                    self._verbose_logged = True
                    logger.info("Enabling verbose yt-dlp logging for first extraction")
                result = await self._extract_track_info(ydl_opts, url)
                return (url, result)

        results = await asyncio.gather(*[extract_one(url) for url in video_urls])

        # FASE 2: sequential enqueue (touches shared state)
        skipped = []
        other_errors = []
        added_count = 0

        for url, result in results:
            if isinstance(result, TrackUnavailableError):
                skipped.append({"title": result.track_id, "reason": result.reason})
            elif isinstance(result, Exception):
                other_errors.append(str(result)[:60])
                logger.error(f"Error encolando {url}: {result}")
            else:
                await self._enqueue_from_info(ctx, result, silent=True)
                added_count += 1

        if skipped:
            embed = discord.Embed(
                title="⚠️ Canciones no añadidas",
                colour=COLOR_WARNING,
            )
            lines = [f"No se agregaron **{len(skipped)}** canciones a la cola:"]
            reasons = [s["reason"] for s in skipped]
            if len(set(reasons)) == 1:
                reason = reasons[0][:40] + ("…" if len(reasons[0]) > 40 else "")
                lines.append(f"\n{len(skipped)} canciones no disponibles — {reason}")
            else:
                for s in skipped[:10]:
                    title_str = s["title"][:50] + ("…" if len(s["title"]) > 50 else "")
                    reason_str = s["reason"][:40] + ("…" if len(s["reason"]) > 40 else "")
                    line = f"• {title_str} — {reason_str}"
                    if len(line) > 80:
                        line = line[:79] + "…"
                    lines.append(line)
                remaining = len(skipped) - 10
                if remaining > 0:
                    lines.append(f"...y {remaining} más")
            embed.description = "\n".join(lines)
            await ctx.send(embed=embed)

        if other_errors:
            embed = discord.Embed(
                title="⚠️ Errores al procesar playlist",
                colour=COLOR_WARNING,
            )
            lines = ["Se encontraron errores al procesar algunas canciones:"]
            for err in other_errors[:5]:
                lines.append(f"• {err[:77]}" if len(err) > 77 else f"• {err}")
            remaining = len(other_errors) - 5
            if remaining > 0:
                lines.append(f"...y {remaining} más")
            embed.description = "\n".join(lines)
            await ctx.send(embed=embed)

        self.start_inactivity_check(ctx)
        if added_count == 0:
            await ctx.send(
                embed=build_warning_embed("No se pudo agregar ninguna canción a la cola.")
            )
            return

        await ctx.send(
            embed=build_info_embed(
                "Playlist añadida", "Se agregó la playlist a la cola."
            )
        )

        if ctx.voice_client and ctx.voice_client.is_connected():
            if not ctx.voice_client.is_playing():
                await self.play_next_in_queue(ctx)

    def start_inactivity_check(self, ctx):
        """Make sure the per-guild inactivity loop is tracking this guild."""
        logger.debug(
            f"start_inactivity_check llamado para guild={ctx.guild.id}"
        )
        s = self._state(ctx)
        s.inactivity_channel = ctx.channel
        self.update_activity(ctx)

        if not self.check_inactivity.is_running():
            logger.debug("Iniciando check_inactivity loop")
            self.check_inactivity.start()
        else:
            logger.debug("check_inactivity ya está corriendo")

    @commands.hybrid_command(name="dbz", description="Reproduce la playlist de Dragon Ball Z")
    async def dbz(self, ctx: commands.Context):
        logger.info("dbz invoked by %s in guild %s", ctx.author, ctx.guild.id if ctx.guild else None)
        await ctx.defer()
        if not await self.join_voice_channel(ctx):
            return
        await self.play_playlist(ctx, DBZ_PLAYLIST_URL, shuffle=True)

    @commands.hybrid_command(name="anime", description="Reproduce la playlist de Anime")
    async def anime(self, ctx: commands.Context):
        logger.info("anime invoked by %s in guild %s", ctx.author, ctx.guild.id if ctx.guild else None)
        await ctx.defer()
        if not await self.join_voice_channel(ctx):
            return
        await self.play_playlist(ctx, ANIME_PLAYLIST_URL, shuffle=True)

    @commands.hybrid_command(name="play", description="Play a song or playlist")
    async def play(self, ctx: commands.Context, *, search: str):
        logger.info(
            "play invoked by %s in guild %s: query=%r",
            ctx.author, ctx.guild.id if ctx.guild else None, search,
        )
        await ctx.defer()
        await self._play_internal(ctx, search, silent=False)

    async def _play_internal(self, ctx, search: str, silent: bool = False):
        try:
            logger.debug(f"Comando play ejecutado con search: {search}")
            join_result = await self.join_voice_channel(ctx)
            logger.debug(f"join_voice_channel retornó: {join_result}")

            if not join_result:
                logger.debug("No se pudo unir al canal de voz")
                return

            logger.debug(
                f"Bot conectado al canal de voz: {ctx.voice_client.channel.name}"
            )
        except Exception as e:
            logger.error(f"Exception al inicio de play(): {type(e).__name__}: {e}")
            logger.error(traceback.format_exc())
            await ctx.send(embed=build_error_embed("Error al iniciar la reproducción."))
            return

        async with ctx.typing():
            is_url = "youtube.com" in search or "youtu.be" in search
            is_playlist = "playlist?list=" in search or "&list=" in search
            logger.debug(f"is_url: {is_url}, is_playlist: {is_playlist}")

            try:
                if is_url and is_playlist:
                    logger.debug("Procesando playlist...")
                    video_urls = await utils.get_video_urls_from_playlist(search)
                    if not video_urls:
                        await ctx.send(
                            embed=build_error_embed("No se pudieron obtener canciones de la playlist.")
                        )
                        return

                    await ctx.send(
                        embed=build_info_embed("Procesando playlist", f"Agregando {len(video_urls)} canciones a la cola...")
                    )
                    await self.play_playlist(ctx, search)
                else:
                    logger.debug("Procesando video individual...")
                    logger.debug(f"YTDL_OPTIONS cookiefile: {YTDL_OPTIONS.get('cookiefile')}")

                    # Enable verbose logging for first extraction to debug
                    debug_opts = YTDL_OPTIONS.copy()
                    if not hasattr(self, '_verbose_logged'):
                        debug_opts['verbose'] = True
                        self._verbose_logged = True
                        logger.info("Enabling verbose yt-dlp logging for first extraction")

                    with SafeYoutubeDL(debug_opts) as ydl:
                        logger.debug(f"YoutubeDL instance cookiefile: {ydl.params.get('cookiefile')}")
                        if is_url:
                            logger.debug(f"Limpiando URL: {search}")
                            search = utils.clean_yt_link(search)
                            logger.debug(f"URL limpio: {search}")
                            logger.debug("Extrayendo información del video...")
                            active_ydl = ydl
                            precomputed_headers = None
                            try:
                                info = await self._extract_info(ydl, search, download=False)
                            except yt_dlp.utils.DownloadError as e:
                                if "Requested format is not available" in str(e):
                                    logger.warning(
                                        "Format no disponible, reintentando con format=best"
                                    )
                                    fallback_opts = YTDL_OPTIONS.copy()
                                    fallback_opts["format"] = "best"
                                    try:
                                        with SafeYoutubeDL(fallback_opts) as ydl_fb:
                                            info = await self._extract_info(
                                                ydl_fb, search, download=False
                                            )
                                            active_ydl = ydl_fb
                                            precomputed_headers = self._extract_http_headers(
                                                info, ydl_fb
                                            )
                                    except yt_dlp.utils.DownloadError as e2:
                                        if self._is_unavailable_error(str(e2)):
                                            reason = self._map_unavailable_reason(str(e2))
                                            video_id = self._extract_video_id(search)
                                            if not silent:
                                                await ctx.send(
                                                    embed=build_error_embed(
                                                        f"⏭ Este track no está disponible: {reason}"
                                                    )
                                                )
                                                return
                                            raise TrackUnavailableError(video_id, reason)
                                        raise
                                elif self._is_unavailable_error(str(e)):
                                    reason_raw = str(e)
                                    mapped_reason = self._map_unavailable_reason(reason_raw)
                                    video_id = self._extract_video_id(search)
                                    if silent:
                                        logger.warning(f"Track no disponible (silencioso): {mapped_reason}")
                                        raise TrackUnavailableError(video_id, mapped_reason)
                                    logger.warning(f"Track no disponible: {mapped_reason}")
                                    await ctx.send(
                                        embed=build_error_embed(
                                            f"⏭ Este track no está disponible: {mapped_reason}"
                                        )
                                    )
                                    return
                                else:
                                    raise
                            url = info["url"]
                            title = info.get("title", "Título no encontrado")
                            headers = precomputed_headers or self._extract_http_headers(
                                info, active_ydl
                            )
                            logger.debug(f"Video extraído: {title}")
                        else:
                            logger.debug(f"Buscando en YouTube: {search}")
                            search_opts = YTDL_OPTIONS.copy()
                            search_opts["extract_flat"] = True
                            search_opts["skip_download"] = True
                            search_opts.pop("playlist_items", None)
                            with SafeYoutubeDL(search_opts) as ydl_search:
                                search_info = await self._extract_info(
                                    ydl_search, f"ytsearch5:{search}", download=False
                                )
                            entries = list(search_info.get("entries") or [])[:5]
                            if not entries:
                                await ctx.send(embed=build_error_embed("No se encontraron resultados."))
                                return
                            entries = [
                                e for e in entries if e.get("ie_key") == "Youtube"
                            ]
                            if not entries:
                                await ctx.send(
                                    embed=build_error_embed("No se encontraron videos reproducibles.")
                                )
                                return

                            info = await self._select_first_playable_candidate(
                                ydl, entries
                            )

                            if not info:
                                await ctx.send(
                                    embed=build_error_embed("No se encontró un formato compatible para los resultados.")
                                )
                                return

                            url = info["url"]
                            title = info["title"]
                            headers = self._extract_http_headers(info, ydl)
                            logger.debug(f"Video encontrado: {title}")

                        logger.debug(f"Agregando a la cola: {title}")
                        song = {
                            "title": title,
                            "url": url,
                            "headers": headers,
                            "thumbnail": info.get("thumbnail"),
                            "duration": info.get("duration"),
                            "webpage_url": info.get("webpage_url"),
                        }
                        self._state(ctx).queue.append(song)
                        if not silent:
                            logger.debug("Enviando mensaje de confirmación...")
                            await ctx.send(
                                embed=build_added_to_queue_embed(song, len(self._state(ctx).queue))
                            )
                            logger.debug("Mensaje enviado")

            except Exception as e:
                logger.error(f"Exception en play(): {type(e).__name__}: {e}")
                logger.error(traceback.format_exc())
                if silent:
                    raise
                await ctx.send(
                    embed=build_error_embed("Ocurrió un error al intentar procesar la canción o playlist.")
                )
                logger.debug("Mensaje de error enviado al chat")

        self.start_inactivity_check(ctx)

        logger.debug("Verificando estado del voice_client antes de reproducir...")
        logger.debug(f"voice_client: {ctx.voice_client}")
        logger.debug(
            f"is_connected: {ctx.voice_client.is_connected() if ctx.voice_client else 'N/A'}"
        )
        logger.debug(
            f"is_playing: {ctx.voice_client.is_playing() if ctx.voice_client else 'N/A'}"
        )
        logger.debug(f"Queue length: {len(self._state(ctx).queue)}")

        if ctx.voice_client and ctx.voice_client.is_connected():
            if not ctx.voice_client.is_playing():
                logger.debug("Iniciando reproducción desde la cola...")
                await self.play_next_in_queue(ctx)
            else:
                logger.debug("Ya hay una canción reproduciéndose")
        else:
            logger.error("voice_client no está conectado después de join_voice_channel")
            await ctx.send(embed=build_error_embed("No se pudo establecer conexión con el canal de voz."))

    @commands.hybrid_command(name="stop", description="Stops playback and leaves the voice channel.")
    async def stop(self, ctx: commands.Context):
        if ctx.voice_client:
            s = self._state(ctx)
            s.queue.clear()
            ctx.voice_client.stop()
            await ctx.voice_client.disconnect()
            await self._finalize_now_playing(ctx, "Reproducción detenida.")
            await ctx.send(embed=build_info_embed("⏹ Detenido", "Reproducción detenida."))
            self._cleanup_state(ctx.guild.id)
            # The check_inactivity loop stops itself once self.states is empty

    @commands.hybrid_command(name="skip", description="Skips the current song.")
    async def skip(self, ctx: commands.Context):
        logger.info("skip invoked by %s in guild %s", ctx.author, ctx.guild.id if ctx.guild else None)
        if ctx.voice_client and ctx.voice_client.is_playing():
            s = self._state(ctx)
            s.current_song = None
            ctx.voice_client.stop()
            await ctx.send(embed=build_info_embed("⏭ Skipeado", "Se skipeó la canción actual."))
            self.update_activity(ctx)  # Update activity when skipping
        else:
            await ctx.send(embed=build_error_embed("No hay nada que skipear."))

    @commands.hybrid_command(name="pause", description="Pauses the current song.")
    async def pause(self, ctx: commands.Context):
        logger.info("pause invoked by %s in guild %s", ctx.author, ctx.guild.id if ctx.guild else None)
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.pause()
            await ctx.send(embed=build_info_embed("⏸ Pausado", "Se ha pausado la reproducción."))
            self.update_activity(ctx)  # Update activity when pausing
        else:
            await ctx.send(embed=build_error_embed("No hay nada reproduciéndose para pausar."))

    @commands.hybrid_command(name="resume", description="Resumes the paused song.")
    async def resume(self, ctx: commands.Context):
        logger.info("resume invoked by %s in guild %s", ctx.author, ctx.guild.id if ctx.guild else None)
        if ctx.voice_client and ctx.voice_client.is_paused():
            ctx.voice_client.resume()
            await ctx.send(embed=build_info_embed("▶ Reanudado", "Se ha reanudado la reproducción."))
            self.update_activity(ctx)  # Update activity when resuming
        else:
            await ctx.send(embed=build_error_embed("No hay nada pausado para reanudar."))

    @commands.hybrid_command(name="queue", description="Displays the current song queue.")
    async def queue(self, ctx: commands.Context):
        s = self._state(ctx)
        if s.queue:
            embed = build_queue_embed(s.queue, s.actual_song, page=1)
            total_pages = max(1, math.ceil(len(s.queue) / 10))
            if total_pages > 1:
                view = QueuePaginationView(s.queue, s.actual_song)
                msg = await ctx.send(embed=embed, view=view)
                view.message = msg
            else:
                await ctx.send(embed=embed)
        else:
            await ctx.send(embed=build_info_embed("📋 Cola de reproducción", "La cola está vacía."))
        self.update_activity(ctx)  # Update activity when viewing queue

    @commands.hybrid_command(
        name="rq", description="Removes a song from the queue by its position in the list."
    )
    async def remove_from_queue(self, ctx: commands.Context, position: int):
        s = self._state(ctx)
        if not s.queue:
            await ctx.send(embed=build_error_embed("La cola está vacía."))
            return

        try:
            removed = s.queue.pop(position - 1)
            await ctx.send(embed=build_info_embed("🗑️ Eliminado", f"Se ha eliminado de la cola: **{removed['title']}**"))
            self.update_activity(ctx)  # Update activity when removing song
        except IndexError:
            await ctx.send(
                embed=build_warning_embed("Posición inválida. Asegúrate de que el número esté dentro del rango de la cola.")
            )

    @commands.hybrid_command(name="clear", description="Clears the song queue.")
    async def clear(self, ctx: commands.Context):
        self._state(ctx).queue.clear()
        await ctx.send(embed=build_info_embed("🧹 Cola vaciada", "La cola se vació."))
        self.update_activity(ctx)  # Update activity when clearing queue

    @commands.hybrid_command(name="shuffle", description="Shuffles the song queue.")
    async def shuffle(self, ctx: commands.Context):
        s = self._state(ctx)
        if len(s.queue) > 0:
            random.shuffle(s.queue)
            await ctx.invoke(self.bot.get_command("queue"))
            self.update_activity(ctx)  # Update activity when shuffling
        else:
            await ctx.send(embed=build_warning_embed("La cola está vacía."))

    @commands.hybrid_command(name="coin", description="Flips a coin.")
    async def coin(self, ctx: commands.Context):
        logger.info("coin invoked by %s in guild %s", ctx.author, ctx.guild.id if ctx.guild else None)
        result = random.choice(["Cara", "Sello"])
        await ctx.send(embed=build_info_embed("🪙 Moneda", f"Resultado: **{result}**"))

    @tasks.loop(seconds=15)
    async def check_inactivity(self):
        """Per-guild inactivity check. Disconnects only the guilds that timed out."""
        INACTIVITY_TIMEOUT = 300  # 5 minutes
        WARNING_TIME = 240  # Warn at 4 minutes

        # If no guild is being tracked, stop the loop
        if not self.states:
            logger.debug("check_inactivity: sin estados activos, deteniendo loop")
            self.check_inactivity.stop()
            return

        current_time = time()

        # Iterate over a snapshot to allow safe mutation via _cleanup_state
        for guild_id, s in list(self.states.items()):
            try:
                guild = self.bot.get_guild(guild_id)
                voice_client = (
                    discord.utils.get(self.bot.voice_clients, guild=guild)
                    if guild
                    else None
                )

                # Bot is not connected to voice in this guild — drop state
                if not voice_client or not voice_client.is_connected():
                    logger.debug(
                        f"check_inactivity: guild={guild_id} sin voice_client, limpiando"
                    )
                    self._cleanup_state(guild_id)
                    continue

                # Active by definition: playing, paused, or queued
                if (
                    voice_client.is_playing()
                    or voice_client.is_paused()
                    or len(s.queue) > 0
                ):
                    s.last_activity = current_time
                    s.inactivity_warned = False
                    continue

                time_since_activity = current_time - s.last_activity

                # Disconnect immediately if the channel is empty (only bot left)
                channel = voice_client.channel
                if channel:
                    members_in_channel = [
                        m for m in channel.members if not m.bot
                    ]
                    if not members_in_channel:
                        await voice_client.disconnect()
                        await self._finalize_now_playing(guild, "No hay usuarios en el canal.")
                        if s.inactivity_channel:
                            await s.inactivity_channel.send(
                                embed=build_info_embed("⏹ Desconectado", "No hay usuarios en el canal.")
                            )
                        self._cleanup_state(guild_id)
                        continue

                # Warning a minute before disconnect
                if (
                    time_since_activity > WARNING_TIME
                    and not s.inactivity_warned
                ):
                    s.inactivity_warned = True
                    if s.inactivity_channel:
                        remaining_time = int(
                            INACTIVITY_TIMEOUT - time_since_activity
                        )
                        await s.inactivity_channel.send(
                            embed=build_warning_embed(
                                f"El bot se desconectará en {remaining_time} segundos por inactividad. "
                                f"Usa cualquier comando de música para mantener la conexión."
                            )
                        )

                # Disconnect for inactivity
                if time_since_activity > INACTIVITY_TIMEOUT:
                    await voice_client.disconnect()
                    await self._finalize_now_playing(guild, "Bot desconectado por inactividad.")
                    if s.inactivity_channel:
                        await s.inactivity_channel.send(
                            embed=build_info_embed("⏹ Desconectado", "Bot desconectado por inactividad.")
                        )
                    self._cleanup_state(guild_id)

            except Exception as e:
                logger.error(
                    f"Error en check_inactivity para guild={guild_id}: {e}"
                )
                # Continue with the other guilds; do not stop the whole loop
                continue

    @commands.hybrid_command(name="search", description="Searches for a song on YouTube.")
    async def search(self, ctx: commands.Context, *, query: str):
        logger.info(
            "search invoked by %s in guild %s: query=%r",
            ctx.author, ctx.guild.id if ctx.guild else None, query,
        )
        await ctx.defer(ephemeral=ctx.interaction is not None)
        search_options = YTDL_OPTIONS.copy()
        search_options.pop("playlist_items", None)
        search_options["extract_flat"] = True

        entries = []
        async with ctx.typing():
            with SafeYoutubeDL(search_options) as ydl:
                try:
                    info = await self._extract_info(ydl, f"ytsearch5:{query}", download=False)
                    entries = info.get("entries", [])
                except Exception as e:
                    await ctx.send(embed=build_error_embed("Ocurrió un error al buscar la canción."))
                    logger.error(f"Error en search: {e}")
                    return

        if not entries:
            await ctx.send(embed=build_error_embed("No se encontraron resultados."))
            return

        view = SearchView(entries, self, ctx)
        await ctx.send(
            embed=build_search_results_embed(entries),
            view=view,
            ephemeral=ctx.interaction is not None,
        )
        self.update_activity(ctx)  # Update activity when searching


class SearchSelect(discord.ui.Select):
    def __init__(self, entries, music_cog, ctx):
        self.entries = entries
        self.music_cog = music_cog
        self.ctx = ctx

        options = [
            discord.SelectOption(label=entry["title"], value=str(i))
            for i, entry in enumerate(entries)
        ]
        super().__init__(
            placeholder="Selecciona una canción para reproducir",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        # Acknowledge immediately — heavy work follows
        await interaction.response.defer()

        index = int(self.values[0])
        selected_entry = self.entries[index]
        title = selected_entry["title"]
        logger.info(
            "search selection by %s in guild %s: %r",
            interaction.user,
            interaction.guild.id if interaction.guild else None,
            title,
        )

        video_id = selected_entry["id"]
        if not video_id:
            await interaction.followup.send(
                embed=build_error_embed("No se encontró el ID del video."), ephemeral=True
            )
            return

        try:
            url = f"https://www.youtube.com/watch?v={video_id}"
            with SafeYoutubeDL(YTDL_OPTIONS) as ydl:
                info = await self.music_cog._extract_info(ydl, url, download=False)
                url = info["url"]
                headers = self.music_cog._extract_http_headers(info, ydl)
        except Exception as e:
            await interaction.followup.send(
                embed=build_error_embed("Error al obtener la URL del video."), ephemeral=True
            )
            logger.error(f"Error obteniendo URL en SearchSelect: {e}")
            return

        full_url = info.get("url", None)
        if not full_url:
            await interaction.followup.send(
                embed=build_error_embed("No se encontró la URL del video."), ephemeral=True
            )
            return

        if not await self.music_cog.join_voice_channel(self.ctx):
            return

        song = {
            "title": title,
            "url": full_url,
            "headers": headers,
            "thumbnail": info.get("thumbnail"),
            "duration": info.get("duration"),
            "webpage_url": info.get("webpage_url"),
        }
        self.music_cog._state(self.ctx).queue.append(song)
        await interaction.followup.send(
            embed=build_added_to_queue_embed(song, len(self.music_cog._state(self.ctx).queue))
        )

        self.music_cog.update_activity(self.ctx)

        if not self.ctx.voice_client.is_playing():
            await self.music_cog.play_next_in_queue(self.ctx)

        with contextlib.suppress(discord.errors.NotFound):
            await interaction.message.delete()
        self.view.stop()


class SearchView(discord.ui.View):
    def __init__(self, entries, music_cog, ctx, timeout=30):
        super().__init__(timeout=timeout)
        self.author = ctx.author
        self.add_item(SearchSelect(entries, music_cog, ctx))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.author:
            await interaction.response.send_message(
                embed=build_warning_embed("No puedes interactuar con este menú."), ephemeral=True
            )
            return False
        return True


async def setup(bot):
    await bot.add_cog(Music(bot))
