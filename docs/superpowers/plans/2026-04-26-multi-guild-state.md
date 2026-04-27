# Multi-guild state refactor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the bot fully multi-guild by encapsulating all per-server mutable state in a `GuildState` class indexed by `guild.id`, and drop the `GUILD_ID` configuration.

**Architecture:** Introduce `class GuildState` that owns `queue`, `actual_song`, `last_activity`, `inactivity_warned`, `inactivity_channel`. The `Music` cog keeps `self.states: dict[int, GuildState]` and exposes `_state(ctx)` (idempotent setdefault) and `_cleanup_state(guild_id)`. The inactivity loop iterates over all guild states independently. The voice client is not stored — discord.py already manages one per guild.

**Tech Stack:** Python 3.13 (local) / 3.12 (Docker), discord.py 2.7.1 with `[voice]` extra, davey 0.1.5, yt-dlp 2026.1.31, ffmpeg.

**Spec reference:** `docs/superpowers/specs/2026-04-26-multi-guild-state-design.md`

**Validation strategy note:** the repository has no automated test suite. Each task ends with a static check (`python -m py_compile`) and, when relevant, a manual smoke step described explicitly. The full multi-guild manual validation lives in Task 11.

---

## Task 1: Add `GuildState` class and `_state` / `_cleanup_state` helpers

**Files:**
- Modify: `cogs/music_cog.py`

- [ ] **Step 1: Add the `GuildState` class above `class Music`**

Insert the following block immediately before `class Music(commands.Cog):` at the top of the cog (around line 102 of the current file, after `ANIME_PLAYLIST_URL`):

```python
class GuildState:
    """Per-guild music state. One instance per Discord server."""

    __slots__ = (
        "queue",
        "actual_song",
        "last_activity",
        "inactivity_warned",
        "inactivity_channel",
    )

    def __init__(self) -> None:
        self.queue: list[dict] = []
        self.actual_song: str | None = None
        self.last_activity: float = time()
        self.inactivity_warned: bool = False
        self.inactivity_channel: discord.TextChannel | None = None
```

- [ ] **Step 2: Replace `Music.__init__` with the new state container**

Replace this current block:

```python
class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.queue = []
        self.actual_song = None
        self.inactivity_channel = None
        self.last_activity_timestamp = None
        self.inactivity_warned = False  # Flag to prevent spam warnings
```

with:

```python
class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.states: dict[int, GuildState] = {}

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
```

- [ ] **Step 3: Replace `update_activity` to take a context**

Replace the current method:

```python
    def update_activity(self):
        """Update activity timestamp"""
        self.last_activity_timestamp = time()
        self.inactivity_warned = False
```

with:

```python
    def update_activity(self, ctx) -> None:
        """Refresh the activity timestamp for the guild from `ctx`."""
        s = self._state(ctx)
        s.last_activity = time()
        s.inactivity_warned = False
```

- [ ] **Step 4: Verify the file still parses**

Run: `venv\Scripts\python.exe -m py_compile cogs\music_cog.py`
Expected: no output (success). Any `SyntaxError` must be fixed before continuing.

- [ ] **Step 5: Commit**

```powershell
git add cogs/music_cog.py
git commit -m "add GuildState and per-guild helpers"
```

---

## Task 2: Migrate `play_next_in_queue` and `_after_play` to per-guild state

**Files:**
- Modify: `cogs/music_cog.py`

- [ ] **Step 1: Replace `play_next_in_queue` to use `_state(ctx)`**

Replace the entire current method (lines around 170-219):

```python
    async def play_next_in_queue(self, ctx):
        logger.debug(
            f"play_next_in_queue llamado, canciones en cola: {len(self.queue)}"
        )

        if len(self.queue) > 0:
            # Verify that voice_client is available and connected
            if not ctx.voice_client or not ctx.voice_client.is_connected():
                logger.error("voice_client no está conectado en play_next_in_queue")
                await ctx.send("Error: El bot no está conectado a un canal de voz.")
                return

            self.actual_song = self.queue[0]["title"]
            song = self.queue.pop(0)
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
                await ctx.send(f"Reproduciendo: **{song['title']}**")
                self.update_activity()  # Update activity when playing
            except Exception as e:
                logger.error(
                    f"Exception en play_next_in_queue: {type(e).__name__}: {e}"
                )
                logger.error(traceback.format_exc())
                await ctx.send(
                    f"Error al reproducir **{song['title']}**. Intentando con la siguiente canción..."
                )
                # Try to play the next song
                await self.play_next_in_queue(ctx)
```

