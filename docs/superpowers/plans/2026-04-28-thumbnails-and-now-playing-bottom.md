# Thumbnails and Now Playing Bottom Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Agregar thumbnails y metadatos de duración/enlace a los embeds de música, y cambiar la publicación de "Ahora reproduciendo" para que siempre reaparezca al final del chat.

**Architecture:** El cambio se concentra en dos puntos: enriquecimiento del dict `song` en `cogs/music_cog.py` y renderizado visual en `utils/ui.py`. La estrategia mantiene el flujo actual de cola/reproducción, pero hace que `_publish_now_playing` reemplace el mensaje previo mediante `delete()` + `send()` para asegurar posición final en el chat.

**Tech Stack:** Python, discord.py, pytest, unittest.mock, yt-dlp

---

### Task 1: Thumbnails in both embeds

**Files:**
- Modify: `cogs/music_cog.py:599-605`
- Modify: `cogs/music_cog.py:916-920`
- Modify: `utils/ui.py:58-87`
- Test: `tests/test_ui.py`
- Test: `tests/test_search_select_stop.py`

- [ ] **Step 1: Write the failing tests**

In `tests/test_ui.py` add:

```python
def test_build_now_playing_embed_uses_explicit_thumbnail_and_duration():
    embed = build_now_playing_embed(
        {
            "title": "Cha-La Head-Cha-La",
            "thumbnail": "https://cdn.example/thumb.jpg",
            "duration": 213,
            "webpage_url": "https://www.youtube.com/watch?v=YnL70cee6qo",
        }
    )
    assert embed.title == "🎵 Ahora reproduciendo"
    assert embed.thumbnail.url == "https://cdn.example/thumb.jpg"
    assert len(embed.fields) == 1
    assert embed.fields[0].name == "Duración"
    assert embed.fields[0].value == "213"


def test_build_added_to_queue_embed_sets_thumbnail_when_present():
    embed = build_added_to_queue_embed(
        {
            "title": "Limit Break x Survivor",
            "thumbnail": "https://cdn.example/queue-thumb.jpg",
        },
        position=3,
    )
    assert embed.title == "✅ Añadido a la cola"
    assert embed.description == "Limit Break x Survivor"
    assert embed.thumbnail.url == "https://cdn.example/queue-thumb.jpg"


def test_build_added_to_queue_embed_skips_thumbnail_when_missing():
    embed = build_added_to_queue_embed(
        {"title": "Limit Break x Survivor"},
        position=3,
    )
    assert embed.title == "✅ Añadido a la cola"
    assert embed.thumbnail.url is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_ui.py::test_build_now_playing_embed_uses_explicit_thumbnail_and_duration tests/test_ui.py::test_build_added_to_queue_embed_sets_thumbnail_when_present tests/test_ui.py::test_build_added_to_queue_embed_skips_thumbnail_when_missing -v`

Expected: FAIL

- [ ] **Step 3: Implement — utils/ui.py**

Update `build_now_playing_embed` to prefer `song.get("thumbnail")` over the regex fallback:

```python
def build_now_playing_embed(song: dict) -> discord.Embed:
    title = song.get("title", "Título desconocido")
    source_url = song.get("source_url") or song.get("webpage_url") or song.get("url")

    embed = discord.Embed(
        title="🎵 Ahora reproduciendo",
        description=f"**{title}**",
        colour=COLOR_PRIMARY,
    )

    thumbnail = song.get("thumbnail")
    if thumbnail:
        embed.set_thumbnail(url=thumbnail)
    else:
        video_id = _extract_youtube_video_id(source_url)
        if video_id:
            embed.set_thumbnail(url=f"https://img.youtube.com/vi/{video_id}/0.jpg")

    duration = song.get("duration")
    if duration:
        embed.add_field(name="Duración", value=str(duration), inline=True)

    embed.set_footer(text=_build_footer_text())
    return embed
```

Update `build_added_to_queue_embed` to set thumbnail:

