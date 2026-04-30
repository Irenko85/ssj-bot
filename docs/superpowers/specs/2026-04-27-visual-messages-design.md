# Diseño: Mejoras visuales de mensajes del bot

**Fecha:** 2026-04-27  
**Estado:** Aprobado  
**Alcance:** `utils/ui.py` (nuevo), `cogs/music_cog.py` (modificado), `bot.py` (modificado)

---

## Objetivo

Reemplazar todos los mensajes de texto plano del bot de música por `discord.Embed` ricos y añadir botones de control de reproducción al mensaje de "Ahora reproduciendo", logrando una experiencia visual oscura y premium.

---

## Arquitectura

### Archivos afectados

| Archivo | Tipo de cambio |
|---------|---------------|
| `utils/ui.py` | NUEVO — centraliza toda la lógica visual |
| `cogs/music_cog.py` | MODIFICADO — reemplaza `ctx.send()` con helpers de `ui.py` |
| `bot.py` | MODIFICADO — errores globales usan embeds |

---

## `utils/ui.py`

### Paleta de colores (constantes)

```python
COLOR_PRIMARY  = 0x6C3483  # Morado profundo — Now Playing, acciones principales
COLOR_SUCCESS  = 0x2980B9  # Azul índigo — confirmaciones, añadir a cola
COLOR_ERROR    = 0x922B21  # Rojo oscuro — errores
COLOR_WARNING  = 0xCA6F1E  # Ámbar oscuro — advertencias de inactividad
COLOR_INFO     = 0x2C3E50  # Gris azulado — mensajes informativos genéricos
```

### Funciones de construcción de embeds

#### `build_now_playing_embed(song: dict) -> discord.Embed`
- **Color:** `COLOR_PRIMARY`
- **Título:** `🎵 Ahora reproduciendo`
- **Descripción:** nombre de la canción en negrita
- **Thumbnail:** extraído como `https://img.youtube.com/vi/{VIDEO_ID}/0.jpg` usando regex sobre la URL. Si no se puede extraer (playlist, SoundCloud, etc.) → sin thumbnail, sin error.
- **Footer:** nombre del bot + hora actual
- **No incluye** campo "Pedido por"

#### `build_added_to_queue_embed(song: dict, position: int) -> discord.Embed`
- **Color:** `COLOR_SUCCESS`
- **Título:** `✅ Añadido a la cola`
- **Descripción:** nombre de la canción
- **Field:** `Posición en cola` → número

#### `build_queue_embed(songs: list, now_playing: str, page: int = 1, page_size: int = 10) -> discord.Embed`
- **Color:** `COLOR_SUCCESS`
- **Título:** `📋 Cola de reproducción`
- **Descripción:** `▶ Ahora: {now_playing}` + lista numerada de canciones de la página actual
- **Footer:** `Página {page}/{total_pages} · {total} canciones en cola`

#### `build_error_embed(message: str) -> discord.Embed`
- **Color:** `COLOR_ERROR`
- **Título:** `❌ Error`
- **Descripción:** `message`

#### `build_warning_embed(message: str) -> discord.Embed`
- **Color:** `COLOR_WARNING`
- **Título:** `⚠️ Aviso`
- **Descripción:** `message`

#### `build_info_embed(title: str, message: str) -> discord.Embed`
- **Color:** `COLOR_INFO`
- **Título:** `title`
- **Descripción:** `message`

#### `build_search_results_embed(results: list) -> discord.Embed`
- **Color:** `COLOR_PRIMARY`
- **Título:** `🔍 Resultados de búsqueda`
- **Descripción:** lista numerada de resultados

---

### `MusicControlView(discord.ui.View)`

View de duración indefinida (timeout=None) que se adjunta al mensaje de Now Playing.

#### Botones

| Botón | Emoji | Style | ID | Acción |
|-------|-------|-------|----|--------|
| Pause/Resume | ⏸/▶️ | `Secondary` | `pause_resume` | Alterna pausa/reproducción. Cambia emoji según estado. Respuesta ephemeral. |
| Skip | ⏭ | `Primary` | `skip` | Salta la canción actual. Respuesta ephemeral de confirmación. |
| Stop | ⏹ | `Danger` | `stop` | Para la música, desconecta el bot. Deshabilita todos los botones del View. |
| Ver cola | 📋 | `Secondary` | `view_queue` | Muestra la cola actual. Respuesta ephemeral. |

#### Restricciones
- Cualquier usuario del servidor puede usar los botones (sin restricción de quien pidió la canción)
- Al ejecutar `stop`: los 4 botones se ponen en `disabled=True` y se edita el mensaje

#### Ciclo de vida del mensaje Now Playing
- Solo existe **un** mensaje de Now Playing activo por servidor (instancia de `GuildState`)
- Cuando termina una canción y **hay siguiente**: el mensaje se **edita** (`message.edit()`) con el nuevo embed + View. No se envía un mensaje nuevo.
- Cuando la cola se vacía o se ejecuta `stop`: los botones se deshabilitan, el embed cambia a "Reproducción finalizada"

---

## Modificaciones en `cogs/music_cog.py`

### Cambios por comando/evento

| Punto | Cambio |
|-------|--------|
| Inicio de reproducción (`_play_next`) | Enviar/editar mensaje con `build_now_playing_embed` + `MusicControlView`. Guardar referencia al mensaje en `GuildState`. |
| Añadir a cola (`play`) | `build_added_to_queue_embed` |
| Ver cola (`queue`) | `build_queue_embed` |
| Error de reproducción | `build_error_embed` |
| Desconexión por inactividad | `build_warning_embed` |
| Stop / skip / pause | Respuestas ephemeral con `build_info_embed` (salvo los botones que ya responden por sí solos) |
| Búsqueda (`search`) | `build_search_results_embed` + `SearchView` existente |

### `GuildState` — campo nuevo
Añadir `now_playing_message: discord.Message | None = None` para guardar la referencia al mensaje activo de Now Playing.

---

## Modificaciones en `bot.py`

- El manejador de errores global (`on_application_command_error` / `on_command_error`) usa `build_error_embed` en lugar de texto plano.

---

## Casos borde

- **Sin thumbnail disponible:** la función `build_now_playing_embed` ignora silenciosamente el fallo de extracción del ID de YouTube.
- **Canción sin duración:** omitir ese dato del embed.
- **Cola vacía al pedir `queue`:** embed informativo que lo indique.
- **Stop mientras no hay música:** error ephemeral con embed.

---

## Testing

- Los tests existentes en `tests/` no deberían romperse (no testean mensajes directamente).
- No se requieren tests nuevos para esta iteración, aunque se puede considerar testear `build_now_playing_embed` con URLs válidas e inválidas.

---

## Out of scope

- Paginación interactiva de la cola con botones Anterior/Siguiente (posible mejora futura)
- Temas visuales intercambiables por servidor
- Internacionalización (i18n)
