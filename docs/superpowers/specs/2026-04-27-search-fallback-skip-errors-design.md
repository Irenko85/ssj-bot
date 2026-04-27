# Search Fallback: Skip All DownloadErrors

**Date:** 2026-04-27
**Branch:** `fix/search-fallback-skip-errors`
**Type:** Bugfix

## Problem

Cuando el usuario ejecuta `!play <query>` (input no-URL), el bot hace
`ytsearch5:<query>` con `extract_flat=True` y obtiene hasta 5 entries.
Itera construyendo `https://www.youtube.com/watch?v={video_id}` y llama
`_extract_info` por cada candidato hasta que uno funcione.

El bloque `except` actual (`cogs/music_cog.py:492-498`) solo trata como
recuperable el error `"Requested format is not available"`. Cualquier otro
`DownloadError` (ej. `"Video unavailable"`, `"Private video"`,
`"This video has been removed"`) hace `raise`, abortando todo el comando.

**Caso real observado:** `!play d4vd` → primer entry tenía `id` =
`UC98WsFnuhf` (un channel ID, no un video ID). `_extract_info` falla con
`"Video unavailable"` → el comando aborta sin probar los otros 4 candidatos.

## Goal

El loop de búsqueda debe continuar al siguiente candidato ante **cualquier**
`yt_dlp.utils.DownloadError`, no solo "Requested format is not available".
Si todos los candidatos fallan, mostrar el mensaje de error existente al
usuario.

## Non-Goals

- No filtrar entries no-video antes del loop (sería más preciso pero
  requiere identificar campos confiables de yt-dlp; YAGNI por ahora).
- No cambiar el límite `ytsearch5:` ni el orden de candidatos.
- No tocar el path de URL directa (líneas 449-464).

## Approach

### Refactor mínimo para testabilidad

El loop está embebido dentro de `play()`, una función de ~150 líneas con
mucho contexto (`ctx`, `voice_client`, `SafeYoutubeDL` ya abierto, estado
de la guild). Testear el loop inline requeriría mockear demasiado.

Extraemos el loop a un helper privado de `Music`:

```python
async def _select_first_playable_candidate(self, ydl, entries):
    """Itera entries de ytsearch y devuelve el info del primer candidato
    que extraiga sin DownloadError. Devuelve None si todos fallan o si
    no hay entries con id válido."""
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

El callsite en `play()` se reduce a:

```python
info = await self._select_first_playable_candidate(ydl, entries)
if not info:
    await ctx.send(
        "No se encontró un formato compatible para los resultados."
    )
    return
```

### Cambio funcional

- **Antes:** solo `"Requested format is not available"` → `continue`,
  el resto → `raise`.
- **Después:** cualquier `DownloadError` → `continue` con `logger.warning`
  que incluye `video_id` y razón truncada a 200 chars.
- Errores que **no** sean `DownloadError` siguen propagándose (timeouts del
  helper, bugs de programación, etc.). Conservador.

### Comportamiento conservado

- Si `entries` está vacío, el chequeo previo en `play()`
  (`if not entries: return`) sigue siendo el responsable.
- El chequeo `if not info:` post-helper se mantiene idéntico.
- El mensaje de usuario en caso de fallo total no cambia.

## Testing

### Test único (TDD red→green)

`tests/test_select_candidate.py::test_skips_unavailable_and_returns_next`:

- Mock de `Music._extract_info` con `side_effect = [DownloadError("Video
  unavailable"), {"url": "ok", "title": "ok"}]`.
- Llamar `_select_first_playable_candidate` con 2 entries.
- Assert: devuelve el segundo dict.
- Assert: `_extract_info` llamado 2 veces.

Este test fallaría con el código actual (el primer error abortaría con
`raise`) y pasa con el fix.

No agregamos tests de "todos fallan" ni "ningún entry válido" — el
comportamiento de retornar `None` en esos paths es trivial y el helper
es de 10 líneas; YAGNI.

## Risks

- **Esconder bugs reales:** ampliar el except podría enmascarar problemas
  serios (ej. cookies inválidas que afecten a TODOS los videos). Mitigado
  por el `logger.warning` por candidato y el mensaje al usuario cuando
  todos fallan. El usuario verá "No se encontró un formato compatible" y
  los logs tendrán 5 warnings detallados.
- **Errores no-DownloadError:** si yt-dlp lanza otra excepción
  (ej. `ExtractorError` directo), no se skipea. Aceptable: son raros y
  típicamente indican fallas más serias.

## Acceptance Criteria

1. Test nuevo pasa.
2. Tests existentes (5) siguen pasando.
3. Smoke test: `!play d4vd` reproduce sin abortar.
4. Logs muestran warning con `video_id` cuando un candidato es skipeado.
