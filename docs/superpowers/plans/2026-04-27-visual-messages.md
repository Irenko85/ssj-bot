# Visual Messages Improvement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace all plain-text bot messages with rich Discord embeds and add music control buttons to the Now Playing message.

**Architecture:** Create `utils/ui.py` as the single source of truth for all visual output (embed builders + MusicControlView). Modify `cogs/music_cog.py` to use the new helpers, replacing all `ctx.send()` calls. Minimal changes to `bot.py` for global error handling.

**Tech Stack:** Python 3.13, discord.py 2.7.1, pytest

---

## Contexto relevante (del codebase)

- `cogs/music_cog.py:102-119` - `GuildState` usa `__slots__`; cualquier nuevo atributo debe a�adirse ah� y en `__init__`.
- `cogs/music_cog.py:242-297` - `play_next_in_queue()` inicia FFmpeg y hoy env�a `ctx.send()` plano al empezar o fallar reproducci�n.
- `cogs/music_cog.py:427-577` - `_play_internal()` resuelve URLs/b�squedas y a�ade canciones a la cola; hoy guarda `title`, `url`, `headers`, pero **no** una URL fuente apta para thumbnails de YouTube.
- `cogs/music_cog.py:579-666` - comandos `stop`, `skip`, `pause`, `resume`, `queue`, `clear`, `shuffle` todav�a devuelven texto plano.
- `cogs/music_cog.py:675-756` - `check_inactivity` manda avisos y desconexiones por texto a `inactivity_channel`.
- `cogs/music_cog.py:765-889` - `search`, `SearchSelect` y `SearchView` ya usan componentes UI de discord.py; sirven como referencia para `MusicControlView`.
- `bot.py:93-127` - handlers globales `on_app_command_error` y `handle_command_error` hoy responden con texto plano o re-lanzan errores.
- `tests/test_search_view_ephemeral.py:10-107` - patr�n actual para mockear `ctx.send`, `ctx.defer`, `ctx.typing` en comandos h�bridos.
- `tests/test_search_select_stop.py:10-103` - patr�n actual para mockear `interaction.response`, `interaction.followup`, `interaction.message` en componentes UI.
- `tests/conftest.py:1` - est� vac�o; no existe realmente un patr�n compartido reutilizable aqu�.

## File Structure

**Files to create**
- `utils/ui.py` - builders de embeds, helper de footer/thumbnail y `MusicControlView`.
- `tests/test_ui.py` - tests unitarios para builders de embeds.
- `tests/test_music_control_view.py` - tests unitarios de botones y callbacks del view.
- `tests/test_guild_state.py` - test m�nimo para `GuildState.now_playing_message`.
- `tests/test_now_playing_flow.py` - tests de integraci�n unitaria para env�o/edici�n del mensaje Now Playing.
- `tests/test_visual_command_embeds.py` - tests para `play/_play_internal`, `queue`, `search` y `SearchSelect` con embeds.
- `tests/test_inactivity_embeds.py` - tests del loop de inactividad con embeds.
- `tests/test_bot_error_embeds.py` - tests de handlers globales en `bot.py`.

**Files to modify**
- `cogs/music_cog.py` - integraci�n completa de embeds, persistencia del mensaje Now Playing y botones.
- `bot.py` - imports de `utils.ui` y uso de `build_error_embed`.
- `tests/test_skip_pause_resume_feedback.py` - adaptar asserts de texto a embeds.
- `tests/test_search_view_ephemeral.py` - adem�s del flag `ephemeral`, verificar que `/search` ya env�a embed.
- `tests/test_command_not_found_handler.py` - actualizar el comportamiento esperado del handler global de comandos.

**Files not touched**
- `utils/utils.py` - no requiere cambios para esta mejora visual.
- `requirements.txt`, `requirements-dev.txt`, `pytest.ini` - no hace falta a�adir dependencias.
- `tests/conftest.py` - como est� vac�o, no aporta nada �til para esta iteraci�n.

## Decisiones de dise�o

1. **Guardar `source_url` en cada canci�n en cola** - alternativa: extraer thumbnail desde `song["url"]`; se descarta porque hoy `url` es el stream directo de yt-dlp, no la URL de YouTube, as� que no sirve para derivar `img.youtube.com`.
2. **Usar `utils/ui.py` solo para construcci�n visual y callbacks del `MusicControlView`** - alternativa: mover lifecycle del mensaje Now Playing tambi�n ah�; se descarta porque editar mensajes, limpiar estado y coordinar voice clients pertenece al cog, no a una utilidad visual.
3. **A�adir helpers privados en `Music` para enviar feedback y finalizar el mensaje Now Playing** - alternativa: repetir `ctx.send(embed=...)` / `message.edit(...)` por todo el archivo; se descarta para evitar divergencias entre comandos, botones e inactividad.
4. **Mantener `SearchView` y `SearchSelect` en `music_cog.py`** - alternativa: migrarlos tambi�n a `utils/ui.py`; se descarta para no mezclar esta mejora visual con un refactor estructural extra.
5. **Footer del embed con nombre fijo `SSJ Bot` + hora actual** - alternativa: leer `bot.user.name`; se descarta en builders puros porque no reciben instancia del bot y el spec no exige variabilidad.
6. **`build_queue_embed()` tolera cola vac�a y pagina valores fuera de rango** - alternativa: lanzar error si `songs=[]` o `page` inv�lida; se descarta para que el comando `queue` y el bot�n `Ver cola` sean robustos.
7. **Los tests de `MusicControlView` ir�n en un archivo propio** - alternativa: meterlos todos en `tests/test_ui.py`; se descarta porque las views requieren mocks as�ncronos distintos y quedar�an mezclados con tests de builders puros.

## Plan de implementaci�n (paso a paso)

### Task 1: `utils/ui.py` - paleta de colores y `build_error_embed`

**Files:**
- Create: `utils/ui.py`
- Create: `tests/test_ui.py`

- [ ] **Step 1.1: Write the failing test**

Create `tests/test_ui.py` with:

```python
import discord

from utils.ui import COLOR_ERROR, build_error_embed


def test_build_error_embed_uses_error_palette():
    embed = build_error_embed("Boom")

    assert isinstance(embed, discord.Embed)
    assert embed.title == "? Error"
    assert embed.description == "Boom"
    assert embed.colour.value == COLOR_ERROR
```

- [ ] **Step 1.2: Run the test to verify it fails**

Run: `python -m pytest tests/test_ui.py::test_build_error_embed_uses_error_palette -v`  
Expected: FAIL with `ModuleNotFoundError: No module named 'utils.ui'`.

- [ ] **Step 1.3: Write the minimal implementation**

Create `utils/ui.py`:

```python
from __future__ import annotations

import discord

COLOR_PRIMARY = 0x6C3483
COLOR_SUCCESS = 0x2980B9
COLOR_ERROR = 0x922B21
COLOR_WARNING = 0xCA6F1E
COLOR_INFO = 0x2C3E50


def build_error_embed(message: str) -> discord.Embed:
    return discord.Embed(
        title="? Error",
        description=message,
        colour=COLOR_ERROR,
    )
```

- [ ] **Step 1.4: Run the test to verify it passes**

