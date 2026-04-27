# Slash Commands Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate all 13 prefix commands in `cogs/music_cog.py` to discord.py hybrid commands, disable the `!` prefix in favor of mentions, register slash commands per guild via `GUILD_IDS` env var, and make the `/search` dropdown ephemeral.

**Architecture:** Replace `@commands.command` decorators with `@commands.hybrid_command`. Keep all existing `Context`-based helpers unchanged. Add per-guild slash command sync in `on_ready`. Split `play()` into a public hybrid command and a private `_play_internal()` that retains the `silent` parameter used by `play_playlist`. Make `SearchView` ephemeral when invoked via slash interaction.

**Tech Stack:** Python 3.12, discord.py 2.7.1, pytest 8.3.4, pytest-asyncio 0.25.0.

---

## File Structure

**Files to modify:**
- `bot.py` — change `command_prefix`, add `GUILD_IDS` parsing, add per-guild sync in `on_ready`, add `on_app_command_error` handler.
- `cogs/music_cog.py` — replace decorators on all 13 commands, remove aliases, add `defer()` to slow commands, split `play` into public/internal, make `SearchView` ephemeral.
- `.env.example` — add `GUILD_IDS=` with comment.
- `README.md` — replace `!command` with `/command`, document `GUILD_IDS`, note alias removal.

**Files to create:**
- `tests/test_search_view_ephemeral.py` — verify search view ephemeral flag.
- `tests/test_play_internal_separation.py` — verify `_play_internal` silent behavior and `play` delegation.

**Files NOT touched:**
- `utils/utils.py` — async migration already complete.
- `tests/test_extract_info.py`, `tests/test_utils.py`, `tests/test_select_candidate.py` — existing tests remain green.
- `Dockerfile`, `docker-compose.yml` — no infrastructure changes.

---

## Task 1: Bot Infrastructure (Prefix Disable + Sync + Error Handler)

**Files:**
- Modify: `bot.py`
- Modify: `.env.example` (create if missing)

- [ ] **Step 1.1: Verify current state**

Run: `git status`
Expected: clean working tree on `feature/migrate-to-slash-commands`.

- [ ] **Step 1.2: Modify `bot.py` imports**

Replace the imports block at the top of `bot.py` with:

```python
import os
import sys
import asyncio
import logging
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
```

(adds `from discord import app_commands`).

- [ ] **Step 1.3: Add GUILD_IDS parsing**

After `TOKEN = os.getenv("DISCORD_TOKEN")` (line 11), add:

```python


def _parse_guild_ids(raw: str | None) -> list[int]:
    """Parse comma-separated guild IDs from env var. Skips invalid tokens."""
    if not raw:
        return []
    out: list[int] = []
    for piece in raw.split(","):
        piece = piece.strip()
        if not piece:
            continue
        try:
            out.append(int(piece))
        except ValueError:
            logging.getLogger("ssj-bot").warning(
                "Ignorando GUILD_IDS inválido: %r", piece
            )
    return out


GUILD_IDS = _parse_guild_ids(os.getenv("GUILD_IDS"))
```

- [ ] **Step 1.4: Change command_prefix**

Replace line 25 (currently `bot = commands.Bot(command_prefix="!", intents=intents)`) with:

```python
bot = commands.Bot(command_prefix=commands.when_mentioned, intents=intents)
```

- [ ] **Step 1.5: Add per-guild sync in on_ready**

Replace the `on_ready` function (lines 28-31) with:

```python
@bot.event
async def on_ready():
    """Event triggered when the bot has connected to Discord."""
    logger.info(f"{bot.user.name} conectado en {len(bot.guilds)} servidor(es).")
    await _sync_app_commands()


async def _sync_app_commands():
    """Sync slash commands. Per-guild if GUILD_IDS set, else global."""
    if GUILD_IDS:
        success = 0
        for gid in GUILD_IDS:
            try:
                await bot.tree.sync(guild=discord.Object(id=gid))
                success += 1
            except Exception as e:
                logger.warning("Sync falló para guild %s: %s", gid, e)
        logger.info(
            "Slash commands sincronizados en %d/%d guild(s).",
            success,
            len(GUILD_IDS),
        )
    else:
        try:
            await bot.tree.sync()
            logger.info(
                "Slash commands sincronizados globalmente (puede tardar hasta 1h)."
            )
        except Exception as e:
            logger.error("Sync global falló: %s", e)
```