with:

```python
    async def play_next_in_queue(self, ctx):
        s = self._state(ctx)
        logger.debug(
            f"play_next_in_queue llamado en guild={ctx.guild.id}, canciones en cola: {len(s.queue)}"
        )

        if len(s.queue) > 0:
            # Verify that voice_client is available and connected
            if not ctx.voice_client or not ctx.voice_client.is_connected():
                logger.error("voice_client no está conectado en play_next_in_queue")
                await ctx.send("Error: El bot no está conectado a un canal de voz.")
                return

            s.actual_song = s.queue[0]["title"]
            song = s.queue.pop(0)
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
                await ctx.send(f"Reproduciendo: **{song['title']}**")
                self.update_activity(ctx)  # Update activity when playing
            except Exception as e:
                logger.error(
                    f"Exception en play_next_in_queue: {type(e).__name__}: {e}"
                )
                logger.error(traceback.format_exc())
                await ctx.send(
                    f"Error al reproducir **{song['title']}**. Intentando con la siguiente canción..."
                )
                # Try to play the next song
                await self.play_next_in_queue(ctx)
```

- [ ] **Step 2: `_after_play` does not need changes — confirm**

Open `cogs/music_cog.py` around the `_after_play` method (just below `play_next_in_queue`). It should already look like this (no edits required):

```python
    async def _after_play(self, ctx, error, song_title):
        """Callback que se ejecuta después de que termina una canción"""
        if error:
            logger.error(f"Error durante la reproducción de '{song_title}': {error}")
        else:
            logger.debug(f"Canción '{song_title}' terminó correctamente")
        await self.play_next_in_queue(ctx)
```

If it differs, restore it to this version. No code change is committed in this step — it's a sanity check only.

- [ ] **Step 3: Verify the file still parses**

Run: `venv\Scripts\python.exe -m py_compile cogs\music_cog.py`
Expected: no output.

- [ ] **Step 4: Commit**

```powershell
git add cogs/music_cog.py
git commit -m "migrate play_next_in_queue to GuildState"
```

---

## Task 3: Migrate `join_voice_channel` and `play_playlist`

**Files:**
- Modify: `cogs/music_cog.py`

- [ ] **Step 1: Update `update_activity()` calls inside `join_voice_channel`**

Find the three `self.update_activity()` calls inside `join_voice_channel` (around lines 263, 268). They appear in three places — when connecting, when moving, and (implicitly elsewhere). Change each to `self.update_activity(ctx)`.

Replace the call at "Add a small delay to ensure the connection is ready":

```python
                    self.update_activity()  # Update activity when connecting
```

with:

```python
                    self.update_activity(ctx)  # Update activity when connecting
```

And the one in the `elif` branch:

```python
                    self.update_activity()  # Update activity when moving
```

with:

```python
                    self.update_activity(ctx)  # Update activity when moving
```

- [ ] **Step 2: Verify the file still parses**

Run: `venv\Scripts\python.exe -m py_compile cogs\music_cog.py`
Expected: no output.

- [ ] **Step 3: `play_playlist` does not touch the queue directly — confirm and skip**

Open the `play_playlist` method. It calls `self.play(...)` and `self.start_inactivity_check(ctx)`, both of which we will update separately. No direct edits required here.

- [ ] **Step 4: Commit**

```powershell
git add cogs/music_cog.py
git commit -m "pass ctx to update_activity in join_voice_channel"
```

---

## Task 4: Migrate `start_inactivity_check` and the `check_inactivity` loop

**Files:**
- Modify: `cogs/music_cog.py`

This is the most involved change. The current loop receives a single `ctx` and uses global attributes. The new loop iterates over all `self.states` and resolves the voice client per guild.

