# Plan: Search Fallback Skip All DownloadErrors

**Spec:** `docs/superpowers/specs/2026-04-27-search-fallback-skip-errors-design.md`
**Branch:** `fix/search-fallback-skip-errors`
**Base:** `develop` @ `a6bb344`

## Tasks

### Task 1: TDD red — escribir test del helper

**Goal:** Test que falle contra el código actual (sin helper) y que defina
el contrato del nuevo `_select_first_playable_candidate`.

**Files:**
- Crear `tests/test_select_candidate.py`.

**Test:**

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
import yt_dlp
from cogs.music_cog import Music


@pytest.mark.asyncio
async def test_skips_unavailable_and_returns_next():
    bot = MagicMock()
    music = Music(bot)
    music._extract_info = AsyncMock(
        side_effect=[
            yt_dlp.utils.DownloadError("Video unavailable"),
            {"url": "https://ok", "title": "OK"},
        ]
    )
    ydl = MagicMock()
    entries = [{"id": "BAD"}, {"id": "GOOD"}]

    result = await music._select_first_playable_candidate(ydl, entries)

    assert result == {"url": "https://ok", "title": "OK"}
    assert music._extract_info.call_count == 2
```

**Verification:**

```
python -m pytest tests/test_select_candidate.py -v
```

Debe fallar con `AttributeError: 'Music' object has no attribute
'_select_first_playable_candidate'`.

**Commit:** `add select-candidate helper test`

---

### Task 2: GREEN — implementar helper y refactorizar callsite

**Goal:** Crear el helper `_select_first_playable_candidate` y reemplazar
el loop inline en `play()`.

**Files:**
- `cogs/music_cog.py`.

**Cambios:**

1. Agregar método `_select_first_playable_candidate` cerca de
   `_extract_info` (búsqueda: la clase `Music`, después de
   `_extract_info`):

```python
async def _select_first_playable_candidate(self, ydl, entries):
    for entry in entries:
        video_id = entry.get("id") or entry.get("url")
        if not video_id:
            continue
        candidate_url = f"https://www.youtube.com/watch?v={video_id}"
        try:
            return await self._extract_info(ydl, candidate_url, download=False)
        except yt_dlp.utils.DownloadError as e:
            reason = str(e)[:200]
            logger.warning(
                f"Candidato {video_id} no disponible, probando otro: {reason}"
            )
            continue
    return None
```

2. Reemplazar el loop inline (`cogs/music_cog.py:479-498`):

   **Antes:**

   ```python
   info = None
   for entry in entries:
       video_id = entry.get("id") or entry.get("url")
       if not video_id:
           continue
       candidate_url = (
           f"https://www.youtube.com/watch?v={video_id}"
       )
       try:
           info = await self._extract_info(
               ydl, candidate_url, download=False
           )
           break
       except yt_dlp.utils.DownloadError as e:
           if "Requested format is not available" in str(e):
               logger.warning(
                   f"Format no disponible para {video_id}, probando otro resultado"
               )
               continue
           raise
   ```

   **Después:**

   ```python
   info = await self._select_first_playable_candidate(ydl, entries)
   ```

**Verification:**

```
python -m pytest -v
```

Debe pasar 6/6 (5 anteriores + 1 nuevo).

**Commit:** `add _select_first_playable_candidate helper`

---

### Task 3: Smoke test manual

**Goal:** Confirmar en bot real que `!play d4vd` ya no aborta.

**Steps:**

1. Activar venv, lanzar bot en background con `Start-Process` redirigiendo a
   `bot.log`/`bot.err.log`.
2. Esperar al "Bot online" en log.
3. En Discord: `!play d4vd`.
4. Verificar:
   - Bot reproduce algún resultado (no necesariamente d4vd específico, mientras
     no aborte el comando).
   - `bot.log` contiene `Candidato <id> no disponible, probando otro: ...` si
     algún candidato fue skipeado.
   - `bot.err.log` no muestra excepción no manejada de "Video unavailable".
5. Detener bot.

**Verification:** Reproducción exitosa + warnings esperados en log.

**Commit:** ninguno (sin cambios de código).

## Acceptance Criteria

- Tests: 6/6 passing.
- Smoke test confirma comportamiento.
- Loop inline reemplazado por una sola línea en `play()`.

## Out of Scope

- Filtrado pre-loop de entries no-video.
- Tests adicionales (todos-fallan, sin-entries-válidos).
- Mejorar el mensaje de usuario cuando todos fallan.