Run: `python -m pytest tests/test_ui.py::test_build_error_embed_uses_error_palette -v`  
Expected: PASS.

- [ ] **Step 1.5: Commit**

```bash
git add utils/ui.py tests/test_ui.py
git commit -m "add error embed builder"
```

---

### Task 2: `build_info_embed` y `build_warning_embed`

**Files:**
- Modify: `utils/ui.py`
- Modify: `tests/test_ui.py`

- [ ] **Step 2.1: Write the failing tests**

Append to `tests/test_ui.py`:

```python
from utils.ui import COLOR_INFO, COLOR_WARNING, build_info_embed, build_warning_embed


def test_build_warning_embed_uses_warning_palette():
    embed = build_warning_embed("Atento")

    assert embed.title == "?? Aviso"
    assert embed.description == "Atento"
    assert embed.colour.value == COLOR_WARNING


def test_build_info_embed_uses_custom_title():
    embed = build_info_embed("Cola", "Sin canciones")

    assert embed.title == "Cola"
    assert embed.description == "Sin canciones"
    assert embed.colour.value == COLOR_INFO
```

- [ ] **Step 2.2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_ui.py::test_build_warning_embed_uses_warning_palette tests/test_ui.py::test_build_info_embed_uses_custom_title -v`  
Expected: FAIL with `ImportError` or `AttributeError` because the builders do not exist yet.

- [ ] **Step 2.3: Write the minimal implementation**

Update `utils/ui.py`:

```python
def build_warning_embed(message: str) -> discord.Embed:
    return discord.Embed(
        title="?? Aviso",
        description=message,
        colour=COLOR_WARNING,
    )


def build_info_embed(title: str, message: str) -> discord.Embed:
    return discord.Embed(
        title=title,
        description=message,
        colour=COLOR_INFO,
    )
```

- [ ] **Step 2.4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_ui.py::test_build_warning_embed_uses_warning_palette tests/test_ui.py::test_build_info_embed_uses_custom_title -v`  
Expected: 2 PASS.

- [ ] **Step 2.5: Commit**

```bash
git add utils/ui.py tests/test_ui.py
git commit -m "add info and warning embeds"
```

---

### Task 3: `build_now_playing_embed`

**Files:**
- Modify: `utils/ui.py`
- Modify: `tests/test_ui.py`

- [ ] **Step 3.1: Write the failing tests**

Append to `tests/test_ui.py`:

```python
from utils.ui import COLOR_PRIMARY, build_now_playing_embed


def test_build_now_playing_embed_adds_youtube_thumbnail():
    embed = build_now_playing_embed(
        {
            "title": "Cha-La Head-Cha-La",
            "source_url": "https://www.youtube.com/watch?v=YnL70cee6qo",
        }
    )

    assert embed.title == "?? Ahora reproduciendo"
    assert embed.description == "**Cha-La Head-Cha-La**"
    assert embed.colour.value == COLOR_PRIMARY
    assert embed.thumbnail.url == "https://img.youtube.com/vi/YnL70cee6qo/0.jpg"
    assert embed.footer.text.startswith("SSJ Bot � ")


def test_build_now_playing_embed_ignores_url_without_video_id():
    embed = build_now_playing_embed(
        {
            "title": "Unknown",
            "source_url": "https://www.youtube.com/watch",
        }
    )

    assert embed.title == "?? Ahora reproduciendo"
    assert embed.thumbnail.url is None


def test_build_now_playing_embed_ignores_soundcloud_url():
    embed = build_now_playing_embed(
        {
            "title": "Sound",
            "source_url": "https://soundcloud.com/artist/song",
        }
    )

    assert embed.title == "?? Ahora reproduciendo"
    assert embed.thumbnail.url is None
```

- [ ] **Step 3.2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_ui.py -k now_playing -v`  
Expected: FAIL because `build_now_playing_embed` does not exist.

- [ ] **Step 3.3: Write the minimal implementation**

Update `utils/ui.py`:

```python
from __future__ import annotations

import re

import discord

COLOR_PRIMARY = 0x6C3483
COLOR_SUCCESS = 0x2980B9
COLOR_ERROR = 0x922B21
COLOR_WARNING = 0xCA6F1E
COLOR_INFO = 0x2C3E50

BOT_LABEL = "SSJ Bot"
YOUTUBE_VIDEO_RE = re.compile(
    r"(?:youtube\.com/watch\?v=|youtu\.be/)([A-Za-z0-9_-]{11})"
)


def _build_footer_text() -> str:
    return f"{BOT_LABEL} � {discord.utils.utcnow().strftime('%H:%M')}"


def _extract_youtube_video_id(url: str | None) -> str | None:
    if not url:
        return None
    match = YOUTUBE_VIDEO_RE.search(url)
    if match:
        return match.group(1)
    return None


def build_now_playing_embed(song: dict) -> discord.Embed:
    title = song.get("title", "T�tulo desconocido")
    source_url = song.get("source_url") or song.get("webpage_url") or song.get("url")

    embed = discord.Embed(
        title="?? Ahora reproduciendo",
        description=f"**{title}**",
        colour=COLOR_PRIMARY,
    )

    video_id = _extract_youtube_video_id(source_url)
    if video_id:
        embed.set_thumbnail(url=f"https://img.youtube.com/vi/{video_id}/0.jpg")

    duration = song.get("duration")
    if duration:
        embed.add_field(name="Duraci�n", value=str(duration), inline=True)

    embed.set_footer(text=_build_footer_text())
    return embed
```

- [ ] **Step 3.4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_ui.py -k now_playing -v`  
Expected: 3 PASS.

- [ ] **Step 3.5: Commit**

```bash
git add utils/ui.py tests/test_ui.py
git commit -m "add now playing embed builder"
```

---

### Task 4: `build_added_to_queue_embed`

**Files:**
- Modify: `utils/ui.py`
- Modify: `tests/test_ui.py`

- [ ] **Step 4.1: Write the failing test**

Append to `tests/test_ui.py`:

```python
from utils.ui import COLOR_SUCCESS, build_added_to_queue_embed


def test_build_added_to_queue_embed_shows_position():
    embed = build_added_to_queue_embed({"title": "Limit Break x Survivor"}, position=3)

    assert embed.title == "? A�adido a la cola"
    assert embed.description == "Limit Break x Survivor"
    assert embed.colour.value == COLOR_SUCCESS
    assert len(embed.fields) == 1
    assert embed.fields[0].name == "Posici�n en cola"
    assert embed.fields[0].value == "3"
```

- [ ] **Step 4.2: Run the test to verify it fails**

Run: `python -m pytest tests/test_ui.py::test_build_added_to_queue_embed_shows_position -v`  
Expected: FAIL because `build_added_to_queue_embed` does not exist.

- [ ] **Step 4.3: Write the minimal implementation**

Update `utils/ui.py`:

```python
def build_added_to_queue_embed(song: dict, position: int) -> discord.Embed:
    embed = discord.Embed(
        title="? A�adido a la cola",
        description=song.get("title", "T�tulo desconocido"),
        colour=COLOR_SUCCESS,
    )
    embed.add_field(name="Posici�n en cola", value=str(position), inline=True)
    return embed
```

- [ ] **Step 4.4: Run the test to verify it passes**