- [ ] **Step 1: Replace `start_inactivity_check`**

Replace the current method:

```python
    def start_inactivity_check(self, ctx):
        """Inicia o reinicia el check de inactividad"""
        logger.debug("start_inactivity_check llamado")
        self.inactivity_channel = ctx.channel
        self.update_activity()

        if not self.check_inactivity.is_running():
            logger.debug("Iniciando check_inactivity loop")
            self.check_inactivity.start(ctx)
        else:
            logger.debug("check_inactivity ya está corriendo")
```

with:

```python
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
```

Note: the loop is now started **without arguments**. The new implementation iterates over `self.states` itself.

- [ ] **Step 2: Replace the `check_inactivity` loop**

Replace the entire `@tasks.loop(...)` definition (lines around 580-651):

```python
    @tasks.loop(seconds=15)  # Increased to 15 seconds to reduce load
    async def check_inactivity(self, ctx):
        INACTIVITY_TIMEOUT = 300  # 5 minutes instead of 3
        WARNING_TIME = 240  # Warn at 4 minutes

        try:
            logger.debug("check_inactivity ejecutándose...")
            # Check if bot is connected
            if not ctx.voice_client or not ctx.voice_client.is_connected():
                logger.debug(
                    "check_inactivity: voice_client no conectado, deteniendo loop"
                )
                self.check_inactivity.stop()
                return

            # If no activity timestamp, initialize it
            if self.last_activity_timestamp is None:
                self.update_activity()
                return

            current_time = time()
            time_since_activity = current_time - self.last_activity_timestamp

            # If playing, paused, or has songs in queue, consider as active
            if (
                ctx.voice_client.is_playing()
                or ctx.voice_client.is_paused()
                or len(self.queue) > 0
            ):
                self.update_activity()
                return

            # Check if there are users in the voice channel (excluding bot)
            if ctx.voice_client.channel:
                members_in_channel = [
                    member
                    for member in ctx.voice_client.channel.members
                    if not member.bot
                ]
                if not members_in_channel:
                    # If no users, disconnect immediately
                    await ctx.voice_client.disconnect()
                    self.check_inactivity.stop()
                    if self.inactivity_channel:
                        await self.inactivity_channel.send(
                            "🛑 Desconectado porque no hay usuarios en el canal."
                        )
                    return

            # Warning before disconnecting
            if time_since_activity > WARNING_TIME and not self.inactivity_warned:
                self.inactivity_warned = True
                if self.inactivity_channel:
                    remaining_time = int(INACTIVITY_TIMEOUT - time_since_activity)
                    await self.inactivity_channel.send(
                        f"⚠️ El bot se desconectará en {remaining_time} segundos por inactividad. "
                        f"Usa cualquier comando de música para mantener la conexión."
                    )

            # Disconnect due to inactivity
            if time_since_activity > INACTIVITY_TIMEOUT:
                await ctx.voice_client.disconnect()
                self.check_inactivity.stop()
                if self.inactivity_channel:
                    await self.inactivity_channel.send(
                        "🛑 Desconectado por inactividad."
                    )

        except Exception as e:
            logger.error(f"Error en check_inactivity: {e}")
            # In case of error, stop the loop to prevent error spam
            self.check_inactivity.stop()
```

with:

```python
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
                        if s.inactivity_channel:
                            await s.inactivity_channel.send(
                                "🛑 Desconectado porque no hay usuarios en el canal."
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
                            f"⚠️ El bot se desconectará en {remaining_time} segundos por inactividad. "
                            f"Usa cualquier comando de música para mantener la conexión."
                        )

                # Disconnect for inactivity
                if time_since_activity > INACTIVITY_TIMEOUT:
                    await voice_client.disconnect()
                    if s.inactivity_channel:
                        await s.inactivity_channel.send(
                            "🛑 Desconectado por inactividad."
                        )
                    self._cleanup_state(guild_id)

            except Exception as e:
                logger.error(
                    f"Error en check_inactivity para guild={guild_id}: {e}"
                )
                # Continue with the other guilds; do not stop the whole loop
                continue
```

