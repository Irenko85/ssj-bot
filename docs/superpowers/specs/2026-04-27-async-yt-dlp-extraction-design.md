# Async yt-dlp Extraction — Design Spec

**Date:** 2026-04-27
**Branch:** `fix/async-yt-dlp-extraction`
**Author:** Irenco Peña (with assistant)
**Scope:** Hobby bot used by a small group of friends (low concurrency, no SLA).

## Problem

`yt_dlp.YoutubeDL.extract_info(...)` is synchronous and currently called from
inside `async def` coroutines. Every call blocks the asyncio event loop for as
long as YouTube takes to respond (often several seconds). The Discord voice
client requires the loop to send heartbeats every ~13 seconds; when extractions
exceed that window, `discord.py` logs `voice heartbeat blocked for more than 10
seconds` and audio playback degrades or drops.

Seven call sites are affected:

| # | File | Line | Context |
|---|------|------|---------|
| 1 | `cogs/music_cog.py` | 432 | `play()` — single video URL extraction |
| 2 | `cogs/music_cog.py` | 441 | `play()` — fallback `format=best` retry |
| 3 | `cogs/music_cog.py` | 456 | `play()` — `ytsearch5:` query |
| 4 | `cogs/music_cog.py` | 473 | `play()` — loop over candidate URLs |
| 5 | `cogs/music_cog.py` | 721 | `search` command — `ytsearch5:` query |
| 6 | `cogs/music_cog.py` | 768 | `SearchSelect.callback` — extract chosen video |
| 7 | `utils/utils.py`    | 14  | `get_video_urls_from_playlist` (sync function called from async code) |

## Goals

- Stop blocking the event loop during yt-dlp extractions.
- Keep the change small and focused — this is a hobby project.
- Add minimal automated tests (pytest + pytest-asyncio) covering the new async
  glue. Use TDD for the new code.
- Bound extraction time with a hardcoded timeout so a hung yt-dlp call can't
  keep a thread (or a Discord command) alive forever.

## Non-Goals

- No general audit of other potentially blocking calls.
- No retry logic for transient failures.
- No cancellation of in-flight extractions when the user runs `!stop`.
- No env-var or runtime configuration of timeouts.
- No refactor toward a `YtDlpClient` abstraction.
- No 100% test coverage. Tests focus on the new async glue, not on every
  Discord command path (mocking discord.py would be more work than the fix).

## Architecture

### 1. Helper in `Music` cog

Add a class constant and an async helper that wraps every `extract_info` call
in `asyncio.to_thread` plus `asyncio.wait_for`:

```python
class Music(commands.Cog):
    EXTRACT_TIMEOUT_SECONDS = 30

    async def _extract_info(self, ydl, *args, **kwargs):
        """Run blocking ydl.extract_info in a worker thread, with timeout.

        Re-raises asyncio.TimeoutError after logging a warning so callers
        can decide how to react.
        """
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
```

`asyncio` is already imported in `music_cog.py`.

### 2. Migrate the six cog call sites

Replace each `ydl.extract_info(...)` (or `ydl_fb.extract_info(...)`,
`ydl_search.extract_info(...)`) with
`await self._extract_info(ydl, ...)` (or the corresponding instance).

The `SearchSelect.callback` (line 768) lives in a separate class but already
holds `self.music_cog`, so it calls `await self.music_cog._extract_info(ydl, ...)`.

### 3. Convert `utils.get_video_urls_from_playlist` to async

```python
import asyncio

async def get_video_urls_from_playlist(playlist_url: str) -> list[str]:
    """Get video URLs from a YouTube playlist using yt-dlp (async, non-blocking)."""
    ydl_opts = {
        "quiet": True,
        "extract_flat": True,
        "skip_download": True,
    }

    def _do_extract():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(playlist_url, download=False)

    try:
        info = await asyncio.wait_for(asyncio.to_thread(_do_extract), timeout=30)
    except asyncio.TimeoutError:
        print("Playlist extraction timed out")
        return []
    except Exception as e:
        print(f"Error al obtener la playlist: {e}")
        return []

    return [
        f"https://www.youtube.com/watch?v={entry['id']}"
        for entry in info.get("entries", [])
        if "id" in entry
    ]
```

Two callers updated to `await`:
- `cogs/music_cog.py:327`
- `cogs/music_cog.py:402`

The `30` second timeout in `utils.py` is duplicated as a literal (not imported
from the cog) on purpose: importing it would couple `utils` to a specific cog,
violating the existing layering. Acceptable for a hobby project with one
shared value.

### 4. Error handling

`asyncio.TimeoutError` is a subclass of `Exception`, so the existing broad
`except Exception` blocks at lines 505–509 (play), 723–725 (search), and
771–776 (SearchSelect) catch it automatically. We do **not** add specific
timeout handlers per call site; the user-facing message stays generic
("Ocurrió un error al intentar procesar la canción o playlist."). The `logger.warning`
inside `_extract_info` provides server-side diagnostic.

The one nuance is the candidate loop at line 473: today it `continue`s on
`DownloadError` "format not available". A `TimeoutError` there will currently
abort the loop (caught by the outer except). We accept that — for a hobby bot,
falling back to "an error occurred" is fine.

## Tests

`tests/` directory with pytest + pytest-asyncio. Tests target the two new
pieces of glue, not the full Discord command paths.

`tests/test_extract_info.py` — three tests for `Music._extract_info`:
1. Runs in a worker thread (capture `threading.current_thread()` inside the mock; assert it differs from the event-loop thread).
2. Returns the value produced by `extract_info`.
3. Raises `asyncio.TimeoutError` when the mock outlasts the timeout (override `EXTRACT_TIMEOUT_SECONDS` to a small value in the test).

`tests/test_utils.py` — two tests for `utils.get_video_urls_from_playlist`:
1. Returns the expected list of URLs from a mocked `YoutubeDL`.
2. Returns `[]` when the mocked `extract_info` raises.

`conftest.py` minimal: pytest-asyncio mode set to `auto` via `pytest.ini`.

Total: 5 tests.

## Verification

Beyond the automated tests:
- Manual smoke test: launch the bot, run `!play <url>`, `!play <search query>`, `!search <query>`, `!play <playlist url>`. Watch `bot.log` for absence of `voice heartbeat blocked` warnings.
- Subjective: audio plays without stutter at the start.

## Files Changed

- **New:**
  - `requirements-dev.txt`
  - `pytest.ini`
  - `tests/__init__.py`
  - `tests/conftest.py`
  - `tests/test_extract_info.py`
  - `tests/test_utils.py`
- **Modified:**
  - `cogs/music_cog.py` (add helper, migrate 6 call sites, update 2 callers of `get_video_urls_from_playlist`)
  - `utils/utils.py` (function becomes `async`, adds `asyncio` import, adds timeout)
- **Unchanged:**
  - `bot.py`, `requirements.txt`, `.env`, README

## Open Questions

None for now.