- [ ] **Step 1.6: Add app command error handler**

After the `on_ready` block, add:

```python
@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError,
):
    """Catch unhandled errors from slash commands."""
    logger.error(
        "Error en slash command %s: %s",
        interaction.command.name if interaction.command else "?",
        error,
        exc_info=True,
    )
    msg = "Ocurrió un error inesperado."
    try:
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)
    except Exception as e:
        logger.error("No pude enviar mensaje de error al usuario: %s", e)
```

- [ ] **Step 1.7: Update `.env.example`**

If `.env.example` exists, append. Otherwise, create it with:

```bash
DISCORD_TOKEN=your_bot_token_here
LOG_LEVEL=INFO

# Comma-separated guild IDs where slash commands are registered.
# Leave empty for global sync (takes up to 1 hour to propagate).
# Get a guild ID: enable Discord Developer Mode -> right-click server -> Copy ID.
GUILD_IDS=
```

- [ ] **Step 1.8: Smoke test bot.py imports**

Run: `python -c "import bot"` from the repo root with the venv active.
Expected: no output (success). Any `ImportError` or `SyntaxError` is a failure.

- [ ] **Step 1.9: Run existing tests to verify nothing regressed**

Run: `python -m pytest -q`
Expected: 6 passed.

- [ ] **Step 1.10: Commit**

```bash
git add bot.py .env.example
git commit -m "wire slash command sync and disable prefix"
```

---

## Task 2: Play Refactor (Split Public/Internal)

**Files:**
- Modify: `cogs/music_cog.py:410-561` (the `play` method).
- Create: `tests/test_play_internal_separation.py`.

- [ ] **Step 2.1: Write failing test for `_play_internal` silent=True behavior**

Create `tests/test_play_internal_separation.py`:

```python
"""Tests for the public/internal split of the play command."""
import inspect
from unittest.mock import AsyncMock, MagicMock

import pytest

from cogs.music_cog import Music


def test_play_command_does_not_expose_silent():
    """The public hybrid `play` command must not expose a `silent` parameter."""
    sig = inspect.signature(Music.play.callback)
    assert "silent" not in sig.parameters, (
        "silent must not be a slash command parameter"
    )


def test_play_internal_exists_and_accepts_silent():
    """`_play_internal` must exist with a `silent` keyword argument."""
    assert hasattr(Music, "_play_internal"), "missing _play_internal helper"
    sig = inspect.signature(Music._play_internal)
    assert "silent" in sig.parameters, "_play_internal must accept silent"
    assert sig.parameters["silent"].default is False
```

- [ ] **Step 2.2: Run the test and verify it fails**

Run: `python -m pytest tests/test_play_internal_separation.py -v`
Expected: FAIL with `AttributeError: type object 'Music' has no attribute '_play_internal'` OR with `AttributeError` on `Music.play.callback`. The test fails because the split has not been implemented yet.

- [ ] **Step 2.3: Implement the split**

Open `cogs/music_cog.py`. Find the existing `play` method starting at line 410. The current signature is:

```python
@commands.command(name="play", aliases=["p"], description="Play a song or playlist")
async def play(self, ctx, *, search: str, silent: bool = False):
```

Replace the entire method with two methods. The public command:

```python
    @commands.hybrid_command(name="play", description="Play a song or playlist")
    async def play(self, ctx: commands.Context, search: str):
        await ctx.defer()
        await self._play_internal(ctx, search, silent=False)

    async def _play_internal(self, ctx, search: str, silent: bool = False):
```