- [ ] **Step 3: Verify the file still parses**

Run: `venv\Scripts\python.exe -m py_compile cogs\music_cog.py`
Expected: no output.

- [ ] **Step 4: Commit**

```powershell
git add cogs/music_cog.py
git commit -m "refactor inactivity loop per guild"
```

---

## Task 5: Migrate the `play` command body

**Files:**
- Modify: `cogs/music_cog.py`

The `play` command appends to `self.queue` once and reads `len(self.queue)` for logging. We replace those two specific lines and update the `update_activity()` calls implicitly invoked through helpers (those are already updated in earlier tasks).

- [ ] **Step 1: Update queue append inside `play`**

Find the block at the end of the `try:` clause (around line 456-459):

```python
                        logger.debug(f"Agregando a la cola: {title}")
                        self.queue.append(
                            {"title": title, "url": url, "headers": headers}
                        )
```

Replace with:

```python
                        logger.debug(f"Agregando a la cola: {title}")
                        self._state(ctx).queue.append(
                            {"title": title, "url": url, "headers": headers}
                        )
```

- [ ] **Step 2: Update `Queue length:` debug log**

Find the line (around line 483):

```python
        logger.debug(f"Queue length: {len(self.queue)}")
```

Replace with:

```python
        logger.debug(f"Queue length: {len(self._state(ctx).queue)}")
```

- [ ] **Step 3: Verify the file still parses**

Run: `venv\Scripts\python.exe -m py_compile cogs\music_cog.py`
Expected: no output.

- [ ] **Step 4: Commit**

```powershell
git add cogs/music_cog.py
git commit -m "migrate play command to GuildState"
```

---

## Task 6: Migrate `stop`, `skip`, `pause`, `resume`, and add cleanup on stop

**Files:**
- Modify: `cogs/music_cog.py`

- [ ] **Step 1: Replace `stop` to clear per-guild queue and cleanup state**

Replace:

```python
    @commands.command(name="stop", help="Stops playback and leaves the voice channel.")
    async def stop(self, ctx):
        if ctx.voice_client:
            self.queue.clear()
            ctx.voice_client.stop()
            await ctx.voice_client.disconnect()
            await ctx.send("Reproducción detenida. CHAO CTM!")

            # Stop inactivity check
            if self.check_inactivity.is_running():
                self.check_inactivity.stop()
```

with:

```python
    @commands.command(name="stop", help="Stops playback and leaves the voice channel.")
    async def stop(self, ctx):
        if ctx.voice_client:
            s = self._state(ctx)
            s.queue.clear()
            ctx.voice_client.stop()
            await ctx.voice_client.disconnect()
            await ctx.send("Reproducción detenida. CHAO CTM!")
            self._cleanup_state(ctx.guild.id)
            # The check_inactivity loop stops itself once self.states is empty
```

- [ ] **Step 2: Replace `skip`**

Replace:

```python
    @commands.command(name="skip", aliases=["s"], help="Skips the current song.")
    async def skip(self, ctx):
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.stop()
            await ctx.send("Se skipeó la canción actual.")
            self.update_activity()  # Update activity when skipping
```

with:

```python
    @commands.command(name="skip", aliases=["s"], help="Skips the current song.")
    async def skip(self, ctx):
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.stop()
            await ctx.send("Se skipeó la canción actual.")
            self.update_activity(ctx)  # Update activity when skipping
```

- [ ] **Step 3: Replace `pause`**

Replace:

```python
    @commands.command(name="pause", help="Pauses the current song.")
    async def pause(self, ctx):
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.pause()
            await ctx.send("Se ha pausado la reproducción.")
            self.update_activity()  # Update activity when pausing
```

with:

```python
    @commands.command(name="pause", help="Pauses the current song.")
    async def pause(self, ctx):
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.pause()
            await ctx.send("Se ha pausado la reproducción.")
            self.update_activity(ctx)  # Update activity when pausing
```

- [ ] **Step 4: Replace `resume`**

Replace:

```python
    @commands.command(name="resume", aliases=["r"], help="Resumes the paused song.")
    async def resume(self, ctx):
        if ctx.voice_client and ctx.voice_client.is_paused():
            ctx.voice_client.resume()
            await ctx.send("Se ha reanudado la reproducción.")
            self.update_activity()  # Update activity when resuming
```

with:

```python
    @commands.command(name="resume", aliases=["r"], help="Resumes the paused song.")
    async def resume(self, ctx):
        if ctx.voice_client and ctx.voice_client.is_paused():
            ctx.voice_client.resume()
            await ctx.send("Se ha reanudado la reproducción.")
            self.update_activity(ctx)  # Update activity when resuming
```

- [ ] **Step 5: Verify the file still parses**

Run: `venv\Scripts\python.exe -m py_compile cogs\music_cog.py`
Expected: no output.

- [ ] **Step 6: Commit**

```powershell
git add cogs/music_cog.py
git commit -m "migrate stop skip pause resume to GuildState"
```

---

## Task 7: Migrate `queue`, `remove_from_queue`, `clear`, `shuffle`, `search`

**Files:**
- Modify: `cogs/music_cog.py`

- [ ] **Step 1: Replace `queue`**

Replace:

```python
    @commands.command(
        name="queue", aliases=["q"], help="Displays the current song queue."
    )
    async def queue(self, ctx):
        if self.queue:
            queue_list = "\n".join(
                f"{i + 1}. {song['title']}" for i, song in enumerate(self.queue)
            )
            await ctx.send(
                f"Reproduciendo: **{self.actual_song}**\nCanciones en cola ({len(self.queue)}):\n**{queue_list}**"
            )
        else:
            await ctx.send("La cola está vacía.")
        self.update_activity()  # Update activity when viewing queue
```

with:

```python
    @commands.command(
        name="queue", aliases=["q"], help="Displays the current song queue."
    )
    async def queue(self, ctx):
        s = self._state(ctx)
        if s.queue:
            queue_list = "\n".join(
                f"{i + 1}. {song['title']}" for i, song in enumerate(s.queue)
            )
            await ctx.send(
                f"Reproduciendo: **{s.actual_song}**\nCanciones en cola ({len(s.queue)}):\n**{queue_list}**"
            )
        else:
            await ctx.send("La cola está vacía.")
        self.update_activity(ctx)  # Update activity when viewing queue
```

- [ ] **Step 2: Replace `remove_from_queue`**

Replace:

```python
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
            self.update_activity()  # Update activity when removing song
        except IndexError:
            await ctx.send(
                "Posición inválida. Asegúrate de que el número esté dentro del rango de la cola."
            )
```

with:

```python
    @commands.command(
        name="rq", help="Removes a song from the queue by its position in the list."
    )
    async def remove_from_queue(self, ctx, position: int):
        s = self._state(ctx)
        if not s.queue:
            await ctx.send("La cola está vacía.")
            return

        try:
            removed = s.queue.pop(position - 1)
            await ctx.send(f"Se ha eliminado de la cola: **{removed['title']}**")
            self.update_activity(ctx)  # Update activity when removing song
        except IndexError:
            await ctx.send(
                "Posición inválida. Asegúrate de que el número esté dentro del rango de la cola."
            )
```

- [ ] **Step 3: Replace `clear`**

Replace:

```python
    @commands.command(name="clear", aliases=["qc"], help="Clears the song queue.")
    async def clear(self, ctx):
        self.queue.clear()
        await ctx.send("La cola se vació.")
        self.update_activity()  # Update activity when clearing queue
```

with:

```python
    @commands.command(name="clear", aliases=["qc"], help="Clears the song queue.")
    async def clear(self, ctx):
        self._state(ctx).queue.clear()
        await ctx.send("La cola se vació.")
        self.update_activity(ctx)  # Update activity when clearing queue
```

- [ ] **Step 4: Replace `shuffle`**

Replace:

```python
    @commands.command(name="shuffle", help="Shuffles the song queue.")
    async def shuffle(self, ctx):
        if len(self.queue) > 0:
            random.shuffle(self.queue)
            await ctx.invoke(self.bot.get_command("queue"))
            self.update_activity()  # Update activity when shuffling
        else:
            await ctx.send("La cola está vacía.")
```

