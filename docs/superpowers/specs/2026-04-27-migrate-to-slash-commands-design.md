# Spec: Migrate to Slash Commands

Date: 2026-04-27
Branch: `feature/migrate-to-slash-commands`

## Problem

Discord bot currently uses prefix commands (`!play`, `!search`, etc.). The
`!search` command sends a `discord.ui.Select` menu attached to a public
message, which is visible and clickable to **every** user in the channel,
not just the command author. The existing `interaction_check` guard
correctly blocks selections from other users, but the menu still appears
in their UI, which is confusing.

Discord only allows ephemeral messages (visible to one user) in response
to **interactions** (slash commands or component clicks), not in response
to prefix commands. To get an ephemeral search menu, `!search` must be a
slash command.

The user decided to migrate **all 13 commands** to slash commands at once,
disabling the `!` prefix entirely, rather than maintaining two systems.

## Goal

Convert all music bot commands from prefix-based (`!command`) to
discord.py hybrid commands (`/command`) and disable the text prefix,
restricting bot invocations to slash commands and bot mentions.

## Non-Goals

- Improve message styling (embeds, colors, thumbnails). Deferred to a
  separate branch.
- Migrate the `coin` / `random` command's logic.
- Add localizations or translations.
- Add per-command permission checks beyond what already exists.
- Implement a manual `/sync` admin command. Auto-sync on `on_ready` is
  sufficient for this hobby bot.

## Design

### Approach: Hybrid Commands

Use `@commands.hybrid_command` instead of pure `app_commands`. Reason:
the existing code is heavily coupled to `commands.Context` (`ctx.send`,
`ctx.author`, `ctx.voice_client`, `_state(ctx)`, `update_activity(ctx)`).
Hybrid commands give us a `Context` object even when invoked via slash,
so 90% of the existing logic works unchanged. The only places that
explicitly need `discord.Interaction` are component callbacks
(`SearchSelect.callback`), which already use it correctly today.

### Component Changes

**`bot.py`:**
- Replace `command_prefix="!"` with `command_prefix=commands.when_mentioned`.
  This disables the `!` prefix; the bot still responds to `@SSJBot play d4vd`
  as a fallback. This is the official discord.py idiom for "no text prefix".
- Read `GUILD_IDS` env var as comma-separated list of guild IDs.
- In `on_ready`, iterate `GUILD_IDS` and call
  `await bot.tree.sync(guild=discord.Object(id=gid))` for each. Wrap in
  `try/except` per guild so one bad ID doesn't crash the bot.
- If `GUILD_IDS` is empty, fall back to global sync (`bot.tree.sync()`),
  which can take up to 1 hour to propagate.
- Log a single line per sync result: success count and skipped guilds.
- Add a minimal `on_app_command_error` handler at the bot level that logs
  the error and sends a generic followup message
  ("Ocurrió un error inesperado.") to the user. Uses
  `interaction.followup.send` if `interaction.response.is_done()`,
  otherwise `interaction.response.send_message`.

**`cogs/music_cog.py`:**

For all 13 commands, replace `@commands.command(...)` with
`@commands.hybrid_command(...)`:

- `dbz`, `anime`, `play`, `stop`, `skip`, `pause`, `resume`, `queue`,
  `rq` (remove from queue by position), `clear`, `shuffle`, `coin`,
  `search`.

Per-command modifications:

- **Aliases removed**: `p` (play), `s` (skip), `r` (resume),
  `q` (queue), `qc` (clear), `random` (coin). Slash commands offer
  auto-completion; aliases lose value. Documented in README.

- **Type hints required**: slash commands need explicit type annotations
  for parameters. Add `ctx: commands.Context` to all signatures and type
  annotations to user-facing parameters.

- **Preserve `*, search: str` (consume-rest)**: hybrid commands do
  support keyword-only string arguments (per discord.py docs, e.g.
  `tag create(ctx, name: str, *, content: str)`). Keeping `*,` ensures
  multi-word queries work via the prefix/mention fallback (e.g.
  `@SSJBot play d4vd romantic homicide`). On the slash side, the
  parameter is treated as a single string that accepts spaces natively,
  so the marker is harmless.

- **`defer()` on slow commands**: `play`, `dbz`, `anime`, `search` start
  with `await ctx.defer()` to avoid the 3-second slash command response
  timeout. discord.py converts subsequent `ctx.send` calls to
  `interaction.followup.send` automatically.

- **`play()` split into public/internal**:
  - `play(self, ctx, *, search: str)` is the hybrid command (no `silent`
    parameter exposed).
  - `_play_internal(self, ctx, search: str, silent: bool = False)` is a
    private helper containing the existing logic. `play()` delegates to
    `_play_internal(ctx, search, silent=False)`. `play_playlist` calls
    `_play_internal(ctx, url, silent=True)` directly.