Then keep the entire existing body (the `try:` block currently starting at line 412) inside `_play_internal`, with one modification: remove the `await ctx.defer()` if present in the body (it's already in the public command). The `if not silent:` block at line 528 stays exactly as is.

After the change, the `play_playlist` method (line 375) currently calls `self.play(ctx, search=url, silent=True)`. Update it to call `self._play_internal(ctx, url, silent=True)` — note: positional arg, not keyword.

Specifically, line 375:

```python
                await self.play(ctx, search=url, silent=True)
```

becomes:

```python
                await self._play_internal(ctx, url, silent=True)
```

- [ ] **Step 2.4: Run the new test and verify it passes**

Run: `python -m pytest tests/test_play_internal_separation.py -v`
Expected: 2 passed.

- [ ] **Step 2.5: Run all tests**

Run: `python -m pytest -q`
Expected: 8 passed (6 existing + 2 new).

- [ ] **Step 2.6: Commit**

```bash
git add cogs/music_cog.py tests/test_play_internal_separation.py
git commit -m "split play into public and internal helper"
```

---

## Task 3: Migrate Remaining Commands to Hybrid

**Files:**
- Modify: `cogs/music_cog.py` (decorators on `dbz`, `anime`, `stop`, `skip`, `pause`, `resume`, `queue`, `rq`, `clear`, `shuffle`, `coin`, `search`).

The `play` command was already migrated in Task 2. This task migrates the remaining 12.

- [ ] **Step 3.1: Replace each `@commands.command(...)` with `@commands.hybrid_command(...)` and remove aliases**

For each command listed below, edit the decorator. Help text stays. Drop the `aliases` kwarg entirely.

| Line (approx) | Old decorator | New decorator |
|---|---|---|
| 398 | `@commands.command(name="dbz", help="Reproduce la playlist de Dragon Ball Z")` | `@commands.hybrid_command(name="dbz", description="Reproduce la playlist de Dragon Ball Z")` |
| 404 | `@commands.command(name="anime", help="Reproduce la playlist de Anime")` | `@commands.hybrid_command(name="anime", description="Reproduce la playlist de Anime")` |
| 563 | `@commands.command(name="stop", help="Stops playback and leaves the voice channel.")` | `@commands.hybrid_command(name="stop", description="Stops playback and leaves the voice channel.")` |
| 574 | `@commands.command(name="skip", aliases=["s"], help="Skips the current song.")` | `@commands.hybrid_command(name="skip", description="Skips the current song.")` |
| 581 | `@commands.command(name="pause", help="Pauses the current song.")` | `@commands.hybrid_command(name="pause", description="Pauses the current song.")` |
| 588 | `@commands.command(name="resume", aliases=["r"], help="Resumes the paused song.")` | `@commands.hybrid_command(name="resume", description="Resumes the paused song.")` |
| 595 | `@commands.command(name="queue", aliases=["q"], help="Displays the current song queue.")` | `@commands.hybrid_command(name="queue", description="Displays the current song queue.")` |
| 611 | `@commands.command(name="rq", help="Removes a song from the queue by its position in the list.")` | `@commands.hybrid_command(name="rq", description="Removes a song from the queue by its position in the list.")` |
| 629 | `@commands.command(name="clear", aliases=["qc"], help="Clears the song queue.")` | `@commands.hybrid_command(name="clear", description="Clears the song queue.")` |
| 635 | `@commands.command(name="shuffle", help="Shuffles the song queue.")` | `@commands.hybrid_command(name="shuffle", description="Shuffles the song queue.")` |
| 645 | `@commands.command(name="coin", aliases=["random"], help="Flips a coin.")` | `@commands.hybrid_command(name="coin", description="Flips a coin.")` |
| 740 | `@commands.command(name="search", help="Searches for a song on YouTube.")` | `@commands.hybrid_command(name="search", description="Searches for a song on YouTube.")` |

Notes:
- `help=` becomes `description=`. Slash commands display the description; prefix help still works via `description`.
- All aliases are dropped.
- Method signatures gain `ctx: commands.Context` annotation. Any signature like `async def queue(self, ctx):` becomes `async def queue(self, ctx: commands.Context):`. For `rq(self, ctx, position: int)`, becomes `rq(self, ctx: commands.Context, position: int)`. For `search(self, ctx, *, query: str)`, becomes `search(self, ctx: commands.Context, query: str)` — drop the `*` separator.

- [ ] **Step 3.2: Add `defer()` to slow commands**

Three commands extract from yt-dlp and may exceed 3 seconds. Add `await ctx.defer()` as the first statement of each method body:

- `dbz` (after the `async def dbz` line, before `if not await self.join_voice_channel(ctx):`)
- `anime` (same pattern)
- `search` (after `async def search`, before `search_options = YTDL_OPTIONS.copy()`)

Example for `dbz`:

```python
    @commands.hybrid_command(name="dbz", description="Reproduce la playlist de Dragon Ball Z")
    async def dbz(self, ctx: commands.Context):
        await ctx.defer()
        if not await self.join_voice_channel(ctx):
            return
        await self.play_playlist(ctx, DBZ_PLAYLIST_URL, shuffle=True)
```

(`play` already has `defer()` from Task 2. Other commands respond fast enough.)

- [ ] **Step 3.3: Smoke test imports**

Run: `python -c "from cogs.music_cog import Music"`
Expected: no output. Any error means a syntax issue in the decorators or signatures.

- [ ] **Step 3.4: Run all tests**

Run: `python -m pytest -q`
Expected: 8 passed.

- [ ] **Step 3.5: Commit**

```bash
git add cogs/music_cog.py
git commit -m "migrate remaining commands to hybrid"
```

---

## Task 4: Search View Ephemeral

**Files:**
- Modify: `cogs/music_cog.py:759` (the `ctx.send(view=view)` line in `search`).
- Create: `tests/test_search_view_ephemeral.py`.

- [ ] **Step 4.1: Write failing test**

Create `tests/test_search_view_ephemeral.py`:

```python
"""Tests for SearchView being ephemeral when invoked via slash."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cogs.music_cog import Music


@pytest.mark.asyncio
async def test_search_sends_ephemeral_view_when_invoked_via_slash():
    """When ctx.interaction is set (slash invocation), the view is ephemeral."""
    cog = Music.__new__(Music)
    cog.update_activity = MagicMock()
    cog._extract_info = AsyncMock(
        return_value={"entries": [{"title": "T", "id": "x"}]}
    )

    ctx = MagicMock()
    ctx.interaction = MagicMock()  # slash invocation
    ctx.send = AsyncMock()
    ctx.typing = MagicMock()
    ctx.typing.return_value.__aenter__ = AsyncMock()
    ctx.typing.return_value.__aexit__ = AsyncMock()
    ctx.defer = AsyncMock()

    await cog.search.callback(cog, ctx, query="d4vd")

    assert ctx.send.await_count == 1
    _, kwargs = ctx.send.call_args
    assert kwargs.get("ephemeral") is True


@pytest.mark.asyncio
async def test_search_sends_public_view_when_invoked_via_mention():
    """When ctx.interaction is None (mention invocation), the view is public."""
    cog = Music.__new__(Music)
    cog.update_activity = MagicMock()
    cog._extract_info = AsyncMock(
        return_value={"entries": [{"title": "T", "id": "x"}]}
    )

    ctx = MagicMock()
    ctx.interaction = None  # mention invocation
    ctx.send = AsyncMock()
    ctx.typing = MagicMock()
    ctx.typing.return_value.__aenter__ = AsyncMock()
    ctx.typing.return_value.__aexit__ = AsyncMock()
    ctx.defer = AsyncMock()

    await cog.search.callback(cog, ctx, query="d4vd")

    assert ctx.send.await_count == 1
    _, kwargs = ctx.send.call_args
    assert kwargs.get("ephemeral") is False
```

- [ ] **Step 4.2: Run the test and verify it fails**

Run: `python -m pytest tests/test_search_view_ephemeral.py -v`
Expected: FAIL. The current `search` body calls `ctx.send(view=view)` without an `ephemeral` kwarg, so `kwargs.get("ephemeral")` returns `None`, which is neither `True` nor `False`. Both tests fail.

- [ ] **Step 4.3: Implement the change**

In `cogs/music_cog.py`, find the line in `search` that reads:

```python
        await ctx.send(view=view)
```

(around line 760). Replace it with:

```python
        await ctx.send(view=view, ephemeral=ctx.interaction is not None)
```

- [ ] **Step 4.4: Run the new test and verify it passes**

Run: `python -m pytest tests/test_search_view_ephemeral.py -v`
Expected: 2 passed.

- [ ] **Step 4.5: Run all tests**

Run: `python -m pytest -q`
Expected: 10 passed (8 + 2 new).

- [ ] **Step 4.6: Commit**

```bash
git add cogs/music_cog.py tests/test_search_view_ephemeral.py
git commit -m "make search view ephemeral on slash invocation"
```

---

## Task 5: Documentation + Smoke Test + Deploy

**Files:**
- Modify: `README.md`.

- [ ] **Step 5.1: Update README commands table**

Open `README.md`. Find the section listing bot commands (likely a table with `!play`, `!stop`, etc.). Replace each `!command` with `/command` and remove any alias columns/notes. Add the following note immediately above or below the table:

```markdown
> **Notas sobre comandos:**
> - Todos los comandos son slash commands (`/`). El prefijo `!` ya no funciona.
> - Como fallback, podés invocar al bot mencionándolo: `@SSJBot play d4vd`.
> - Los aliases anteriores (`!p`, `!s`, `!r`, `!q`, `!qc`, `!random`) fueron eliminados.
```

- [ ] **Step 5.2: Add GUILD_IDS to env vars section**

In the README section about environment variables, add:

```markdown
- `GUILD_IDS` (opcional): IDs de servidores donde se registran los slash commands, separados por coma. Si está vacío, los comandos se registran globalmente y pueden tardar hasta 1 hora en aparecer. Para obtener el ID de un server: activá Modo Desarrollador en Discord → click derecho al server → Copiar ID.
```

- [ ] **Step 5.3: Final test run**

Run: `python -m pytest -q`
Expected: 10 passed.

- [ ] **Step 5.4: Commit docs**

```bash
git add README.md
git commit -m "document slash commands migration"
```

- [ ] **Step 5.5: Merge to develop**

```bash
git checkout develop
git merge --no-ff feature/migrate-to-slash-commands -m "merge feature/migrate-to-slash-commands into develop"
git push origin develop
```

- [ ] **Step 5.6: Merge to main**

```bash
git checkout main
git merge --no-ff develop -m "release slash commands migration"
git push origin main
git checkout develop
```

(The `git checkout develop` at the end follows the AGENTS.md rule: always return to `develop` after merging to `main`.)

- [ ] **Step 5.7: Delete local feature branch**

```bash
git branch -d feature/migrate-to-slash-commands
```

- [ ] **Step 5.8: Deploy to home server**

User runs on the Ubuntu Server via SSH:

```bash
cd ~/ssj-bot
git pull
nano .env  # add GUILD_IDS=<your guild ids> if not yet set
sudo docker compose up -d --build
sudo docker compose logs --tail=80
```

Expected: build succeeds, logs show:
- `SSJ Bot conectado en N servidor(es).`
- `Slash commands sincronizados en X/Y guild(s).` (or global sync message).

- [ ] **Step 5.9: Manual smoke tests in Discord**

In a server where the bot is present:

1. Type `/` → confirm new slash commands appear (`/play`, `/search`, `/dbz`, etc.).
2. `/search d4vd` → confirm the dropdown appears **only to you** with the "Only you can see this" indicator.
3. `/play d4vd` → bot joins voice and plays.
4. `/dbz` → playlist loads, single confirmation message (no spam).
5. `@SSJBot play d4vd` → mention works as fallback.
6. `!play d4vd` → bot does NOT respond.

If any test fails, debug before declaring complete.

---

## Self-Review Notes

Spec coverage check:
- ✅ All 13 commands enumerated and migrated (Tasks 2 + 3).
- ✅ `command_prefix=commands.when_mentioned` (Task 1.4).
- ✅ `GUILD_IDS` env var with per-guild sync (Task 1.3, 1.5, 1.7).
- ✅ `on_app_command_error` handler (Task 1.6).
- ✅ `play` split into public/internal with silent (Task 2).
- ✅ Aliases removed: `p`, `s`, `r`, `q`, `qc`, `random` (Task 3.1).
- ✅ `defer()` on slow commands: `play` (Task 2), `dbz`, `anime`, `search` (Task 3.2).
- ✅ `SearchView` ephemeral (Task 4).
- ✅ `.env.example` and README docs (Tasks 1.7, 5).
- ✅ Smoke tests covering all 6 manual scenarios (Task 5.9).

Risks coverage:
- ✅ Per-guild sync errors caught individually (Task 1.5).
- ✅ Keyword-only `*` separator dropped in `play` and `search` (Task 3 notes).
- ✅ `on_app_command_error` uses `is_done()` correctly (Task 1.6).