with:

```python
    @commands.command(name="shuffle", help="Shuffles the song queue.")
    async def shuffle(self, ctx):
        s = self._state(ctx)
        if len(s.queue) > 0:
            random.shuffle(s.queue)
            await ctx.invoke(self.bot.get_command("queue"))
            self.update_activity(ctx)  # Update activity when shuffling
        else:
            await ctx.send("La cola está vacía.")
```

- [ ] **Step 5: Replace `search`**

Replace:

```python
    @commands.command(name="search", help="Searches for a song on YouTube.")
    async def search(self, ctx, *, query: str):
        search_options = YTDL_OPTIONS.copy()
        search_options.pop("playlist_items", None)
        search_options["extract_flat"] = True

        async with ctx.typing():
            with SafeYoutubeDL(search_options) as ydl:
                try:
                    info = ydl.extract_info(f"ytsearch5:{query}", download=False)
                    entries = info.get("entries", [])
                except Exception as e:
                    await ctx.send("Ocurrió un error al buscar la canción.")
                    logger.error(f"Error en search: {e}")

        if not entries:
            await ctx.send("No se encontraron resultados.")
            return

        view = SearchView(entries, self, ctx)
        await ctx.send(view=view)
        self.update_activity()  # Update activity when searching
```

with (only the last line changes):

```python
    @commands.command(name="search", help="Searches for a song on YouTube.")
    async def search(self, ctx, *, query: str):
        search_options = YTDL_OPTIONS.copy()
        search_options.pop("playlist_items", None)
        search_options["extract_flat"] = True

        async with ctx.typing():
            with SafeYoutubeDL(search_options) as ydl:
                try:
                    info = ydl.extract_info(f"ytsearch5:{query}", download=False)
                    entries = info.get("entries", [])
                except Exception as e:
                    await ctx.send("Ocurrió un error al buscar la canción.")
                    logger.error(f"Error en search: {e}")

        if not entries:
            await ctx.send("No se encontraron resultados.")
            return

        view = SearchView(entries, self, ctx)
        await ctx.send(view=view)
        self.update_activity(ctx)  # Update activity when searching
```

- [ ] **Step 6: Verify the file still parses**

Run: `venv\Scripts\python.exe -m py_compile cogs\music_cog.py`
Expected: no output.

- [ ] **Step 7: Commit**

```powershell
git add cogs/music_cog.py
git commit -m "migrate queue rq clear shuffle search to GuildState"
```

---

## Task 8: Migrate `SearchSelect.callback`

**Files:**
- Modify: `cogs/music_cog.py`

The `SearchSelect.callback` (around lines 694-748) appends directly to `self.music_cog.queue`. We swap that for the per-guild state.

- [ ] **Step 1: Replace the queue append and the `update_activity` call**

Find these two lines inside `SearchSelect.callback`:

```python
        self.music_cog.queue.append(
            {"title": title, "url": full_url, "headers": headers}
        )
        await interaction.response.send_message(f"Se agregó a la cola: **{title}**")

        # Update activity when adding song
        self.music_cog.update_activity()
```

Replace with:

```python
        self.music_cog._state(self.ctx).queue.append(
            {"title": title, "url": full_url, "headers": headers}
        )
        await interaction.response.send_message(f"Se agregó a la cola: **{title}**")

        # Update activity when adding song
        self.music_cog.update_activity(self.ctx)
```

- [ ] **Step 2: Verify the file still parses**

Run: `venv\Scripts\python.exe -m py_compile cogs\music_cog.py`
Expected: no output.

- [ ] **Step 3: Commit**

```powershell
git add cogs/music_cog.py
git commit -m "migrate SearchSelect to GuildState"
```

---

## Task 9: Add `@commands.guild_only()` to all music commands

**Files:**
- Modify: `cogs/music_cog.py`

The simplest, highest-coverage way is to add the cog-level check by overriding `cog_check`. This rejects all commands invoked in DM with discord.py's standard `NoPrivateMessage` error.

