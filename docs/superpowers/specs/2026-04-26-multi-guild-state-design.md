# Multi-guild state refactor

**Status:** approved
**Date:** 2026-04-26
**Branch target:** new feature branch from `develop`

## Problem

The bot currently stores music state as instance attributes on the `Music` cog:
`self.queue`, `self.actual_song`, `self.last_activity_timestamp`,
`self.inactivity_warned`, `self.inactivity_channel`. This state is global to the cog
instance, not per-server.

Consequence: if the bot is invited to two or more Discord servers and they use
music commands at the same time, queues mix, the inactivity timer competes, and
state from one guild leaks into another. The `voice_client` itself is already
per-guild thanks to discord.py, but the surrounding state is not.

The `.env` file also exposes a `GUILD_ID` variable that gives the false impression
that the bot is bound to one server. In reality it is only used for an
informational log line at startup.

## Goal

Make the bot fully multi-guild: each server has its own independent queue,
current song, inactivity timer, and notification channel. The bot must be able
to play music in N servers simultaneously. Drop the `GUILD_ID` configuration.

## Non-goals

- Persistence of queues across restarts.
- Per-guild configuration of volume, timeouts, or any other parameter.
- Server allow-list / whitelist.
- Adding an automated test suite (future follow-up).
- Changing the cookies handling (stays global).

## Approach

Introduce a small `GuildState` class that owns all per-server mutable state.
The `Music` cog keeps a single `dict[int, GuildState]` keyed by `guild.id`. A
helper method `_state(ctx)` returns or creates the state for the current guild,
so callers never deal with key-not-found cases.

The voice client itself is not stored. discord.py already manages one voice
client per guild. We obtain it from `ctx.voice_client` or
`discord.utils.get(self.bot.voice_clients, guild=g)` whenever needed.

This was preferred over an alternative design where each global attribute
becomes its own dict (`self.queues`, `self.actual_songs`, ...), because the
class-based approach keeps the per-guild data cohesive and reduces the chance
of forgetting to refactor an attribute.

## Components

### New

- `class GuildState`
  - `queue: list`
  - `actual_song: str | None`
  - `last_activity: float` (defaults to `time()`)
  - `inactivity_warned: bool`
  - `inactivity_channel: discord.TextChannel | None`
- `Music._state(ctx) -> GuildState`
  - Uses `setdefault` on `self.states` so it never raises.
- `Music._cleanup_state(guild_id: int) -> None`
  - Idempotent. `self.states.pop(guild_id, None)`.
  - Called when the bot disconnects from a guild's voice channel
    (manual `!stop`, inactivity timeout, or kicked from the channel).

### Modified

- `Music.__init__`: replace the five global attributes with
  `self.states: dict[int, GuildState] = {}`.
- Every command and helper that touched the old globals now starts with
  `s = self._state(ctx)` and operates on `s.queue`, `s.actual_song`, etc.
- `play_next_in_queue(ctx)` resolves the state from `ctx`.
- `update_activity(ctx)` accepts `ctx` (or guild) so it knows which state
  to update.
- `PlaylistFlattener` is constructed with the target `GuildState` instead of
  appending directly to `self.music_cog.queue`.
- The inactivity loop iterates over `list(self.states.items())` and evaluates
  each guild independently. It only disconnects the guilds that exceeded the
  threshold, leaving the rest untouched.
- All music commands gain a guild-only guard (either via
  `@commands.guild_only()` on the cog or an explicit early return).

### Removed

- `GUILD_ID` reading and validation in `bot.py`.
- The "Conectado al servidor X" log that depended on `GUILD_ID`.
  Replaced by a log listing all guilds the bot is connected to on `on_ready`.
- `GUILD_ID=...` line in `.env` and `.env.example` (if present).

## Data flow examples

**Play in server A while server B is active**

1. `!play` arrives in server A. `s_a = self._state(ctx_a)`.
2. discord.py creates `voice_client_a` independently of the existing
   `voice_client_b`.
3. The track is appended to `s_a.queue`. `s_b.queue` is untouched.
4. `play_next_in_queue(ctx_a)` reads from `s_a.queue` and plays via
   `ctx_a.voice_client`.

**Inactivity disconnects server A only**

1. The inactivity loop sees `time() - s_a.last_activity` exceeded the
   threshold.
2. Calls `voice_client_a.disconnect()`.
3. Calls `self._cleanup_state(guild_a.id)`.
4. Server B is not visited because its `last_activity` is still recent.

**Cold `!queue` in a guild that never played anything**

1. `_state(ctx)` creates an empty `GuildState` via `setdefault`.
2. The command sees `s.queue` empty and replies "Cola vacía".
3. No `KeyError`, no extra branching.

## Error handling

- `_state(ctx)` always returns a valid `GuildState` (never raises).
- `_cleanup_state` is idempotent (`pop` with default).
- Inactivity loop iterates over `list(self.states.items())` to be safe against
  concurrent mutation by `_cleanup_state`.
- DM invocation (`ctx.guild is None`) is rejected with a clear message instead
  of crashing.
- If a voice client disappears mid-playback, the existing exception handler
  in `play_next_in_queue` keeps doing its job; we only ensure that the
  `GuildState` is freed when the voice client is gone.

## Testing strategy

The repository has no automated test suite. Validation is manual:

1. **Single-server regression.** Run `!play`, `!queue`, `!skip`, `!stop`,
   `!shuffle`, `!clear`, `!pause`, `!resume` in one server. Behavior must be
   identical to before the refactor.
2. **Multi-server simultaneous play.** Run `!play` in two servers at once.
   Each must have its own queue and play its own track without interfering.
3. **Targeted cleanup.** `!stop` in server A; verify state of A is released
   (debug log) and B keeps working.
4. **Independent inactivity.** Leave the bot idle in server A while server B
   is active. Only A must disconnect when its timer expires.
5. **DM rejection.** Send `!play` in DM. Must reply with a friendly error,
   not crash.

## Files touched

- `cogs/music_cog.py` (main refactor, ~80% of the change)
- `bot.py` (drop `GUILD_ID`)
- `.env` (drop `GUILD_ID`)
- `.env.example` (if it exists, drop `GUILD_ID`)
- `README.md` (update env vars table)
- `docs/superpowers/specs/2026-04-26-multi-guild-state-design.md` (this file)

## Out of scope

See "Non-goals" above. Notably: persistence, per-guild configuration,
allow-lists, automated tests, cookies-per-guild.