Run: `python -m pytest tests/test_ui.py::test_build_added_to_queue_embed_shows_position -v`  
Expected: PASS.

- [ ] **Step 4.5: Commit**

```bash
git add utils/ui.py tests/test_ui.py
git commit -m "add queue confirmation embed"
```

---

### Task 5: `build_queue_embed`

**Files:**
- Modify: `utils/ui.py`
- Modify: `tests/test_ui.py`

- [ ] **Step 5.1: Write the failing tests**

Append to `tests/test_ui.py`:

```python
from utils.ui import build_queue_embed


def test_build_queue_embed_handles_empty_queue():
    embed = build_queue_embed([], now_playing="Nada")

    assert embed.title == "?? Cola de reproducci�n"
    assert "? Ahora: Nada" in embed.description
    assert "No hay canciones en cola." in embed.description
    assert embed.footer.text == "P�gina 1/1 � 0 canciones en cola"


def test_build_queue_embed_renders_single_song():
    embed = build_queue_embed(
        [{"title": "Dan Dan Kokoro Hikareteku"}],
        now_playing="Cha-La Head-Cha-La",
    )

    assert "? Ahora: Cha-La Head-Cha-La" in embed.description
    assert "1. Dan Dan Kokoro Hikareteku" in embed.description
    assert embed.footer.text == "P�gina 1/1 � 1 canciones en cola"


def test_build_queue_embed_paginates_results():
    songs = [{"title": f"Song {i}"} for i in range(1, 16)]

    embed = build_queue_embed(songs, now_playing="Song 0", page=2, page_size=10)

    assert "11. Song 11" in embed.description
    assert "15. Song 15" in embed.description
    assert "10. Song 10" not in embed.description
    assert embed.footer.text == "P�gina 2/2 � 15 canciones en cola"
```

- [ ] **Step 5.2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_ui.py -k queue_embed -v`  
Expected: FAIL because `build_queue_embed` does not exist.

- [ ] **Step 5.3: Write the minimal implementation**

Update `utils/ui.py`:

```python
import math


def build_queue_embed(
    songs: list,
    now_playing: str,
    page: int = 1,
    page_size: int = 10,
) -> discord.Embed:
    total = len(songs)
    total_pages = max(1, math.ceil(total / page_size))
    page = max(1, min(page, total_pages))

    start = (page - 1) * page_size
    end = start + page_size
    visible_songs = songs[start:end]

    if visible_songs:
        lines = [
            f"{start + index + 1}. {song['title']}"
            for index, song in enumerate(visible_songs)
        ]
        queue_text = "\n".join(lines)
    else:
        queue_text = "No hay canciones en cola."

    embed = discord.Embed(
        title="?? Cola de reproducci�n",
        description=f"? Ahora: {now_playing}\n\n{queue_text}",
        colour=COLOR_SUCCESS,
    )
    embed.set_footer(text=f"P�gina {page}/{total_pages} � {total} canciones en cola")
    return embed
```

- [ ] **Step 5.4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_ui.py -k queue_embed -v`  
Expected: 3 PASS.

- [ ] **Step 5.5: Commit**

```bash
git add utils/ui.py tests/test_ui.py
git commit -m "add paginated queue embed"
```

---

### Task 6: `build_search_results_embed`

**Files:**
- Modify: `utils/ui.py`
- Modify: `tests/test_ui.py`

- [ ] **Step 6.1: Write the failing tests**

Append to `tests/test_ui.py`:

```python
from utils.ui import build_search_results_embed


def test_build_search_results_embed_lists_titles():
    embed = build_search_results_embed(
        [
            {"title": "Blue Bird"},
            {"title": "Silhouette"},
            {"title": "Haruka Kanata"},
        ]
    )

    assert embed.title == "?? Resultados de b�squeda"
    assert "1. Blue Bird" in embed.description
    assert "2. Silhouette" in embed.description
    assert "3. Haruka Kanata" in embed.description


def test_build_search_results_embed_handles_empty_list():
    embed = build_search_results_embed([])

    assert embed.title == "?? Resultados de b�squeda"
    assert embed.description == "No se encontraron resultados."
```

- [ ] **Step 6.2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_ui.py -k search_results_embed -v`  
Expected: FAIL because `build_search_results_embed` does not exist.

- [ ] **Step 6.3: Write the minimal implementation**

Update `utils/ui.py`:

```python
def build_search_results_embed(results: list) -> discord.Embed:
    if results:
        lines = [
            f"{index + 1}. {result['title']}"
            for index, result in enumerate(results)
        ]
        description = "\n".join(lines)
    else:
        description = "No se encontraron resultados."

    return discord.Embed(
        title="?? Resultados de b�squeda",
        description=description,
        colour=COLOR_PRIMARY,
    )
```

- [ ] **Step 6.4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_ui.py -k search_results_embed -v`  
Expected: 2 PASS.

- [ ] **Step 6.5: Commit**

```bash
git add utils/ui.py tests/test_ui.py
git commit -m "add search results embed"
```

---

### Task 7: `MusicControlView` (clase + botones)

**Files:**
- Modify: `utils/ui.py`
- Create: `tests/test_music_control_view.py`

- [ ] **Step 7.1: Write the failing tests**

Create `tests/test_music_control_view.py`:

```python
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from utils.ui import MusicControlView


def make_interaction():
    interaction = MagicMock()
    interaction.guild = MagicMock()
    interaction.guild.voice_client = MagicMock()
    interaction.response = MagicMock()
    interaction.response.send_message = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    interaction.message = MagicMock()
    interaction.message.edit = AsyncMock()
    return interaction


def make_ctx():
    ctx = MagicMock()
    ctx.guild = MagicMock(id=1)
    ctx.interaction = MagicMock()
    return ctx


def make_music_cog():
    music_cog = MagicMock()
    music_cog._state = MagicMock(
        return_value=MagicMock(queue=[{"title": "Song 1"}], actual_song="Song 0")
    )
    music_cog.update_activity = MagicMock()
    music_cog._cleanup_state = MagicMock()
    return music_cog


def test_music_control_view_has_expected_buttons():
    view = MusicControlView(make_music_cog(), make_ctx())

    custom_ids = [child.custom_id for child in view.children]
    assert custom_ids == ["pause_resume", "skip", "stop", "view_queue"]


@pytest.mark.asyncio
async def test_pause_resume_button_pauses_and_flips_emoji():
    view = MusicControlView(make_music_cog(), make_ctx())
    interaction = make_interaction()
    interaction.guild.voice_client.is_paused.return_value = False
    interaction.guild.voice_client.is_playing.return_value = True

    button = next(child for child in view.children if child.custom_id == "pause_resume")
    await button.callback(interaction)

    interaction.guild.voice_client.pause.assert_called_once()
    assert str(button.emoji) == "??"
    interaction.response.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_stop_button_disables_all_buttons_and_edits_message():
    view = MusicControlView(make_music_cog(), make_ctx())
    interaction = make_interaction()
    interaction.guild.voice_client.is_connected.return_value = True
    interaction.guild.voice_client.is_playing.return_value = True

    button = next(child for child in view.children if child.custom_id == "stop")
    await button.callback(interaction)

    assert all(child.disabled for child in view.children)
    interaction.message.edit.assert_awaited_once()
    interaction.guild.voice_client.disconnect.assert_awaited_once()


@pytest.mark.asyncio
async def test_view_queue_button_sends_ephemeral_embed():
    view = MusicControlView(make_music_cog(), make_ctx())
    interaction = make_interaction()

    button = next(child for child in view.children if child.custom_id == "view_queue")
    await button.callback(interaction)

    _, kwargs = interaction.response.send_message.call_args
    assert kwargs["ephemeral"] is True
    assert kwargs["embed"].title == "?? Cola de reproducci�n"
```