- [ ] **Step 1: Add `cog_check` to `Music`**

Insert this method right after the `_cleanup_state` helper (still inside `class Music`):

```python
    async def cog_check(self, ctx) -> bool:
        """Reject DM invocations for every command in this cog."""
        if ctx.guild is None:
            await ctx.send("Este comando solo funciona en un servidor.")
            return False
        return True
```

- [ ] **Step 2: Verify the file still parses**

Run: `venv\Scripts\python.exe -m py_compile cogs\music_cog.py`
Expected: no output.

- [ ] **Step 3: Commit**

```powershell
git add cogs/music_cog.py
git commit -m "reject DM commands in music cog"
```

---

## Task 10: Drop `GUILD_ID` from `bot.py`, `.env` and README

**Files:**
- Modify: `bot.py`
- Modify: `.env`
- Modify: `README.md`

- [ ] **Step 1: Replace `bot.py` startup logic**

Replace lines 11-13:

```python
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")
GUILD_ID = int(GUILD_ID) if GUILD_ID else None
```

with:

```python
TOKEN = os.getenv("DISCORD_TOKEN")
```

- [ ] **Step 2: Replace `on_ready`**

Replace:

```python
@bot.event
async def on_ready():
    """Event triggered when the bot has connected to Discord."""
    logger.info(f"{bot.user.name} conectado.")
    if GUILD_ID:
        guild = discord.utils.get(bot.guilds, id=GUILD_ID)
        if guild:
            logger.info(f"Conectado al servidor {guild.name}.")
        else:
            logger.warning("No se encontró el servidor con el GUILD_ID configurado.")
```

with:

```python
@bot.event
async def on_ready():
    """Event triggered when the bot has connected to Discord."""
    logger.info(f"{bot.user.name} conectado.")
    if bot.guilds:
        names = ", ".join(g.name for g in bot.guilds)
        logger.info(f"Conectado a {len(bot.guilds)} servidor(es): {names}")
    else:
        logger.info("El bot no está en ningún servidor todavía.")
```

- [ ] **Step 3: Remove the `GUILD_ID` line from `.env`**

Open `.env` and delete the line:

```dotenv
GUILD_ID=552949682767134722
```

Save the file. Do not commit `.env` (it is gitignored), but ensure the runtime no longer sees that variable.

- [ ] **Step 4: Update README**

In `README.md` find the dotenv example block (around line 28-34):

```markdown
   ```dotenv
   DISCORD_TOKEN=tu_token
   GUILD_ID=id_de_tu_servidor
   LOG_LEVEL=INFO
   # Opcional: cookies de YouTube
   # YTDL_COOKIES=/app/cookies/cookies.txt
   ```
```

Replace with:

```markdown
   ```dotenv
   DISCORD_TOKEN=tu_token
   LOG_LEVEL=INFO
   # Opcional: cookies de YouTube
   # YTDL_COOKIES=/app/cookies/cookies.txt
   ```
```

If there is any extra prose elsewhere in `README.md` mentioning `GUILD_ID`, search for it and remove that line too. Run: `Select-String -Path README.md -Pattern "GUILD_ID"` — expected: no matches after edits.

- [ ] **Step 5: Verify both files still parse**

Run: `venv\Scripts\python.exe -m py_compile bot.py cogs\music_cog.py`
Expected: no output.

- [ ] **Step 6: Commit**

```powershell
git add bot.py README.md
git commit -m "drop GUILD_ID env var"
```

(`.env` is intentionally not committed because it is gitignored.)

---

## Task 11: Manual smoke test (multi-guild)

**Files:**
- None (verification only)

This task is the validation gate. Do not skip steps. Capture the bot logs while testing.

- [ ] **Step 1: Close any previously running bot window**

Verify there is no `python.exe bot.py` instance running. In PowerShell:

```powershell
Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -like "*ssj-bot*" -or $_.Path -like "*\\ssj-bot\\*" }
```

If any are reported, close their console windows manually before continuing.

- [ ] **Step 2: Start the bot**

```powershell
$env:Path = "$env:LOCALAPPDATA\Microsoft\WinGet\Links;" + $env:Path
.\venv\Scripts\python.exe bot.py
```

