# Async yt-dlp Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop blocking the asyncio event loop during yt-dlp extractions in `cogs/music_cog.py` and `utils/utils.py`, eliminating `voice heartbeat blocked` warnings.

**Architecture:** Wrap every blocking `ydl.extract_info(...)` call in `asyncio.to_thread(...)` plus `asyncio.wait_for(..., timeout=30)`. Add a small `Music._extract_info` helper for the six cog call sites. Convert `utils.get_video_urls_from_playlist` to an async function. Add a minimal pytest setup and 5 unit tests (TDD) covering the new async glue.

**Tech Stack:** Python 3.13, discord.py 2.7.1, yt-dlp 2026.1.31, pytest, pytest-asyncio.

**Spec:** `docs/superpowers/specs/2026-04-27-async-yt-dlp-extraction-design.md`

**Branch:** `fix/async-yt-dlp-extraction`

---

## File Structure

**New files:**
- `requirements-dev.txt` — dev-only dependencies (pytest, pytest-asyncio).
- `pytest.ini` — pytest config (asyncio mode auto).
- `tests/__init__.py` — empty marker, makes `tests` a package.
- `tests/conftest.py` — empty for now; added to allow shared fixtures later if needed.
- `tests/test_extract_info.py` — 3 tests for `Music._extract_info`.
- `tests/test_utils.py` — 2 tests for `utils.get_video_urls_from_playlist`.

**Modified files:**
- `.gitignore` — add `.pytest_cache/`.
- `utils/utils.py` — `get_video_urls_from_playlist` becomes `async`, uses `asyncio.to_thread` + timeout.
- `cogs/music_cog.py` — add `EXTRACT_TIMEOUT_SECONDS` and `_extract_info` helper on `Music`, migrate 6 call sites, `await` the 2 callers of `get_video_urls_from_playlist`.

---

## Task 0: Pytest setup

**Files:**
- Create: `requirements-dev.txt`
- Create: `pytest.ini`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Modify: `.gitignore`

- [ ] **Step 1: Create `requirements-dev.txt`**

```
pytest==8.3.4
pytest-asyncio==0.25.0
```

- [ ] **Step 2: Create `pytest.ini`**

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
```

- [ ] **Step 3: Create `tests/__init__.py`**

Empty file.

- [ ] **Step 4: Create `tests/conftest.py`**

```python
"""Shared pytest fixtures for ssj-bot tests."""
```

(Just a docstring placeholder; future fixtures will live here.)

- [ ] **Step 5: Update `.gitignore`**

Append the line `.pytest_cache/` to `.gitignore`.

After edit, the file should contain (last lines):

```
cookies/
tmpclaude-*
.pytest_cache/
```

- [ ] **Step 6: Install dev dependencies in venv**

Run (PowerShell):
```powershell
.\venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

Expected: pytest and pytest-asyncio installed without errors.

- [ ] **Step 7: Verify pytest discovers no tests yet (sanity check)**

Run:
```powershell
.\venv\Scripts\python.exe -m pytest
```

Expected output: `no tests ran` or similar (exit code 5, "no tests collected"). This confirms pytest is wired up.

- [ ] **Step 8: Commit**

```powershell
git add requirements-dev.txt pytest.ini tests/__init__.py tests/conftest.py .gitignore
git commit -m "add pytest setup"
```

---

## Task 1: TDD — `Music._extract_info` helper

We add the helper using strict TDD: write each failing test, watch it fail, write the minimal implementation, watch it pass, repeat for the next test.

**Files:**
- Modify: `cogs/music_cog.py` (add constant + method on `Music` class)
- Create: `tests/test_extract_info.py`

The `Music` class is a `commands.Cog` subclass. To instantiate it in tests we need a fake bot. discord.py's `commands.Cog.__init__` is permissive, so a `Mock` bot works. To call instance methods we just instantiate and invoke; no Discord connection needed.

### Test 1a — runs in worker thread

- [ ] **Step 1: Write the failing test**

In `tests/test_extract_info.py`:

