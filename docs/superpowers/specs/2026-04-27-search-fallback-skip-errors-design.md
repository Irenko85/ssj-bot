# Search Fallback: Resilient Candidate Selection

**Date:** 2026-04-27
**Branch:** `fix/search-fallback-skip-errors`
**Type:** Bugfix

## Problem

Cuando el usuario ejecuta `!play <query>` (input no-URL), el bot debería
buscar en YouTube, encontrar un video del artista y reproducirlo. En la
práctica, `!play d4vd` mostraba "No se encontró un formato compatible para
los resultados." aunque d4vd tiene videos públicos sobrados en YouTube.

Investigación reveló **dos bugs combinados** en el path de búsqueda
(`cogs/music_cog.py`):

### Bug 1 (causa raíz): `playlist_items: "1"` aplica a ytsearch5

La constante global `YTDL_OPTIONS` en línea 31 tiene `"playlist_items": "1"`
para limitar playlists reales a un solo video. Pero `ytsearch5:<query>` se
trata internamente como una playlist de 5 elementos, y `playlist_items: "1"`
**también la corta a 1 sola entry**.

Resultado: en lugar de obtener 5 candidatos, el bot recibe 1, y a menudo es
el canal del artista (`ie_key='YoutubeTab'`), no un video.

El comando `!search` (línea 734) ya conoce el problema y hace
`search_options.pop("playlist_items", None)`. El path de `!play <query>`
(línea 488) **no lo hace**, así que sufre el bug.

### Bug 2: el except del fallback solo skipea un tipo de error

El bloque `except` del loop (`cogs/music_cog.py:492-498`) solo trata como
recuperable el error `"Requested format is not available"`. Cualquier otro
`DownloadError` (ej. `"Video unavailable"` cuando el "video" es en realidad
un channel ID) hace `raise`, abortando el comando completo.

### Caso real observado

`!play d4vd`:

1. `ytsearch5:d4vd` con `playlist_items: "1"` devuelve 1 sola entry.
2. La entry es el channel `UC98WsFnuhfS3uT8PwdYCjbw` con `ie_key='YoutubeTab'`.
3. Construir `https://www.youtube.com/watch?v=UC98WsFnuhfS3uT8PwdYCjbw`
   y extraerlo lanza `DownloadError: Video unavailable`.
4. El except solo skipea "Requested format is not available" → `raise` →
   comando aborta con stack trace.

Sin el bug 1, `entries` tendría 5 elementos: 1 channel y 4 videos.
Sin el bug 2, el loop ya saltaría al siguiente. Los dos juntos rompen
totalmente la búsqueda.

## Goal

`!play <query>` debe:

1. Recibir hasta 5 candidatos reales del search.
2. Saltarse channels/playlists (no son reproducibles como video).
3. Saltarse videos no disponibles (privados, removidos, etc.).
4. Reproducir el primer candidato que extraiga ok.
5. Si **ningún** candidato funciona, mostrar el mensaje de error existente.

## Non-Goals

- No tocar el path de URL directa.
- No cambiar `ytsearch5:` a otro límite.
- No reemplazar el message de error final.
- No agregar reintentos por candidato individual (yt-dlp ya reintenta
  internamente clientes ios/android/tv/web).

## Approach

### Cambio 1: `pop("playlist_items", ...)` en search_opts

Replicar el patrón ya existente en línea 734. Una sola línea agregada
después de copiar `YTDL_OPTIONS`:

```python
search_opts = YTDL_OPTIONS.copy()
search_opts["extract_flat"] = True
search_opts["skip_download"] = True
search_opts.pop("playlist_items", None)  # NUEVO
```

Esto hace que `ytsearch5:` devuelva las 5 entries reales.

### Cambio 2: filtrar entries no-video antes del loop

Después de obtener `entries` y antes de pasarlas al helper, filtrar:

```python
playable_entries = [
    e for e in entries
    if e.get("ie_key") == "Youtube"
]
```

`ie_key == "Youtube"` identifica videos individuales. Channels son
`YoutubeTab`, playlists son `YoutubePlaylist`, etc. Mantenemos solo
videos.

Si después del filtro `playable_entries` está vacío, mostramos el mismo
mensaje de error que cuando no hay resultados.

### Cambio 3: helper `_select_first_playable_candidate`

Refactor para testabilidad (ya implementado en commits previos de esta
branch). El helper itera entries y skipea **cualquier** `DownloadError`
con un warning descriptivo. Devuelve el primer info exitoso, o `None`
si todos fallan.

### Comportamiento conservado

- Si `entries` está vacío post-search, mensaje "No se encontraron
  resultados."
- Si `playable_entries` está vacío post-filtro, mismo mensaje (o el
  de "No se encontró un formato compatible", a evaluar).
- Si todos los candidatos fallan en el helper, mensaje
  "No se encontró un formato compatible para los resultados."

## Testing

### Test 1 (ya existe): helper skipea DownloadError

`tests/test_select_candidate.py::test_skips_unavailable_and_returns_next`.

### Test 2 (nuevo): filtro deja pasar solo videos

`tests/test_select_candidate.py::test_filters_non_video_entries` —
verificar que dada una lista mixta (channel + 2 videos), el helper
solo intenta los 2 videos.

Nota: el filtro vive en `play()`, no en el helper. Pero podemos
testear el comportamiento end-to-end del helper ante entries
pre-filtradas (asegurarnos que entries con `id` válido se procesan
en orden), y testear el filtro a nivel de comprensión por inspección
de código + smoke test (no merece su propio test unitario porque es
una list comprehension trivial).

Decisión simplificada: **no agregar test 2**. El filtro es 1 línea
trivial y el smoke test cubre el comportamiento real.

### Smoke test final

`!play d4vd` debe reproducir un video de d4vd (cualquiera de los
4 videos en entries 1-4 de ytsearch5).

## Risks

- **Test del filtro omitido:** trade-off explícito de simplicidad.
  Si el filtro futuro crece, agregar test.
- **`ie_key == "Youtube"` muy estricto:** puede que yt-dlp use otros
  ie_keys para videos válidos (ej. `YoutubeShort`). Verificación:
  el smoke test confirmará. Si falta cobertura, se ajusta a
  `ie_key in {"Youtube", ...}`.
- **`pop("playlist_items")` puede romper otros flows:** No, porque
  `search_opts` es una copia local. La constante global queda
  intacta.

## Acceptance Criteria

1. Tests existentes (6) siguen pasando.
2. `!play d4vd` reproduce un video del artista (smoke test).
3. Logs muestran filtrado de channel + intento exitoso de video.
4. Diff focused: ~5 líneas modificadas en `cogs/music_cog.py`.