Expected log lines: `SSJ Bot conectado.` and `Conectado a N servidor(es): <names>`.

- [ ] **Step 3: Single-server regression test**

In server **A**, run, in this order, and confirm each works:
- `!play <song name>` — bot joins voice and plays.
- `!queue` — shows the current song.
- `!play <another song>` — appended to queue.
- `!skip` — skips to the next.
- `!pause` and `!resume`.
- `!shuffle` and `!queue`.
- `!clear` — empties the queue.
- `!stop` — bot disconnects from the voice channel.

- [ ] **Step 4: Multi-server simultaneous test (the actual gate)**

With the bot in two servers (**A** and **B**):
1. Have one user run `!play <song1>` in server A. Confirm A's voice channel is playing.
2. Have a second user run `!play <song2>` in server B **while A is still playing**.
3. Confirm: bot joins **both** voice channels, **both** songs play independently, and `!queue` in each server shows only that server's song.
4. In server A run `!skip`. Confirm only A skips; B keeps playing the same song.
5. In server B run `!stop`. Confirm B disconnects, A keeps playing.

- [ ] **Step 5: DM rejection**

Send `!play whatever` in a DM to the bot.
Expected: the bot replies with "Este comando solo funciona en un servidor." (or the discord.py default `NoPrivateMessage` error).

- [ ] **Step 6: Inactivity check**

Leave the bot idle in server A while server B is being used. Wait ~5 min (do NOT type any music command in A).
Expected: A receives a warning at ~4 min, then disconnects at ~5 min. B keeps working.

- [ ] **Step 7: Document the result**

If any step fails, fix the bug and re-run all steps from the start. Do not proceed to merge until all steps pass.

- [ ] **Step 8: Commit (only if you had to fix anything)**

If steps 3-7 forced any code changes, commit them with a message like:

```powershell
git add cogs/music_cog.py bot.py
git commit -m "fix multi-guild edge case in <area>"
```

If nothing needed fixing, no commit is needed.

---

## Self-Review

**1. Spec coverage:**

| Spec section / requirement | Task |
|---|---|
| `GuildState` class with 5 fields | Task 1 |
| `_state(ctx)` helper using `setdefault` | Task 1 |
| `_cleanup_state(guild_id)` idempotent | Task 1 |
| `play_next_in_queue` per-guild | Task 2 |
| `play` per-guild | Task 5 |
| `stop`/`skip`/`pause`/`resume` per-guild | Task 6 |
| `queue`/`rq`/`clear`/`shuffle`/`search` per-guild | Task 7 |
| `SearchSelect.callback` per-guild | Task 8 |
| `update_activity(ctx)` signature change | Tasks 1, 3, 6, 7, 8 |
| Inactivity loop per-guild | Task 4 |
| `_cleanup_state` on disconnect (manual + inactivity) | Tasks 4, 6 |
| Snapshot iteration for safety | Task 4 |
| DM rejection | Task 9 |
| Drop `GUILD_ID` from bot.py and .env | Task 10 |
| Replace startup log with multi-guild log | Task 10 |
| Update README env vars table | Task 10 |
| Manual validation matrix | Task 11 |

All spec sections covered.

**2. Placeholder scan:** none of the steps contain "TBD", "TODO", "fill in", or vague verbs like "add appropriate error handling". Every code-changing step contains the literal old code and the literal new code.

**3. Type/name consistency:**
- `GuildState` attributes used: `queue`, `actual_song`, `last_activity`, `inactivity_warned`, `inactivity_channel` — same names everywhere they appear.
- Helper names `_state`, `_cleanup_state` — same in all references.
- `update_activity(ctx)` signature consistent across tasks.
- `check_inactivity` is now started without arguments in `start_inactivity_check` and the loop signature matches (`async def check_inactivity(self):`).

No issues found. Plan is final.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-26-multi-guild-state.md`. Two execution options:

1. **Subagent-driven (recommended)** — dispatch a fresh subagent per task, review between tasks.
2. **Inline execution** — execute tasks in this session using executing-plans, with checkpoints.
