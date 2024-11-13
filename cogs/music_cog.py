import discord
import yt_dlp
import random
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
        self.is_playing = None
        self.inactivity_channel = None  # Channel for inactivity messages
        self.check_inactivity.start()  # Start checking for inactivity

    def cog_unload(self):
        # Stop the inactivity check when the cog is unloaded
        self.check_inactivity.cancel()

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
            self.is_playing = True
            await ctx.send(f"Reproduciendo: **{song['title']}**")
        else:
            self.is_playing = False

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

    @commands.command(name="resume", help="Resumes the paused song.")
    async def resume(self, ctx):
        if ctx.voice_client and ctx.voice_client.is_paused():
            ctx.voice_client.resume()
            await ctx.send("Se ha reanudado la reproducción.")

    @commands.command(
        name="queue", aliases=["q"], help="Displays the current song queue."
    )
    async def queue(self, ctx):
        if len(self.queue) > 0:
            queue_list = "\n".join(
                [f"**{i+1}. {song['title']}**" for i, song in enumerate(self.queue)]
            )

            await ctx.send(
                f"Reproduciendo: **{self.actual_song}**\nCanciones en cola: **({len(self.queue)})**:\n{queue_list}"
            )
        else:
            await ctx.send("La cola está vacía.")

    @commands.command(
        name="rq", help="Removes a song from the queue by its position in the list."
    )
    async def remove_from_queue(self, ctx, position: int):
        if len(self.queue) > 0:
            if 0 < position <= len(self.queue):
                removed = self.queue.pop(position - 1)
                await ctx.send(f"Se ha eliminado de la cola: **{removed['title']}**")
            else:
                await ctx.send("Posición inválida.")
        else:
            await ctx.send("La cola está vacía.")

    @commands.command(name="clear", aliases=["qc"], help="Clears the song queue.")
    async def clear(self, ctx):
        self.queue.clear()
        await ctx.send("La cola se vació.")

    @commands.command(name="shuffle", help="Shuffles the song queue.")
    async def shuffle(self, ctx):
        if len(self.queue) > 0:
            random.shuffle(self.queue)
            await ctx.send("Aleatorizado la cola.")
        else:
            await ctx.send("La cola está vacía.")

    @commands.command(name="coin", aliases=["random"], help="Flips a coin.")
    async def coin(self, ctx):
        result = random.choice(["Cara", "Sello"])
        await ctx.send(f"Resultado: **{result}**")

    @tasks.loop(minutes=1)
    async def check_inactivity(self):
        for vc in self.bot.voice_clients:
            if not vc.is_playing() and vc.is_connected():
                if self.inactivity_channel:
                    await self.inactivity_channel.send(
                        "Bot desconectado por inactividad."
                    )
                await vc.disconnect()
                self.is_playing = None
                print("Bot desconectado por inactividad.")


async def setup(bot):
    await bot.add_cog(Music(bot))