```python
"""Tests for Music._extract_info async helper."""
import asyncio
import threading
from unittest.mock import Mock

import pytest

from cogs.music_cog import Music


def _make_cog():
    """Instantiate Music cog with a mock bot, bypassing discord setup."""
    bot = Mock()
    return Music(bot)


@pytest.mark.asyncio
async def test_extract_info_runs_in_worker_thread():
    cog = _make_cog()
    main_thread_id = threading.get_ident()
    captured_thread_id = {}

    def fake_extract(*args, **kwargs):
        captured_thread_id["id"] = threading.get_ident()
        return {"title": "x"}

    fake_ydl = Mock()
    fake_ydl.extract_info = fake_extract

    await cog._extract_info(fake_ydl, "https://example.com")

    assert captured_thread_id["id"] != main_thread_id
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```powershell
.\venv\Scripts\python.exe -m pytest tests/test_extract_info.py::test_extract_info_runs_in_worker_thread -v
```

Expected: FAIL with `AttributeError: 'Music' object has no attribute '_extract_info'`.

- [ ] **Step 3: Add minimal implementation in `cogs/music_cog.py`**

Locate the `Music` class. Add the constant at the top of the class body (right after the docstring or first attribute) and the helper method.

Find the class header (around line where `class Music(commands.Cog):` appears) and add:

```python
class Music(commands.Cog):
    EXTRACT_TIMEOUT_SECONDS = 30

    # ... existing __init__ and other methods ...

    async def _extract_info(self, ydl, *args, **kwargs):
        """Run blocking ydl.extract_info in a worker thread, with timeout."""
        return await asyncio.to_thread(ydl.extract_info, *args, **kwargs)
```

(For now, no `wait_for` — the next test drives that in.)

Place `EXTRACT_TIMEOUT_SECONDS = 30` as a class-level constant near the top of `Music`, and `_extract_info` near the other helper methods (e.g., near `_state` or `_cleanup_state`). Find a good location by reading the existing structure.

- [ ] **Step 4: Run test to verify it passes**

Run:
```powershell
.\venv\Scripts\python.exe -m pytest tests/test_extract_info.py::test_extract_info_runs_in_worker_thread -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add cogs/music_cog.py tests/test_extract_info.py
git commit -m "add Music._extract_info helper"
```

### Test 1b — returns the value

- [ ] **Step 6: Write the failing test**

Append to `tests/test_extract_info.py`:

```python
@pytest.mark.asyncio
async def test_extract_info_returns_value():
    cog = _make_cog()
    fake_ydl = Mock()
    fake_ydl.extract_info = Mock(return_value={"title": "song", "url": "u"})

    result = await cog._extract_info(fake_ydl, "https://example.com")

    assert result == {"title": "song", "url": "u"}
    fake_ydl.extract_info.assert_called_once_with("https://example.com")
```

- [ ] **Step 7: Run test to verify it passes immediately**

Run:
```powershell
.\venv\Scripts\python.exe -m pytest tests/test_extract_info.py::test_extract_info_returns_value -v
```

Expected: PASS (the existing implementation already returns the value). This test acts as a regression guard — it does not drive new code.

If it FAILS, stop and investigate before continuing.

- [ ] **Step 8: Commit**

```powershell
git add tests/test_extract_info.py
git commit -m "add return-value regression test"
```

### Test 1c — timeout

- [ ] **Step 9: Write the failing test**

Append to `tests/test_extract_info.py`:

```python
@pytest.mark.asyncio
async def test_extract_info_raises_timeout(monkeypatch):
    cog = _make_cog()
    monkeypatch.setattr(Music, "EXTRACT_TIMEOUT_SECONDS", 0.05)

    def slow_extract(*args, **kwargs):
        import time
        time.sleep(0.5)
        return {"title": "never returned"}

    fake_ydl = Mock()
    fake_ydl.extract_info = slow_extract

    with pytest.raises(asyncio.TimeoutError):
        await cog._extract_info(fake_ydl, "https://example.com")
