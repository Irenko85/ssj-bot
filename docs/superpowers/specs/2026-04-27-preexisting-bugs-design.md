# Spec: Fix preexisting bugs and add minimal logging

**Date:** 2026-04-27
**Branch:** `fix/preexisting-bugs`
**Base:** `develop`

## Context

Production logs from the running bot revealed three preexisting issues that
predate the slash commands migration:

1. `SearchSelect.callback` calls `self.stop()` but `discord.ui.Select` has no
   `stop()` method (it exists on `View`). This raises `AttributeError` every
   time a user selects a song from `!search`. Confirmed in production logs:
   the crash occurs reliably and visibly disrupts the search flow.
2. `skip`, `pause`, and `resume` silently return when there is nothing to act
   on (no voice client, not playing, not paused). Users get no feedback and
   assume the bot is broken.
3. `CommandNotFound` errors from random `!d`, `!aaa` style typos are logged as
   exceptions, polluting logs without being actionable.

Logs are also sparse: no command invocations are logged, making future
debugging painful.

## Goals

- Eliminate the `SearchSelect` crash.
- Provide user feedback when `skip`/`pause`/`resume` cannot act.
- Silence `CommandNotFound` errors (no log spam, no user response).
- Add minimal `logger.info` instrumentation in key commands and music
  pipeline events to enable future debugging.

## Non-goals

- Refactoring the music pipeline.
- Retrying transient YouTube 503 errors.
- Comprehensive structured logging (JSON, levels-per-component, etc).
- Touching the slash commands migration code beyond what these fixes require.

## Design

### Fix 1: SearchSelect.stop()

**File:** `cogs/music_cog.py:840`

Replace `self.stop()` with `self.view.stop()`. `SearchSelect` is a
`discord.ui.Select` and `View.stop()` is the correct API to terminate the
parent view.

### Fix 2: User feedback in skip/pause/resume

**File:** `cogs/music_cog.py` (skip, pause, resume hybrid commands)

Add an `else` branch that sends a visible message to the channel:

- `skip` → `"No hay nada que skipear."`
- `pause` → `"No hay nada reproduciéndose para pausar."`
- `resume` → `"No hay nada pausado para reanudar."`

Visible (not ephemeral) to stay consistent with the existing success messages
which are also visible.

### Fix 3: Silence CommandNotFound

**File:** `bot.py`

Add a global `on_command_error` event handler:

```python
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    raise error
```

`raise error` preserves default behavior (logging + traceback) for any other
error, so we do not mask real bugs.

### Logging

Add `logger.info` calls at the entry of high-value commands and music
pipeline transitions. Format:

```
"<command> invoked by <user> in guild <guild_id>: <relevant args>"
```

Targets (~11 lines total):

1. `play` — entry, with `search` query
2. `_play_internal` — when actual playback starts (after queue/voice setup)
3. `search` — entry, with `query`
4. `skip`, `pause`, `resume` — entry (one each)
5. `dbz`, `anime`, `coin` — entry (one each)
6. `play_next_in_queue` — when transitioning to next song
7. `SearchSelect.callback` — when a user selects a song

Use the existing `logger = logging.getLogger(__name__)` already in the file.
Bot already has logging configured in `bot.py`.

## Testing

TDD for the three bug fixes. No tests for logging (no testable logic).

### Test 1: `tests/test_search_select_stop.py`

- Instantiate `SearchSelect` with mocked entries/cog/ctx.
- Mock `self.view` with a spy on `stop`.
- Mock the rest of `callback` dependencies (interaction, music_cog state).
- Call `await select.callback(interaction)`.
- Assert `self.view.stop()` was called exactly once.
- Assert no `AttributeError` is raised.

### Test 2: `tests/test_skip_pause_resume_feedback.py`

For each of `skip`, `pause`, `resume`:

- Mock `ctx` with `voice_client=None` (or `is_playing()=False`,
  `is_paused()=False`).
- Call the command callback via `cog.skip.callback(cog, ctx)` (and analogous).
- Assert `ctx.send` was called with the expected message.

### Test 3: `tests/test_command_not_found_handler.py`

- Instantiate the handler logic (extract into a helper if necessary, or
  invoke `bot.on_command_error` directly with mocked ctx and a fake
  `CommandNotFound` instance).
- Assert it returns silently without raising or invoking ctx.send.
- Invoke with a non-`CommandNotFound` error and assert it re-raises.

## Implementation order

Sequential tasks (same file mostly):

1. **Task A** — Fix 1 + Test 1
2. **Task B** — Fix 2 + Test 2
3. **Task C** — Fix 3 + Test 3
4. **Task D** — Logging additions

Each task: TDD, 10/10 tests pass before moving on, commit with focused
message.

## Risks

- **Test 1 may need extensive mocking** of `SearchSelect.callback` because
  the real callback hits yt-dlp and queue state. We can short-circuit by
  patching `self.music_cog._state` and `info_extract` calls.
- **Test 3 relies on the handler signature.** If implementing as
  `@bot.event` decorator inside `bot.py`, testing requires importing
  `bot.on_command_error` directly which may need refactoring to expose it.
  Alternative: implement as a free function `handle_command_error(ctx, error)`
  registered via `bot.add_listener`, easier to test.

## Deployment

After merge to `develop`, deploy to production together with the slash
commands migration that already lives in `develop`. No extra steps.