```python
def build_added_to_queue_embed(song: dict, position: int) -> discord.Embed:
    embed = discord.Embed(
        title="✅ Añadido a la cola",
        description=song.get("title", "Título desconocido"),
        colour=COLOR_SUCCESS,
    )
    embed.add_field(name="Posición en cola", value=str(position), inline=True)
    thumbnail = song.get("thumbnail")
    if thumbnail:
        embed.set_thumbnail(url=thumbnail)
    return embed
```

- [ ] **Step 4: Implement — cogs/music_cog.py (play command, ~line 599)**

When building `song` dict in `play()`, add yt-dlp metadata fields:

```python
song = {
    "title": title,
    "url": url,
    "headers": headers,
    "thumbnail": info.get("thumbnail"),
    "duration": info.get("duration"),
    "webpage_url": info.get("webpage_url"),
}
```

- [ ] **Step 5: Implement — cogs/music_cog.py (SearchSelect.callback, ~line 916)**

Same enrichment in `SearchSelect.callback()`:

```python
song = {
    "title": title,
    "url": full_url,
    "headers": headers,
    "thumbnail": info.get("thumbnail"),
    "duration": info.get("duration"),
    "webpage_url": info.get("webpage_url"),
}
```

- [ ] **Step 6: Run all tests**

Run: `pytest tests/ -v`

Expected: all existing tests pass + new thumbnail tests pass.

- [ ] **Step 7: Commit**

```bash
git add utils/ui.py cogs/music_cog.py tests/test_ui.py
git commit -m "feat: add thumbnails and duration to music embeds"
```

---

### Task 2: Now Playing always at bottom

**Files:**
- Modify: `cogs/music_cog.py` — `_publish_now_playing` method
- Test: `tests/test_now_playing_flow.py`

- [ ] **Step 1: Write the failing test**

In `tests/test_now_playing_flow.py` add:

```python
@pytest.mark.asyncio
async def test_publish_now_playing_deletes_previous_message_and_sends_new_one():
    cog = Music.__new__(Music)
    cog.bot = MagicMock()
    cog.bot.loop = MagicMock()
    cog.states = {}

    ctx = MagicMock()
    ctx.guild = MagicMock(id=1)

    first_message = MagicMock()
    first_message.delete = AsyncMock()

    second_message = MagicMock()
    ctx.send = AsyncMock(return_value=second_message)

    state = cog._state(ctx)
    state.now_playing_message = first_message

    song = {
        "title": "Dan Dan Kokoro Hikareteku",
        "url": "https://stream.example/audio-2",
        "thumbnail": "https://cdn.example/np-thumb.jpg",
        "duration": 245,
        "webpage_url": "https://www.youtube.com/watch?v=5LVcwPrfNo4",
        "headers": {},
    }

    result = await cog._publish_now_playing(ctx, song)

    first_message.delete.assert_awaited_once()
    ctx.send.assert_awaited_once()
    assert state.now_playing_message is second_message
    assert result is second_message
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_now_playing_flow.py::test_publish_now_playing_deletes_previous_message_and_sends_new_one -v`

Expected: FAIL

- [ ] **Step 3: Implement — _publish_now_playing**

Replace current `_publish_now_playing` with:

```python
async def _publish_now_playing(self, ctx, song: dict):
    """Envía el mensaje de Now Playing con embed + botones, siempre al final del chat."""
    s = self._state(ctx)
    embed = build_now_playing_embed(song)
    view = make_music_control_view(self.bot, music_cog=self)

    if s.now_playing_message is not None:
        try:
            await s.now_playing_message.delete()
        except Exception:
            pass
        s.now_playing_message = None

    s.now_playing_message = await ctx.send(embed=embed, view=view)
    return s.now_playing_message
```

- [ ] **Step 4: Run all tests**

Run: `pytest tests/ -v`

Expected: all pass including `test_finalize_now_playing_paths.py` (finalize still edits `state.now_playing_message`).

- [ ] **Step 5: Commit**

```bash
git add cogs/music_cog.py tests/test_now_playing_flow.py
git commit -m "fix: now playing message always appears at bottom of chat"
```