- **`SearchView` ephemeral**: in the `search` command, change
  `await ctx.send(view=view)` to
  `await ctx.send(view=view, ephemeral=ctx.interaction is not None)`.
  When invoked via slash, the menu is ephemeral (only the author sees
  it). When invoked by mention, the menu is public (existing behavior).

**`.env.example`:**
- Add `GUILD_IDS=` (empty by default) with a comment explaining how to
  obtain guild IDs (Discord Developer Mode → right-click server → Copy ID).

**`README.md`:**
- Replace `!command` references with `/command` in the commands table.
- Add `GUILD_IDS` to the environment variables section.
- Note that aliases (`!p`, `!s`, etc.) no longer exist.
- Note that `@SSJBot command` works as a fallback to slash commands.

### Data Flow

The user invokes `/play d4vd` in Discord. Discord sends an interaction
to the bot. discord.py routes it through the `hybrid_command` system,
constructs a `Context` with `ctx.interaction` populated, and calls
`Music.play(self, ctx, search="d4vd")`. The method calls `await
ctx.defer()`, then `await self._play_internal(ctx, "d4vd", silent=False)`,
which runs the existing yt-dlp extraction logic. When the existing code
calls `await ctx.send("Se agregó a la cola: X")`, discord.py routes it
through `interaction.followup.send` automatically.

For `/search d4vd`: the command defers, runs ytsearch5, builds a
`SearchView`, and sends it via `await ctx.send(view=view,
ephemeral=True)`. Only the author sees the dropdown. When the author
selects an option, `SearchSelect.callback(interaction)` runs (uses raw
`Interaction`, unchanged).

### Error Handling

- Per-guild sync errors: caught individually, logged at WARNING, sync
  continues for remaining guilds.
- Slash command runtime errors: caught by `on_app_command_error`, logged
  at ERROR with traceback, generic message sent to user.
- Existing per-command try/except blocks remain unchanged; they catch
  specific yt-dlp / Discord API errors and send user-friendly messages
  via `ctx.send`.

### Testing

New tests:
- `tests/test_search_view_ephemeral.py`: invokes the `search` command
  flow with a mocked `Context` whose `interaction` is non-None and
  asserts that `ctx.send` was called with `ephemeral=True`. Also tests
  the mention path (`interaction is None`) asserts `ephemeral=False`.
- `tests/test_play_internal_separation.py`: verifies
  `_play_internal(silent=True)` does not call `ctx.send` for the
  "Se agregó a la cola" message, and `_play_internal(silent=False)`
  does. The hybrid `play` command always passes `silent=False`.

Existing tests untouched:
- `tests/test_extract_info.py` (3 tests).
- `tests/test_utils.py` (2 tests).
- `tests/test_select_candidate.py` (1 test).

Manual smoke tests after deploy:
1. `/search d4vd` → dropdown appears ephemerally only to the author.
2. `/play d4vd` → bot joins voice and plays.
3. `/dbz` → playlist loads without spam (single "Se agregó la playlist"
   message).
4. `@SSJBot play d4vd` → works (mention fallback).
5. `!play d4vd` → does NOT work.

### Risks and Mitigations

- **Risk**: `GUILD_IDS` misconfigured (ID not a real guild, or bot is
  not in that guild). **Mitigation**: per-guild try/except with WARNING
  log; bot continues running.
- **Risk**: `discord.py 2.7.1` quirks with hybrid commands and
  keyword-only parameters. **Mitigation**: drop the `*` separator in
  `play(search)` and `search(query)`.
- **Risk**: users tipear `!play` por costumbre y no funciona.
  **Mitigation**: README updated; announce on server.
- **Risk**: First sync fails or rate-limited. **Mitigation**: log error
  clearly so user knows to retry; provide manual recovery path
  (restart bot).
- **Risk**: Adding `on_app_command_error` could double-handle errors
  also caught by per-command try/except. **Mitigation**: per-command
  blocks catch domain errors before the global handler; the global
  handler only fires for unhandled exceptions, which is the intended
  behavior.

## Migration Strategy

Single PR (`feature/migrate-to-slash-commands` → `develop` → `main`).
Implementation executed via subagent-driven-development with one
subagent per command (sequential, since all edits target
`cogs/music_cog.py`). The plan document will enumerate per-command
tasks with explicit acceptance criteria.

## Out of Scope (Future Work)

- Embed-styled messages (`feature/embed-messages` branch later).
- Command-level permissions (e.g., admin-only `/clear`).
- Per-guild prefix override (replaced by slash).
- `/sync` admin command (add only if auto-sync proves insufficient).