```

- [ ] **Step 10: Run test to verify it fails**

Run:
```powershell
.\venv\Scripts\python.exe -m pytest tests/test_extract_info.py::test_extract_info_raises_timeout -v
```

Expected: FAIL — the test waits ~0.5s and gets `{"title": "never returned"}` instead of `TimeoutError`.

- [ ] **Step 11: Update `_extract_info` to add timeout**

Replace the body of `_extract_info` in `cogs/music_cog.py`:

```python
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
```

- [ ] **Step 12: Run all extract_info tests, verify they pass**

Run:
```powershell
.\venv\Scripts\python.exe -m pytest tests/test_extract_info.py -v
```

Expected: 3 tests PASS. No warnings about coroutines never awaited.

- [ ] **Step 13: Commit**

```powershell
git add cogs/music_cog.py tests/test_extract_info.py
git commit -m "add timeout to _extract_info"
```

---

## Task 2: Migrate the six cog call sites

No new tests for this task — the helper is already covered, and migrating call sites is mechanical replacement. We rely on `python -m py_compile` for syntactic verification and on the manual smoke test (Task 4) for behavioral verification.

**Files:**
- Modify: `cogs/music_cog.py` (lines 432, 441, 456, 473, 721, 768 in current `develop`; line numbers will shift slightly after Task 1 adds the helper)

For each replacement, the change is the same shape:

| Before | After |
|--------|-------|
| `info = ydl.extract_info(...)` | `info = await self._extract_info(ydl, ...)` |
| `info = ydl_fb.extract_info(...)` | `info = await self._extract_info(ydl_fb, ...)` |
| `search_info = ydl_search.extract_info(...)` | `search_info = await self._extract_info(ydl_search, ...)` |

The `SearchSelect.callback` site (line 768) is in a different class and references the cog as `self.music_cog`, so the call becomes `await self.music_cog._extract_info(ydl, ...)`.

- [ ] **Step 1: Locate and replace site #1 (was line 432)**

Find the block:

```python
                            try:
                                info = ydl.extract_info(search, download=False)
                            except yt_dlp.utils.DownloadError as e:
```

Replace `info = ydl.extract_info(search, download=False)` with `info = await self._extract_info(ydl, search, download=False)`.

- [ ] **Step 2: Replace site #2 (was line 441)**

Find:

```python
                                    with SafeYoutubeDL(fallback_opts) as ydl_fb:
                                        info = ydl_fb.extract_info(
                                            search, download=False
                                        )
```

Replace with:

```python
                                    with SafeYoutubeDL(fallback_opts) as ydl_fb:
                                        info = await self._extract_info(
                                            ydl_fb, search, download=False
                                        )
```

- [ ] **Step 3: Replace site #3 (was line 456)**

Find:

```python
                            with SafeYoutubeDL(search_opts) as ydl_search:
                                search_info = ydl_search.extract_info(
                                    f"ytsearch5:{search}", download=False
                                )
```

Replace with:

```python
                            with SafeYoutubeDL(search_opts) as ydl_search:
                                search_info = await self._extract_info(
                                    ydl_search, f"ytsearch5:{search}", download=False
                                )
```

- [ ] **Step 4: Replace site #4 (was line 473)**

Find:

```python
                                try:
                                    info = ydl.extract_info(
                                        candidate_url, download=False
                                    )
                                    break
                                except yt_dlp.utils.DownloadError as e:
```

Replace with:

```python
                                try:
                                    info = await self._extract_info(
                                        ydl, candidate_url, download=False
                                    )
                                    break
                                except yt_dlp.utils.DownloadError as e:
```

- [ ] **Step 5: Replace site #5 (was line 721, inside `search` command)**

Find:

```python
        async with ctx.typing():
            with SafeYoutubeDL(search_options) as ydl:
                try:
                    info = ydl.extract_info(f"ytsearch5:{query}", download=False)
                    entries = info.get("entries", [])
                except Exception as e:
                    await ctx.send("Ocurrió un error al buscar la canción.")
                    logger.error(f"Error en search: {e}")
```

Replace `info = ydl.extract_info(f"ytsearch5:{query}", download=False)` with `info = await self._extract_info(ydl, f"ytsearch5:{query}", download=False)`.

- [ ] **Step 6: Replace site #6 (was line 768, inside `SearchSelect.callback`)**

Find:

```python
        try:
            url = f"https://www.youtube.com/watch?v={video_id}"
            with SafeYoutubeDL(YTDL_OPTIONS) as ydl:
                info = ydl.extract_info(url, download=False)
                url = info["url"]
                headers = self.music_cog._extract_http_headers(info, ydl)
        except Exception as e:
```

Replace `info = ydl.extract_info(url, download=False)` with `info = await self.music_cog._extract_info(ydl, url, download=False)`.

- [ ] **Step 7: Verify zero remaining `extract_info(` direct calls in `music_cog.py`**

Run:
```powershell
Select-String -Path cogs/music_cog.py -Pattern "\.extract_info\("
```

Expected output: only the `_extract_info` definition itself and lines that say `await ... self._extract_info(...)` or `await self.music_cog._extract_info(...)`. No bare `ydl.extract_info(`, `ydl_fb.extract_info(`, `ydl_search.extract_info(` calls remain.

- [ ] **Step 8: Compile-check**

Run:
```powershell
.\venv\Scripts\python.exe -m py_compile cogs/music_cog.py
```

Expected: exit code 0, no output.

- [ ] **Step 9: Run all tests, confirm green**

Run:
```powershell
.\venv\Scripts\python.exe -m pytest -v
```

Expected: 3 tests PASS (from Task 1). No new tests yet for Task 2.

- [ ] **Step 10: Commit**

```powershell
git add cogs/music_cog.py
git commit -m "migrate extract_info calls to async helper"
```

---

## Task 3: TDD — async `utils.get_video_urls_from_playlist`

**Files:**
- Modify: `utils/utils.py`
- Create: `tests/test_utils.py`

### Test 3a — returns video URLs

- [ ] **Step 1: Write the failing test**

In `tests/test_utils.py`:

```python
"""Tests for utils.get_video_urls_from_playlist."""
from unittest.mock import MagicMock, patch

import pytest

from utils import utils


@pytest.mark.asyncio
async def test_returns_video_urls():
    fake_info = {
        "entries": [
            {"id": "abc123"},
            {"id": "def456"},
            {"id": "ghi789"},
        ]
    }

    with patch("utils.utils.yt_dlp.YoutubeDL") as YDL:
        ydl_instance = MagicMock()
        ydl_instance.extract_info.return_value = fake_info
        YDL.return_value.__enter__.return_value = ydl_instance

        result = await utils.get_video_urls_from_playlist(
            "https://www.youtube.com/playlist?list=PLfake"
        )

    assert result == [
        "https://www.youtube.com/watch?v=abc123",
        "https://www.youtube.com/watch?v=def456",
        "https://www.youtube.com/watch?v=ghi789",
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```powershell
.\venv\Scripts\python.exe -m pytest tests/test_utils.py::test_returns_video_urls -v
```

Expected: FAIL with `TypeError: object list can't be used in 'await' expression` (current function is sync).

- [ ] **Step 3: Convert `utils.get_video_urls_from_playlist` to async**

Replace the entire content of `utils/utils.py` with:

```python
import asyncio
import yt_dlp
from urllib.parse import urlparse, parse_qs, urlunparse, urlencode


async def get_video_urls_from_playlist(playlist_url: str) -> list:
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


def clean_yt_link(link: str) -> str:
    """Cleans a YouTube link by removing unnecessary query args."""
    parsed_link = urlparse(link)
    query_params = {
        k: v
        for k, v in parse_qs(parsed_link.query).items()
        if k not in {"list", "start_radio", "index", "t"}
    }
    new_query = urlencode(query_params, doseq=True)
    new_link = urlunparse(parsed_link._replace(query=new_query))
    return new_link
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```powershell
.\venv\Scripts\python.exe -m pytest tests/test_utils.py::test_returns_video_urls -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add utils/utils.py tests/test_utils.py
git commit -m "convert get_video_urls_from_playlist to async"
```

### Test 3b — returns `[]` on extraction error

- [ ] **Step 6: Write the failing test**

Append to `tests/test_utils.py`:

```python
@pytest.mark.asyncio
async def test_returns_empty_on_error():
    with patch("utils.utils.yt_dlp.YoutubeDL") as YDL:
        ydl_instance = MagicMock()
        ydl_instance.extract_info.side_effect = RuntimeError("network down")
        YDL.return_value.__enter__.return_value = ydl_instance

        result = await utils.get_video_urls_from_playlist(
            "https://www.youtube.com/playlist?list=PLfake"
        )

    assert result == []
```

- [ ] **Step 7: Run test to verify it passes**

Run:
```powershell
.\venv\Scripts\python.exe -m pytest tests/test_utils.py::test_returns_empty_on_error -v
```

Expected: PASS (the existing `except Exception` clause handles `RuntimeError`).

This test acts as a regression guard for the error-handling path.

- [ ] **Step 8: Commit**

```powershell
git add tests/test_utils.py
git commit -m "add error-path regression test for utils"
```

---

## Task 4: Update callers of `get_video_urls_from_playlist`

**Files:**
- Modify: `cogs/music_cog.py` (current lines 327 and 402)

- [ ] **Step 1: Update caller at line 327 (in `play_playlist`)**

Find:

```python
        video_urls = utils.get_video_urls_from_playlist(playlist_url)
```

Replace with:

```python
        video_urls = await utils.get_video_urls_from_playlist(playlist_url)
```

- [ ] **Step 2: Update caller at line 402 (inside `play` command)**

Find:

```python
                if is_url and is_playlist:
                    logger.debug("Procesando playlist...")
                    video_urls = utils.get_video_urls_from_playlist(search)
```

Replace with:

```python
                if is_url and is_playlist:
                    logger.debug("Procesando playlist...")
                    video_urls = await utils.get_video_urls_from_playlist(search)
```

- [ ] **Step 3: Verify both callers updated**

Run:
```powershell
Select-String -Path cogs/music_cog.py -Pattern "get_video_urls_from_playlist"
```

Expected: 2 lines, both showing `await utils.get_video_urls_from_playlist(...)`.

- [ ] **Step 4: Compile-check**

Run:
```powershell
.\venv\Scripts\python.exe -m py_compile cogs/music_cog.py
.\venv\Scripts\python.exe -m py_compile utils/utils.py
```

Expected: exit code 0 for both.

- [ ] **Step 5: Run full test suite**

Run:
```powershell
.\venv\Scripts\python.exe -m pytest -v
```

Expected: 5 tests PASS (3 from Task 1, 2 from Task 3).

- [ ] **Step 6: Commit**

```powershell
git add cogs/music_cog.py
git commit -m "await async playlist helper in callers"
```

---

## Task 5: Manual smoke test + final review

This task has no automated steps; it is a manual verification + final review checkpoint.

- [ ] **Step 1: Confirm all automated tests pass**

Run:
```powershell
.\venv\Scripts\python.exe -m pytest -v
```

Expected: 5/5 PASS.

- [ ] **Step 2: Compile-check the full project**

Run:
```powershell
.\venv\Scripts\python.exe -m py_compile bot.py cogs/music_cog.py utils/utils.py
```

Expected: exit code 0.

- [ ] **Step 3: Launch bot in background**

Run:
```powershell
Start-Process -FilePath ".\venv\Scripts\python.exe" -ArgumentList "bot.py" -RedirectStandardOutput "bot.log" -RedirectStandardError "bot.err.log" -NoNewWindow
```

- [ ] **Step 4: Manual checks in Discord**

In a Discord server where the bot is invited:
1. Run `!play <single video URL>` — confirm audio starts.
2. Run `!play <search query>` (no URL) — confirm a result is found and plays.
3. Run `!search <query>` and pick an option from the dropdown — confirm playback.
4. Run `!play <playlist URL>` — confirm queue fills and starts playing.
5. While each command runs, watch `bot.log` in another terminal:
   ```powershell
   Get-Content bot.log -Wait -Tail 20
   ```

- [ ] **Step 5: Confirm absence of `voice heartbeat blocked` warnings**

Run:
```powershell
Select-String -Path bot.log -Pattern "voice heartbeat blocked"
```

Expected: no matches (or far fewer than before; ideally zero across a 5-minute session of playing music).

- [ ] **Step 6: Stop bot**

Run:
```powershell
Get-Process python | Stop-Process -Force
```

Then verify:
```powershell
Get-Process python -ErrorAction SilentlyContinue
```

Expected: no python processes left.

- [ ] **Step 7: Final review checklist**

Visually inspect the diff vs `develop`:
```powershell
git diff develop --stat
git log develop..HEAD --oneline
```

Confirm:
- All 7 original sync `extract_info` sites are replaced (search the full repo: `Select-String -Path cogs,utils -Pattern "extract_info\(" -Recurse` should show only `_extract_info` definition, `_do_extract` inner, and `await ... _extract_info(...)` call sites).
- Both `get_video_urls_from_playlist` callers use `await`.
- `tests/` has 5 tests.
- `requirements-dev.txt`, `pytest.ini`, `.gitignore` updated.

- [ ] **Step 8: Update todos and report**

Mark all plan tasks complete. Report any deviations from the plan and the runtime observations from Step 5.

No commit for this task — it's verification only.

---

## Self-review notes

- **Spec coverage:** All 7 sites covered (Task 1+2 cover 6 cog sites, Task 3+4 cover utils + its 2 callers). Helper, timeout, tests, manual verification all present.
- **No placeholders:** All code blocks are concrete. All commands are exact PowerShell commands matching the user's environment (Windows / pwsh / venv).
- **Type consistency:** `_extract_info(self, ydl, *args, **kwargs)` signature consistent across Task 1 and Task 2. `EXTRACT_TIMEOUT_SECONDS` referenced consistently.
- **TDD discipline:** Task 1c demonstrates true RED → GREEN cycle (timeout test fails before adding `wait_for`). Task 1a also a true RED → GREEN. Task 1b and Task 3b are deliberate regression tests (pass immediately) and the plan calls that out so the engineer doesn't conclude the test is wrong.
