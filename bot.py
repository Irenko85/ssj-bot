import discord
import os
import yt_dlp
import asyncio
from discord.ext import commands, tasks
from dotenv import load_dotenv
from urllib.parse import urlparse, parse_qs, urlunparse, urlencode

load_dotenv()

intents = discord.Intents.all()
intents.message_content = True

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


class SSJBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        self.queue = []
        self.actual_song = None
        self.is_playing = None

    async def on_ready(self):
        print(f"Logged in as {self.user.name}")
        channel = self.get_channel(
            884592421575491594
        )  # ID del canal musica de ~LGTV, cambiar en caso de usar otro servidor
        self.check_inactivity.start(channel)

    async def play_next_in_queue(self, ctx):
        if len(self.queue) > 0:
            self.actual_song = self.queue[0]["title"]
            song = self.queue.pop(0)
            url = song["url"]
            source = await discord.FFmpegOpusAudio.from_probe(url, **FFMPEG_OPTIONS)
            ctx.voice_client.play(
                source,
                after=lambda _: self.loop.create_task(self.play_next_in_queue(ctx)),
            )
            self.is_playing = True
            await ctx.send(f"Reproduciendo: **{song['title']}**")
        else:
            self.is_playing = False

    async def skip(self, ctx):
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.stop()

    @tasks.loop(seconds=60)
    async def check_inactivity(self, channel):
        if not self.is_playing and self.is_playing is not None:
            print("Bot desconectado por inactividad")
            self.is_playing = None
            await channel.send("Bot desconectado por inactividad")
            await self.voice_clients[0].disconnect()


client = SSJBot()


@client.command(name="hola")
async def hello(ctx: commands.Context):
    await ctx.send(f"Hola! {ctx.author.mention}")


@client.command(name="play", aliases=["p"], description="Reproducir una canción")
async def play(ctx: commands.Context, *, search: str):
    voice_channel = ctx.author.voice.channel if ctx.author.voice else None

    if not voice_channel:
        await ctx.send(
            f"{ctx.author.mention} debes estar en un canal de voz para usar este comando!"
        )
        return

    if not ctx.voice_client:
        await voice_channel.connect()

    async with ctx.typing():
        is_url = "youtube.com/watch" in search or "youtu.be" in search
        with yt_dlp.YoutubeDL(YTDL_OPTIONS) as ydl:
            try:
                if is_url:
                    search = clean_yt_link(search)
                    info = ydl.extract_info(search, download=False)
                    url = info["url"]
                    title = info.get("title", "Título desconocido")
                else:
                    info = ydl.extract_info(f"ytsearch:{search}", download=False)
                    if "entries" in info and len(info["entries"]) > 0:
                        info = info["entries"][0]
                    url = info["url"]
                    title = info["title"]

                client.queue.append({"title": title, "url": url})
                await ctx.send(f"Se agregó a la cola: **{title}**")
            except Exception as e:
                await ctx.send("Hubo un error al procesar el enlace o la búsqueda.")
                print(f"Error: {e}")

    if not ctx.voice_client.is_playing():
        await client.play_next_in_queue(ctx)


@client.command(name="stop")
async def stop(ctx: commands.Context):
    if ctx.voice_client:
        ctx.voice_client.stop()
        await ctx.voice_client.disconnect()
        await ctx.send("Reproducción detenida, CHAO CTM!")


@client.command(name="skip", aliases=["s"])
async def skip(ctx: commands.Context):
    await client.skip(ctx)


@client.command(name="pause")
async def pause(ctx: commands.Context):
    if ctx.voice_client:
        ctx.voice_client.pause()
        await ctx.send("Reproducción pausada")


@client.command(name="resume")
async def resume(ctx: commands.Context):
    if ctx.voice_client:
        ctx.voice_client.resume()
        await ctx.send("Reproducción reanudada")


@client.command(name="queue", aliases=["q"])
async def queue(ctx: commands.Context):
    if len(client.queue) > 0:
        queue = "\n".join([f"- **{song['title']}**" for song in client.queue])
        await ctx.send(f"Actualmente reproduciendo: **{client.actual_song}**")
        await ctx.send(f"Canciones en cola **({len(client.queue)})**:\n{queue}")
    else:
        await ctx.send("No hay canciones en cola")


@client.command(
    name="qc", aliases=["clear"], description="Limpia la cola de reproducción"
)
async def clear(ctx: commands.Context):
    client.queue.clear()
    await ctx.send("Se ha vaciado la cola de reproducción")


@client.command(name="shuffle", description="Mezcla las canciones en cola")
async def shuffle(ctx):
    if len(client.queue) > 0:
        import random

        random.shuffle(client.queue)
        await ctx.send("Se ha mezclado la cola de reproducción")
    else:
        await ctx.send("No hay canciones en cola")


@client.command(name="random", aliases=["coin"])
async def random(ctx):
    import random

    result = random.choice(["Cara", "Sello"])
    await ctx.send(f"Resultado: **{result}**")


def clean_yt_link(link):
    parsed_link = urlparse(link)
    query_params = {
        k: v
        for k, v in parse_qs(parsed_link.query).items()
        if k not in {"list", "start_radio", "index", "t"}
    }
    new_query = urlencode(query_params, doseq=True)
    new_link = urlunparse(parsed_link._replace(query=new_query))

    return new_link


if __name__ == "__main__":
    asyncio.run(client.start(os.getenv("DISCORD_TOKEN")))