- [ ] **Step 7.2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_music_control_view.py -v`  
Expected: FAIL because `MusicControlView` does not exist.

- [ ] **Step 7.3: Write the minimal implementation**

Append to `utils/ui.py`:

```python
class MusicControlView(discord.ui.View):
    def __init__(self, music_cog, ctx):
        super().__init__(timeout=None)
        self.music_cog = music_cog
        self.ctx = ctx

    @discord.ui.button(
        emoji="?",
        style=discord.ButtonStyle.secondary,
        custom_id="pause_resume",
    )
    async def pause_resume(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        voice_client = interaction.guild.voice_client if interaction.guild else None
        if not voice_client:
            await interaction.response.send_message(
                embed=build_error_embed("No hay reproducci�n activa."),
                ephemeral=True,
            )
            return

        if voice_client.is_paused():
            voice_client.resume()
            button.emoji = "?"
            message = "Se reanud� la reproducci�n."
        elif voice_client.is_playing():
            voice_client.pause()
            button.emoji = "??"
            message = "Se paus� la reproducci�n."
        else:
            await interaction.response.send_message(
                embed=build_error_embed("No hay reproducci�n activa."),
                ephemeral=True,
            )
            return

        self.music_cog.update_activity(self.ctx)
        await interaction.message.edit(view=self)
        await interaction.response.send_message(
            embed=build_info_embed("Control de reproducci�n", message),
            ephemeral=True,
        )

    @discord.ui.button(
        emoji="?",
        style=discord.ButtonStyle.primary,
        custom_id="skip",
    )
    async def skip(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        voice_client = interaction.guild.voice_client if interaction.guild else None
        if not voice_client or not voice_client.is_playing():
            await interaction.response.send_message(
                embed=build_error_embed("No hay nada que skipear."),
                ephemeral=True,
            )
            return

        voice_client.stop()
        self.music_cog.update_activity(self.ctx)
        await interaction.response.send_message(
            embed=build_info_embed("Control de reproducci�n", "Se skipe� la canci�n actual."),
            ephemeral=True,
        )

    @discord.ui.button(
        emoji="?",
        style=discord.ButtonStyle.danger,
        custom_id="stop",
    )
    async def stop(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        voice_client = interaction.guild.voice_client if interaction.guild else None
        if not voice_client:
            await interaction.response.send_message(
                embed=build_error_embed("No hay reproducci�n activa."),
                ephemeral=True,
            )
            return

        state = self.music_cog._state(self.ctx)
        state.queue.clear()

        if voice_client.is_playing() or voice_client.is_paused():
            voice_client.stop()
        if voice_client.is_connected():
            await voice_client.disconnect()

        for child in self.children:
            child.disabled = True

        await interaction.message.edit(
            embed=build_info_embed("? Reproducci�n finalizada", "La reproducci�n se detuvo."),
            view=self,
        )
        await interaction.response.send_message(
            embed=build_info_embed("Control de reproducci�n", "Se detuvo la reproducci�n."),
            ephemeral=True,
        )

        if interaction.guild:
            self.music_cog._cleanup_state(interaction.guild.id)

    @discord.ui.button(
        emoji="??",
        style=discord.ButtonStyle.secondary,
        custom_id="view_queue",
    )
    async def view_queue(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        state = self.music_cog._state(self.ctx)

        if state.queue:
            embed = build_queue_embed(
                state.queue,
                now_playing=state.actual_song or "Nada",
            )
        else:
            embed = build_info_embed(
                "?? Cola de reproducci�n",
                "La cola est� vac�a.",
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)
```

- [ ] **Step 7.4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_music_control_view.py -v`  
Expected: 4 PASS.

- [ ] **Step 7.5: Commit**

```bash
git add utils/ui.py tests/test_music_control_view.py
git commit -m "add music control view"
```

---

### Task 8: A�adir `now_playing_message` a `GuildState`

**Files:**
- Modify: `cogs/music_cog.py`
- Create: `tests/test_guild_state.py`

- [ ] **Step 8.1: Write the failing test**

Create `tests/test_guild_state.py`:

```python
from cogs.music_cog import GuildState


def test_guild_state_starts_without_now_playing_message():
    state = GuildState()

    assert state.now_playing_message is None
```

- [ ] **Step 8.2: Run the test to verify it fails**

Run: `python -m pytest tests/test_guild_state.py -v`  
Expected: FAIL with `AttributeError: 'GuildState' object has no attribute 'now_playing_message'`.

- [ ] **Step 8.3: Write the minimal implementation**

Update `cogs/music_cog.py` in `GuildState`:

```python
class GuildState:
    """Per-guild music state. One instance per Discord server."""

    __slots__ = (
        "queue",
        "actual_song",
        "last_activity",
        "inactivity_warned",
        "inactivity_channel",
        "now_playing_message",
    )

    def __init__(self) -> None:
        self.queue: list[dict] = []
        self.actual_song: str | None = None
        self.last_activity: float = time()
        self.inactivity_warned: bool = False
        self.inactivity_channel: discord.TextChannel | None = None
        self.now_playing_message: discord.Message | None = None
```

- [ ] **Step 8.4: Run the test to verify it passes**

Run: `python -m pytest tests/test_guild_state.py -v`  
Expected: PASS.

- [ ] **Step 8.5: Commit**

```bash
git add cogs/music_cog.py tests/test_guild_state.py
git commit -m "track now playing message state"
```

---

### Task 9: Integrar embeds en `music_cog.py` - mensajes de reproducci�n

**Files:**
- Modify: `cogs/music_cog.py:242-297`
- Create: `tests/test_now_playing_flow.py`

- [ ] **Step 9.1: Write the failing tests**

Create `tests/test_now_playing_flow.py`:

```python
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cogs.music_cog import Music
from utils.ui import MusicControlView


@pytest.mark.asyncio
async def test_play_next_sends_now_playing_message_when_missing():
    cog = Music.__new__(Music)
    cog.bot = MagicMock()
    cog.bot.loop = MagicMock()
    cog.states = {}
    cog.update_activity = MagicMock()

    ctx = MagicMock()
    ctx.guild = MagicMock(id=1)
    ctx.voice_client = MagicMock()
    ctx.voice_client.is_connected.return_value = True
    ctx.voice_client.play = MagicMock()
    ctx.send = AsyncMock(return_value=MagicMock())

    state = cog._state(ctx)
    state.queue = [
        {
            "title": "Cha-La Head-Cha-La",
            "url": "https://stream.example/audio",
            "source_url": "https://www.youtube.com/watch?v=YnL70cee6qo",
            "headers": {},
        }
    ]

    with patch("cogs.music_cog.discord.FFmpegOpusAudio", return_value=MagicMock()):
        await cog.play_next_in_queue(ctx)

    _, kwargs = ctx.send.call_args
    assert kwargs["embed"].title == "?? Ahora reproduciendo"
    assert isinstance(kwargs["view"], MusicControlView)
    assert state.now_playing_message is ctx.send.return_value


@pytest.mark.asyncio
async def test_play_next_edits_existing_now_playing_message():
    cog = Music.__new__(Music)
    cog.bot = MagicMock()
    cog.bot.loop = MagicMock()
    cog.states = {}
    cog.update_activity = MagicMock()

    ctx = MagicMock()
    ctx.guild = MagicMock(id=1)
    ctx.voice_client = MagicMock()
    ctx.voice_client.is_connected.return_value = True
    ctx.voice_client.play = MagicMock()
    ctx.send = AsyncMock()

    state = cog._state(ctx)
    state.now_playing_message = MagicMock()
    state.now_playing_message.edit = AsyncMock()
    state.queue = [
        {
            "title": "Dan Dan Kokoro Hikareteku",
            "url": "https://stream.example/audio-2",
            "source_url": "https://www.youtube.com/watch?v=5LVcwPrfNo4",
            "headers": {},
        }
    ]

    with patch("cogs.music_cog.discord.FFmpegOpusAudio", return_value=MagicMock()):
        await cog.play_next_in_queue(ctx)

    state.now_playing_message.edit.assert_awaited_once()
    ctx.send.assert_not_awaited()
```

- [ ] **Step 9.2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_now_playing_flow.py -v`  
Expected: FAIL because `play_next_in_queue()` still uses plain `ctx.send()` and never edits `now_playing_message`.

- [ ] **Step 9.3: Write the minimal implementation**

Update imports at top of `cogs/music_cog.py`:

```python
from utils.ui import (
    MusicControlView,
    build_error_embed,
    build_info_embed,
    build_now_playing_embed,
)
```

Add private helpers inside `Music` before `play_next_in_queue()`:

```python
    async def _send_embed(self, ctx, embed: discord.Embed, *, ephemeral: bool = False):
        if ephemeral and ctx.interaction is not None:
            return await ctx.send(embed=embed, ephemeral=True)
        return await ctx.send(embed=embed)

    async def _publish_now_playing(self, ctx, song: dict):
        s = self._state(ctx)
        embed = build_now_playing_embed(song)
        view = MusicControlView(self, ctx)

        if s.now_playing_message is not None:
            try:
                await s.now_playing_message.edit(embed=embed, view=view)
                return s.now_playing_message
            except (discord.NotFound, discord.HTTPException):
                s.now_playing_message = None

        s.now_playing_message = await ctx.send(embed=embed, view=view)
        return s.now_playing_message

    async def _finalize_now_playing(self, ctx, message: str):
        s = self._state(ctx)
        s.actual_song = None

        if s.now_playing_message is None:
            return

        view = MusicControlView(self, ctx)
        for child in view.children:
            child.disabled = True

        try:
            await s.now_playing_message.edit(
                embed=build_info_embed("? Reproducci�n finalizada", message),
                view=view,
            )
        except (discord.NotFound, discord.HTTPException):
            pass
```

Update `play_next_in_queue()`:

```python
    async def play_next_in_queue(self, ctx):
        s = self._state(ctx)
        logger.debug(
            f"play_next_in_queue llamado en guild={ctx.guild.id}, canciones en cola: {len(s.queue)}"
        )

        if len(s.queue) == 0:
            await self._finalize_now_playing(ctx, "La cola termin�.")
            return

        if not ctx.voice_client or not ctx.voice_client.is_connected():
            logger.error("voice_client no est� conectado en play_next_in_queue")
            await self._send_embed(
                ctx,
                build_error_embed("El bot no est� conectado a un canal de voz."),
            )
            return

        song = s.queue.pop(0)
        s.actual_song = song["title"]

        try:
            before_options = self._build_before_options(song.get("headers"))
            source = discord.FFmpegOpusAudio(
                song["url"],
                before_options=before_options,
                options=FFMPEG_OPTIONS["options"],
            )
            ctx.voice_client.play(
                source,
                after=lambda e: self.bot.loop.create_task(
                    self._after_play(ctx, e, song["title"])
                ),
            )
            await self._publish_now_playing(ctx, song)
            self.update_activity(ctx)
        except Exception as e:
            logger.error(f"Exception en play_next_in_queue: {type(e).__name__}: {e}")
            logger.error(traceback.format_exc())
            await self._send_embed(
                ctx,
                build_error_embed(
                    f"Error al reproducir **{song['title']}**. Intentando con la siguiente canci�n..."
                ),
            )
            await self.play_next_in_queue(ctx)
```

- [ ] **Step 9.4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_now_playing_flow.py -v`  
Expected: 2 PASS.

- [ ] **Step 9.5: Commit**

```bash
git add cogs/music_cog.py tests/test_now_playing_flow.py
git commit -m "add now playing embed lifecycle"
```

---

### Task 10: Integrar embeds en `music_cog.py` - a�adir a cola, queue, search

**Files:**
- Modify: `cogs/music_cog.py:427-577`
- Modify: `cogs/music_cog.py:621-631`
- Modify: `cogs/music_cog.py:765-889`
- Modify: `tests/test_search_view_ephemeral.py`
- Create: `tests/test_visual_command_embeds.py`

- [ ] **Step 10.1: Write the failing tests**

Create `tests/test_visual_command_embeds.py`:

```python
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cogs.music_cog import Music, SearchSelect


@pytest.mark.asyncio
async def test_play_internal_sends_added_to_queue_embed():
    cog = Music.__new__(Music)
    cog.states = {}
    cog.update_activity = MagicMock()
    cog.start_inactivity_check = MagicMock()
    cog.join_voice_channel = AsyncMock(return_value=True)

    ctx = MagicMock()
    ctx.guild = MagicMock(id=1)
    ctx.voice_client = MagicMock()
    ctx.voice_client.is_connected.return_value = True
    ctx.voice_client.is_playing.return_value = True
    ctx.send = AsyncMock()
    ctx.typing = MagicMock()
    ctx.typing.return_value.__aenter__ = AsyncMock()
    ctx.typing.return_value.__aexit__ = AsyncMock()

    info = {
        "url": "https://stream.example/audio",
        "title": "Blue Bird",
        "webpage_url": "https://www.youtube.com/watch?v=abc123def45",
        "http_headers": {},
    }

    with patch("cogs.music_cog.SafeYoutubeDL") as ydl_class:
        ydl = MagicMock()
        ydl_class.return_value.__enter__ = MagicMock(return_value=ydl)
        ydl_class.return_value.__exit__ = MagicMock(return_value=False)
        cog._extract_info = AsyncMock(return_value=info)
        cog._extract_http_headers = MagicMock(return_value={})

        await cog._play_internal(ctx, "https://www.youtube.com/watch?v=abc123def45")

    _, kwargs = ctx.send.call_args
    assert kwargs["embed"].title == "? A�adido a la cola"
    assert cog._state(ctx).queue[0]["source_url"] == info["webpage_url"]


@pytest.mark.asyncio
async def test_queue_command_sends_queue_embed():
    cog = Music.__new__(Music)
    cog.states = {}
    cog.update_activity = MagicMock()

    ctx = MagicMock()
    ctx.guild = MagicMock(id=1)
    ctx.send = AsyncMock()

    state = cog._state(ctx)
    state.actual_song = "Song 0"
    state.queue = [{"title": "Song 1"}, {"title": "Song 2"}]

    await cog.queue.callback(cog, ctx)

    _, kwargs = ctx.send.call_args
    assert kwargs["embed"].title == "?? Cola de reproducci�n"


@pytest.mark.asyncio
async def test_search_select_sends_added_to_queue_embed():
    entries = [{"title": "Song A", "id": "abc123def45"}]

    music_cog = MagicMock()
    music_cog._extract_info = AsyncMock(
        return_value={"url": "https://stream.url", "http_headers": {}}
    )
    music_cog._extract_http_headers = MagicMock(return_value={})
    music_cog._state = MagicMock(return_value=MagicMock(queue=[]))
    music_cog.update_activity = MagicMock()
    music_cog.join_voice_channel = AsyncMock()
    music_cog.play_next_in_queue = AsyncMock()

    ctx = MagicMock()
    ctx.voice_client = MagicMock()
    ctx.voice_client.is_connected = MagicMock(return_value=True)
    ctx.voice_client.is_playing = MagicMock(return_value=False)

    select = SearchSelect(entries, music_cog, ctx)
    select._values = ["0"]

    interaction = MagicMock()
    interaction.response = MagicMock()
    interaction.response.send_message = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    interaction.message = MagicMock()
    interaction.message.delete = AsyncMock()

    with patch("cogs.music_cog.SafeYoutubeDL") as ydl_class:
        ydl_instance = MagicMock()
        ydl_class.return_value.__enter__ = MagicMock(return_value=ydl_instance)
        ydl_class.return_value.__exit__ = MagicMock(return_value=False)
        with patch.object(
            type(select), "view", new_callable=lambda: property(lambda self: MagicMock(stop=MagicMock()))
        ):
            await select.callback(interaction)

    _, kwargs = interaction.response.send_message.call_args
    assert kwargs["embed"].title == "? A�adido a la cola"
```

Update `tests/test_search_view_ephemeral.py` to assert embed exists:

```python
    _, kwargs = ctx.send.call_args
    assert kwargs.get("ephemeral") is True
    assert kwargs["embed"].title == "?? Resultados de b�squeda"
```

and:

```python
    _, kwargs = ctx.send.call_args
    assert kwargs.get("ephemeral") is False
    assert kwargs["embed"].title == "?? Resultados de b�squeda"
```

- [ ] **Step 10.2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_visual_command_embeds.py tests/test_search_view_ephemeral.py -v`  
Expected: FAIL because the command paths still send text or send view without embed.

- [ ] **Step 10.3: Write the minimal implementation**

Update imports in `cogs/music_cog.py`:

```python
from utils.ui import (
    MusicControlView,
    build_added_to_queue_embed,
    build_error_embed,
    build_info_embed,
    build_now_playing_embed,
    build_queue_embed,
    build_search_results_embed,
    build_warning_embed,
)
```

Update queue append path in `_play_internal()`:

```python
                        source_url = info.get("webpage_url") or search

                        self._state(ctx).queue.append(
                            {
                                "title": title,
                                "url": url,
                                "source_url": source_url,
                                "headers": headers,
                            }
                        )
                        if not silent:
                            await self._send_embed(
                                ctx,
                                build_added_to_queue_embed(
                                    {"title": title},
                                    position=len(self._state(ctx).queue),
                                ),
                            )
```

Update `queue()`:

```python
    @commands.hybrid_command(name="queue", description="Displays the current song queue.")
    async def queue(self, ctx: commands.Context):
        s = self._state(ctx)

        if s.queue:
            embed = build_queue_embed(
                s.queue,
                now_playing=s.actual_song or "Nada",
            )
        else:
            embed = build_info_embed("?? Cola de reproducci�n", "La cola est� vac�a.")

        await self._send_embed(ctx, embed)
        self.update_activity(ctx)
```

Update `search()`:

```python
    @commands.hybrid_command(name="search", description="Searches for a song on YouTube.")
    async def search(self, ctx: commands.Context, *, query: str):
        logger.info(
            "search invoked by %s in guild %s: query=%r",
            ctx.author, ctx.guild.id if ctx.guild else None, query,
        )
        await ctx.defer(ephemeral=ctx.interaction is not None)
        search_options = YTDL_OPTIONS.copy()
        search_options.pop("playlist_items", None)
        search_options["extract_flat"] = True

        entries = []

        async with ctx.typing():
            with SafeYoutubeDL(search_options) as ydl:
                try:
                    info = await self._extract_info(ydl, f"ytsearch5:{query}", download=False)
                    entries = info.get("entries", [])
                except Exception as e:
                    await self._send_embed(
                        ctx,
                        build_error_embed("Ocurri� un error al buscar la canci�n."),
                    )
                    logger.error(f"Error en search: {e}")

        if not entries:
            await self._send_embed(
                ctx,
                build_info_embed("?? Resultados de b�squeda", "No se encontraron resultados."),
            )
            return

        view = SearchView(entries, self, ctx)
        await ctx.send(
            embed=build_search_results_embed(entries),
            view=view,
            ephemeral=ctx.interaction is not None,
        )
        self.update_activity(ctx)
```

Update `SearchSelect.callback()`:

```python
        source_url = f"https://www.youtube.com/watch?v={video_id}"
        self.music_cog._state(self.ctx).queue.append(
            {
                "title": title,
                "url": full_url,
                "source_url": source_url,
                "headers": headers,
            }
        )
        await interaction.response.send_message(
            embed=build_added_to_queue_embed(
                {"title": title},
                position=len(self.music_cog._state(self.ctx).queue),
            )
        )
```

- [ ] **Step 10.4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_visual_command_embeds.py tests/test_search_view_ephemeral.py -v`  
Expected: all PASS.

- [ ] **Step 10.5: Commit**

```bash
git add cogs/music_cog.py tests/test_visual_command_embeds.py tests/test_search_view_ephemeral.py
git commit -m "replace queue and search texts"
```

---

### Task 11: Integrar embeds en `music_cog.py` - errores e inactividad

**Files:**
- Modify: `cogs/music_cog.py`
- Modify: `tests/test_skip_pause_resume_feedback.py`
- Create: `tests/test_inactivity_embeds.py`

- [ ] **Step 11.1: Write the failing tests**

Replace `tests/test_skip_pause_resume_feedback.py` asserts with embed-aware assertions:

```python
"""Tests for skip/pause/resume providing feedback when no-op."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from cogs.music_cog import Music


@pytest.mark.asyncio
async def test_skip_sends_feedback_when_no_voice_client():
    cog = Music.__new__(Music)
    cog.update_activity = MagicMock()

    ctx = MagicMock()
    ctx.interaction = None
    ctx.voice_client = None
    ctx.send = AsyncMock()

    await cog.skip.callback(cog, ctx)

    _, kwargs = ctx.send.call_args
    assert kwargs["embed"].description == "No hay nada que skipear."


@pytest.mark.asyncio
async def test_skip_sends_feedback_when_not_playing():
    cog = Music.__new__(Music)
    cog.update_activity = MagicMock()

    ctx = MagicMock()
    ctx.interaction = None
    ctx.voice_client = MagicMock()
    ctx.voice_client.is_playing = MagicMock(return_value=False)
    ctx.send = AsyncMock()

    await cog.skip.callback(cog, ctx)

    _, kwargs = ctx.send.call_args
    assert kwargs["embed"].description == "No hay nada que skipear."


@pytest.mark.asyncio
async def test_pause_sends_feedback_when_no_voice_client():
    cog = Music.__new__(Music)
    cog.update_activity = MagicMock()

    ctx = MagicMock()
    ctx.interaction = None
    ctx.voice_client = None
    ctx.send = AsyncMock()

    await cog.pause.callback(cog, ctx)

    _, kwargs = ctx.send.call_args
    assert kwargs["embed"].description == "No hay nada reproduci�ndose para pausar."


@pytest.mark.asyncio
async def test_resume_sends_feedback_when_not_paused():
    cog = Music.__new__(Music)
    cog.update_activity = MagicMock()

    ctx = MagicMock()
    ctx.interaction = None
    ctx.voice_client = MagicMock()
    ctx.voice_client.is_paused = MagicMock(return_value=False)
    ctx.send = AsyncMock()

    await cog.resume.callback(cog, ctx)

    _, kwargs = ctx.send.call_args
    assert kwargs["embed"].description == "No hay nada pausado para reanudar."
```

Create `tests/test_inactivity_embeds.py`:

```python
from time import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from cogs.music_cog import GuildState, Music


@pytest.mark.asyncio
async def test_check_inactivity_sends_warning_embed():
    cog = Music.__new__(Music)
    cog.states = {}

    guild = MagicMock(id=1)
    channel = MagicMock()
    channel.members = [MagicMock(bot=False)]
    voice_client = MagicMock()
    voice_client.is_connected.return_value = True
    voice_client.is_playing.return_value = False
    voice_client.is_paused.return_value = False
    voice_client.channel = channel

    cog.bot = MagicMock()
    cog.bot.get_guild = MagicMock(return_value=guild)
    cog.bot.voice_clients = [voice_client]

    state = GuildState()
    state.last_activity = time() - 241
    state.inactivity_channel = MagicMock()
    state.inactivity_channel.send = AsyncMock()
    cog.states[guild.id] = state

    await cog.check_inactivity.coro(cog)

    _, kwargs = state.inactivity_channel.send.call_args
    assert kwargs["embed"].title == "?? Aviso"
```

- [ ] **Step 11.2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_skip_pause_resume_feedback.py tests/test_inactivity_embeds.py -v`  
Expected: FAIL because command callbacks and inactivity loop still send plain strings.

- [ ] **Step 11.3: Write the minimal implementation**

Update command feedback in `cogs/music_cog.py`:

```python
    @commands.hybrid_command(name="stop", description="Stops playback and leaves the voice channel.")
    async def stop(self, ctx: commands.Context):
        if not ctx.voice_client:
            await self._send_embed(
                ctx,
                build_error_embed("No hay reproducci�n activa."),
                ephemeral=ctx.interaction is not None,
            )
            return

        s = self._state(ctx)
        s.queue.clear()
        ctx.voice_client.stop()
        await ctx.voice_client.disconnect()
        await self._finalize_now_playing(ctx, "La reproducci�n se detuvo.")
        await self._send_embed(
            ctx,
            build_info_embed("Control de reproducci�n", "Reproducci�n detenida."),
            ephemeral=ctx.interaction is not None,
        )
        self._cleanup_state(ctx.guild.id)

    @commands.hybrid_command(name="skip", description="Skips the current song.")
    async def skip(self, ctx: commands.Context):
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.stop()
            await self._send_embed(
                ctx,
                build_info_embed("Control de reproducci�n", "Se skipe� la canci�n actual."),
                ephemeral=ctx.interaction is not None,
            )
            self.update_activity(ctx)
        else:
            await self._send_embed(
                ctx,
                build_error_embed("No hay nada que skipear."),
                ephemeral=ctx.interaction is not None,
            )

    @commands.hybrid_command(name="pause", description="Pauses the current song.")
    async def pause(self, ctx: commands.Context):
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.pause()
            await self._send_embed(
                ctx,
                build_info_embed("Control de reproducci�n", "Se ha pausado la reproducci�n."),
                ephemeral=ctx.interaction is not None,
            )
            self.update_activity(ctx)
        else:
            await self._send_embed(
                ctx,
                build_error_embed("No hay nada reproduci�ndose para pausar."),
                ephemeral=ctx.interaction is not None,
            )

    @commands.hybrid_command(name="resume", description="Resumes the paused song.")
    async def resume(self, ctx: commands.Context):
        if ctx.voice_client and ctx.voice_client.is_paused():
            ctx.voice_client.resume()
            await self._send_embed(
                ctx,
                build_info_embed("Control de reproducci�n", "Se ha reanudado la reproducci�n."),
                ephemeral=ctx.interaction is not None,
            )
            self.update_activity(ctx)
        else:
            await self._send_embed(
                ctx,
                build_error_embed("No hay nada pausado para reanudar."),
                ephemeral=ctx.interaction is not None,
            )
```

Replace plain-string error paths in `cogs/music_cog.py` with embeds, specifically:
- `cog_check()`
- `join_voice_channel()`
- `play_playlist()`
- `_play_internal()` no-results / processing-errors
- `SearchSelect.callback()` error responses
- inactivity sends in `check_inactivity()`

Example replacements:

```python
await self._send_embed(
    ctx,
    build_error_embed("Los comandos de m�sica solo funcionan en servidores."),
)
```

```python
await s.inactivity_channel.send(
    embed=build_warning_embed(
        f"El bot se desconectar� en {remaining_time} segundos por inactividad. Usa cualquier comando de m�sica para mantener la conexi�n."
    )
)
```

```python
await s.inactivity_channel.send(
    embed=build_warning_embed("Desconectado por inactividad.")
)
```

```python
await s.inactivity_channel.send(
    embed=build_warning_embed("Desconectado porque no hay usuarios en el canal.")
)
```

- [ ] **Step 11.4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_skip_pause_resume_feedback.py tests/test_inactivity_embeds.py -v`  
Expected: all PASS.

- [ ] **Step 11.5: Commit**

```bash
git add cogs/music_cog.py tests/test_skip_pause_resume_feedback.py tests/test_inactivity_embeds.py
git commit -m "convert error and inactivity messages"
```

---

### Task 12: `bot.py` - manejador de errores global con embeds

**Files:**
- Modify: `bot.py`
- Modify: `tests/test_command_not_found_handler.py`
- Create: `tests/test_bot_error_embeds.py`

- [ ] **Step 12.1: Write the failing tests**

Create `tests/test_bot_error_embeds.py`:

```python
from unittest.mock import AsyncMock, MagicMock

import pytest
from discord import app_commands

from bot import on_app_command_error


@pytest.mark.asyncio
async def test_app_command_error_sends_embed():
    interaction = MagicMock()
    interaction.command = MagicMock(name="play")
    interaction.response = MagicMock()
    interaction.response.is_done.return_value = False
    interaction.response.send_message = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()

    await on_app_command_error(interaction, app_commands.AppCommandError("boom"))

    _, kwargs = interaction.response.send_message.call_args
    assert kwargs["ephemeral"] is True
    assert kwargs["embed"].title == "? Error"
```

Update `tests/test_command_not_found_handler.py`:

```python
"""Tests for global on_command_error handler silencing CommandNotFound."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from discord.ext import commands

from bot import handle_command_error


@pytest.mark.asyncio
async def test_command_not_found_is_silenced():
    ctx = MagicMock()
    ctx.send = AsyncMock()
    error = commands.CommandNotFound('Command "d" is not found')

    await handle_command_error(ctx, error)

    ctx.send.assert_not_called()


@pytest.mark.asyncio
async def test_other_errors_send_embed_feedback():
    ctx = MagicMock()
    ctx.send = AsyncMock()
    error = commands.CommandInvokeError(RuntimeError("boom"))

    await handle_command_error(ctx, error)

    _, kwargs = ctx.send.call_args
    assert kwargs["embed"].title == "? Error"
```

- [ ] **Step 12.2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_command_not_found_handler.py tests/test_bot_error_embeds.py -v`  
Expected: FAIL because handlers still send plain text or re-raise.

- [ ] **Step 12.3: Write the minimal implementation**

Update `bot.py` imports:

```python
from utils.ui import build_error_embed
```

Update `on_app_command_error()`:

```python
@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError,
):
    logger.error(
        "Error en slash command %s: %s",
        interaction.command.name if interaction.command else "?",
        error,
        exc_info=True,
    )
    embed = build_error_embed("Ocurri� un error inesperado.")
    try:
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)
    except Exception as e:
        logger.error("No pude enviar mensaje de error al usuario: %s", e)
```

Update `handle_command_error()`:

```python
async def handle_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return

    logger.error("Error en comando tradicional: %s", error, exc_info=True)
    await ctx.send(embed=build_error_embed("Ocurri� un error inesperado."))
```

- [ ] **Step 12.4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_command_not_found_handler.py tests/test_bot_error_embeds.py -v`  
Expected: all PASS.

- [ ] **Step 12.5: Commit**

```bash
git add bot.py tests/test_command_not_found_handler.py tests/test_bot_error_embeds.py
git commit -m "use embeds in error handlers"
```

---

### Task 13: Verificaci�n final

**Files:**
- No code changes expected

- [ ] **Step 13.1: Run the targeted visual-message suite**

Run:

```bash
python -m pytest tests/test_ui.py tests/test_music_control_view.py tests/test_guild_state.py tests/test_now_playing_flow.py tests/test_visual_command_embeds.py tests/test_inactivity_embeds.py tests/test_bot_error_embeds.py tests/test_skip_pause_resume_feedback.py tests/test_search_view_ephemeral.py tests/test_search_select_stop.py tests/test_command_not_found_handler.py -v
```

Expected:
- All listed tests PASS
- No `FAIL`, `ERROR` or `XPASS`

- [ ] **Step 13.2: Run the full test suite**

Run:

```bash
python -m pytest -q
```

Expected:
- Entire suite in `tests/` passes
- Output ends with `passed`
- No regressions in pre-existing tests

- [ ] **Step 13.3: Check for syntax/import regressions**

Run:

```bash
python -m compileall bot.py cogs utils tests
```

Expected:
- No `SyntaxError`
- No import-time failures

- [ ] **Step 13.4: Lint only if a real project linter exists**

Check repo configuration first:
- `requirements-dev.txt` only contains `pytest` and `pytest-asyncio`
- no `pyproject.toml`
- no `ruff.toml`
- no configured lint command discovered in repo root

Expected:
- **Skip lint step intentionally**
- Do **not** invent `ruff`/`flake8` commands for this repo

- [ ] **Step 13.5: Final git review before any PR**

Run:

```bash
git status
git diff -- utils/ui.py cogs/music_cog.py bot.py tests
```

Expected:
- Only intended visual-message files changed
- No accidental edits under `venv/`, `.env`, cache files, or unrelated docs

---

## Riesgos y mitigaciones

- **`song["url"]` no sirve para thumbnail** - mitigar guardando `source_url` al encolar y usando fallback `source_url -> webpage_url -> url` en `build_now_playing_embed`.
- **Editar `now_playing_message` puede fallar si el mensaje fue borrado** - mitigar capturando `discord.NotFound`/`discord.HTTPException` y reenviando un mensaje nuevo.
- **`GuildState` usa `__slots__`** - mitigar a�adiendo `now_playing_message` tanto a `__slots__` como a `__init__`.
- **Los botones pueden quedar activos despu�s de `stop` o al vaciar cola** - mitigar centralizando `_finalize_now_playing()` y deshabilitando todos los hijos del `MusicControlView`.
- **Los comandos h�bridos no siempre aceptan `ephemeral=True`** - mitigar pasando `ephemeral` solo cuando `ctx.interaction is not None` desde `_send_embed()`.
- **El loop `check_inactivity` es dif�cil de testear** - mitigar invocando `cog.check_inactivity.coro(cog)` con mocks controlados en unit tests.

## Tests recomendados

- `tests/test_ui.py`
  - builders b�sicos (`error`, `warning`, `info`)
  - thumbnails YouTube v�lidos/inv�lidos
  - queue vac�a / 1 elemento / paginaci�n
  - search results
- `tests/test_music_control_view.py`
  - estructura de botones
  - pausa/reanudar cambia emoji
  - `stop` deshabilita todos
  - `view_queue` responde ephemeral
- `tests/test_guild_state.py`
  - `now_playing_message` inicializa en `None`
- `tests/test_now_playing_flow.py`
  - primer env�o crea mensaje
  - siguiente canci�n edita mensaje existente
- `tests/test_visual_command_embeds.py`
  - `_play_internal` usa `build_added_to_queue_embed`
  - `queue` usa `build_queue_embed`
  - `SearchSelect` usa `build_added_to_queue_embed`
- `tests/test_inactivity_embeds.py`
  - warning de inactividad usa `build_warning_embed`
- `tests/test_bot_error_embeds.py`
  - slash handler global usa embed
- `tests/test_skip_pause_resume_feedback.py`
  - no-op feedback ahora usa embeds
- `tests/test_search_view_ephemeral.py`
  - `/search` sigue respetando `ephemeral`
  - adem�s manda embed junto al `SearchView`

## Verificaci�n final

- `python -m pytest -q`
- `python -m compileall bot.py cogs utils tests`
- `git status`
- `git diff -- utils/ui.py cogs/music_cog.py bot.py tests`

## Fuera de alcance (lo que este plan NO cubre)

- Paginaci�n interactiva de la cola con botones Anterior/Siguiente
- Refactor completo de `SearchView`/`SearchSelect` hacia `utils/ui.py`
- Internacionalizaci�n de mensajes
- Temas visuales configurables por servidor
- Reescritura del flujo de reproducci�n o de extracci�n yt-dlp
