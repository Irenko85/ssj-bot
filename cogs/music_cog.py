import discord
import yt_dlp
import random
from time import time
from utils import utils
from discord.ext import commands, tasks

FFMPEG_OPTIONS = {
    "options": "-vn",
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
}
YTDL_OPTIONS = {
    "format": "bestaudio",
    "noplaylists": True,
    "quiet": True,
    "no_warnings": True,
    "playlist_items": "1",
}


class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.queue = []
        self.actual_song = None
        self.inactivity_channel = None  # Channel for inactivity messages
        self.last_activity_timestamp = None

    async def play_next_in_queue(self, ctx):
        if len(self.queue) > 0:
            self.actual_song = self.queue[0]["title"]
            song = self.queue.pop(0)
            url = song["url"]
            source = await discord.FFmpegOpusAudio.from_probe(url, **FFMPEG_OPTIONS)
            ctx.voice_client.play(
                source,
                after=lambda _: self.bot.loop.create_task(self.play_next_in_queue(ctx)),
            )
            await ctx.send(f"Reproduciendo: **{song['title']}**")

    async def join_voice_channel(self, ctx):
        if ctx.author.voice:
            channel = ctx.author.voice.channel
            if ctx.voice_client is None or not ctx.voice_client.is_connected():
                await channel.connect()
            elif ctx.voice_client.channel != channel:
                await ctx.voice_client.move_to(channel)
            return True
        else:
            await ctx.send("Necesitas estar en un canal de voz para usar este comando.")
            return False

    @commands.command(name="play", aliases=["p"], description="Play a song")
    async def play(self, ctx, *, search: str):
        self.inactivity_channel = (
            ctx.channel
        )  # Set the inactivity channel to the current channel
        if not await self.join_voice_channel(ctx):
            return

        async with ctx.typing():
            is_url = "youtube.com/watch" in search or "youtu.be" in search
            with yt_dlp.YoutubeDL(YTDL_OPTIONS) as ydl:
                try:
                    if is_url:
                        search = utils.clean_yt_link(search)
                        info = ydl.extract_info(search, download=False)
                        url = info["url"]
                        title = info.get("title", "Título no encontrado")
                    else:
                        info = ydl.extract_info(f"ytsearch:{search}", download=False)[
                            "entries"
                        ][0]
                        url = info["url"]
                        title = info["title"]

                    self.queue.append({"title": title, "url": url})
                    self.last_activity_timestamp = time()
                    if not self.check_inactivity.is_running():
                        self.check_inactivity.start(
                            ctx
                        )  # Start checking for inactivity
                    await ctx.send(f"Se agregó a la cola: **{title}**")
                except Exception as e:
                    await ctx.send(
                        "Ocurrió un error al intentar reproducir la canción."
                    )
                    print(f"Error: {e}")

        if not ctx.voice_client.is_playing():
            await self.play_next_in_queue(ctx)

    @commands.command(name="stop", help="Stops playback and leaves the voice channel.")
    async def stop(self, ctx):
        if ctx.voice_client:
            self.queue.clear()
            ctx.voice_client.stop()
            await ctx.voice_client.disconnect()
            await ctx.send("Reproducción detenida. CHAO CTM!")

    @commands.command(name="skip", aliases=["s"], help="Skips the current song.")
    async def skip(self, ctx):
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.stop()

    @commands.command(name="pause", help="Pauses the current song.")
    async def pause(self, ctx):
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.pause()
            await ctx.send("Se ha pausado la reproducción.")

    @commands.command(name="resume", aliases=["r"], help="Resumes the paused song.")
    async def resume(self, ctx):
        if ctx.voice_client and ctx.voice_client.is_paused():
            ctx.voice_client.resume()
            await ctx.send("Se ha reanudado la reproducción.")

    @commands.command(
        name="queue", aliases=["q"], help="Displays the current song queue."
    )
    async def queue(self, ctx):
        if self.queue:
            queue_list = "\n".join(
                f"{i+1}. {song['title']}" for i, song in enumerate(self.queue)
            )
            await ctx.send(
                f"Reproduciendo: **{self.actual_song}**\nCanciones en cola ({len(self.queue)}):\n**{queue_list}**"
            )
        else:
            await ctx.send("La cola está vacía.")

    @commands.command(
        name="rq", help="Removes a song from the queue by its position in the list."
    )
    async def remove_from_queue(self, ctx, position: int):
        if not self.queue:
            await ctx.send("La cola está vacía.")
            return

        try:
            removed = self.queue.pop(position - 1)
            await ctx.send(f"Se ha eliminado de la cola: **{removed['title']}**")
        except IndexError:
            await ctx.send(
                "Posición inválida. Asegúrate de que el número esté dentro del rango de la cola."
            )

    @commands.command(name="clear", aliases=["qc"], help="Clears the song queue.")
    async def clear(self, ctx):
        self.queue.clear()
        await ctx.send("La cola se vació.")

    @commands.command(name="shuffle", help="Shuffles the song queue.")
    async def shuffle(self, ctx):
        if len(self.queue) > 0:
            random.shuffle(self.queue)
            await ctx.invoke(self.bot.get_command("queue"))
        else:
            await ctx.send("La cola está vacía.")

    @commands.command(name="coin", aliases=["random"], help="Flips a coin.")
    async def coin(self, ctx):
        result = random.choice(["Cara", "Sello"])
        await ctx.send(f"Resultado: **{result}**")

    @tasks.loop(seconds=10)
    async def check_inactivity(self, ctx):
        INACTIVITY_TIMEOUT = 180

        if not ctx.voice_client or not ctx.voice_client.is_connected():
            self.check_inactivity.stop()
            return

        if ctx.voice_client.is_playing() or ctx.voice_client.is_paused():
            self.last_activity_timestamp = time()
            return

        if time() - self.last_activity_timestamp > INACTIVITY_TIMEOUT:
            await ctx.voice_client.disconnect()
            self.check_inactivity.stop()
            await ctx.send("🛑 Desconectado por inactividad.")

    @commands.command(name="search", help="Searches for a song on YouTube.")
    async def search(self, ctx, *, query: str):
        search_options = YTDL_OPTIONS.copy()
        search_options.pop("playlist_items", None)  # Remove playlist_items option
        search_options["extract_flat"] = True  # Extract simple data for optimization

        async with ctx.typing():
            with yt_dlp.YoutubeDL(search_options) as ydl:
                try:
                    info = ydl.extract_info(
                        f"ytsearch5:{query}", download=False
                    )  # We use ytsearch5 to get the first 5 results
                    entries = info.get("entries", [])

                except Exception as e:
                    await ctx.send("Ocurrió un error al buscar la canción.")
                    print(f"Error: {e}")

        if not entries:
            await ctx.send("No se encontraron resultados.")
            return

        view = SearchView(entries, self, ctx)
        await ctx.send(view=view)


# NOTE FOR THE FUTURE:
# Ephemeral messages are messages that can only be seen by the user sending them and the bot.
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
        """
        On this function we need to get the selected song and search more info about it to play it. This is because we optimize the search of the first 5 results to get simpler data.
        We need to get the video ID and the title of the song to play it. The video ID is used to get the URL of the song and the title is used to show it in the queue.
        """
        index = int(self.values[0])
        selected_entry = self.entries[index]
        title = selected_entry["title"]

        video_id = selected_entry["id"]
        if not video_id:
            await interaction.response.send_message(
                "No se encontró el ID del video.", ephemeral=True
            )
            return

        try:
            url = f"https://www.youtube.com/watch?v={video_id}"
            with yt_dlp.YoutubeDL(YTDL_OPTIONS) as ydl:
                info = ydl.extract_info(url, download=False)
                url = info["url"]
        except Exception as e:
            await interaction.response.send_message(
                "Error al obtener la URL del video.", ephemeral=True
            )
            print(f"Error: {e}")
            return

        full_url = info.get("url", None)
        if not full_url:
            await interaction.response.send_message(
                "No se encontró la URL del video.", ephemeral=True
            )
            return

        self.music_cog.queue.append({"title": title, "url": full_url})
        await interaction.response.send_message(f"Se agregó a la cola: **{title}**")

        # If the bot is not connected to a voice channel, try to join the user's channel
        if not self.ctx.voice_client or not self.ctx.voice_client.is_connected():
            # Check if the user is in a voice channel
            if self.ctx.author.voice and self.ctx.author.voice.channel:
                await self.music_cog.join_voice_channel(self.ctx)
            else:
                # If the user is not in a voice channel, send an ephemeral message
                await interaction.followup.send(
                    "Debes estar en un canal de voz para reproducir la canción.",
                    ephemeral=True,
                )
                return

        # Check if the bot is already playing a song
        if not self.ctx.voice_client.is_playing():
            await self.music_cog.play_next_in_queue(
                self.ctx
            )  # Play the next song in the queue

        await interaction.message.delete()  # Delete the search message
        self.stop()  # Stop the select menu


class SearchView(discord.ui.View):
    def __init__(self, entries, music_cog, ctx, timeout=30):
        super().__init__(timeout=timeout)
        self.author = ctx.author
        self.add_item(SearchSelect(entries, music_cog, ctx))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Check if the interaction is from the original author of the message
        if interaction.user != self.author:
            await interaction.response.send_message(
                "No puedes interactuar con este menú.", ephemeral=True
            )
            return False
        return True


async def setup(bot):
    await bot.add_cog(Music(bot))
