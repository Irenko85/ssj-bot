# Spec: Thumbnails en embeds + Now Playing siempre al final

**Fecha:** 2026-04-28
**Branch:** feature/visual-messages

---

## Feature A — Miniatura en "Añadido a la cola" y "Ahora reproduciendo"

### Causa raíz
Al construir el dict `song` en `play()` (~línea 599) y `SearchSelect.callback()` (~línea 916), se descartan campos disponibles del info dict de yt-dlp: `thumbnail`, `duration`, `webpage_url`.

### Cambios requeridos

**`cogs/music_cog.py`** — en ambos lugares donde se construye el dict `song`:
```python
# Antes
song = {"title": title, "url": url, "headers": headers}

# Después
song = {
    "title": title,
    "url": url,
    "headers": headers,
    "thumbnail": info.get("thumbnail"),
    "duration": info.get("duration"),
    "webpage_url": info.get("webpage_url"),
}
```

**`utils/ui.py`** — `build_added_to_queue_embed`:
- Añadir `embed.set_thumbnail(url=thumbnail)` si `song.get("thumbnail")` está disponible.
- `build_now_playing_embed` ya consume `duration` y `webpage_url`/`source_url` — funcionará automáticamente.

### Criterios de aceptación
- El embed "✅ Añadido a la cola" muestra la miniatura del video de YouTube.
- El embed "🎵 Ahora reproduciendo" muestra la miniatura y la duración.
- Si no hay thumbnail disponible, los embeds funcionan igual que antes (sin miniatura).

---

## Feature B — "Ahora reproduciendo" siempre al final del chat

### Comportamiento actual
`_publish_now_playing` edita el mensaje existente (`s.now_playing_message.edit(...)`). El mensaje queda en su posición original y queda enterrado cuando llegan mensajes nuevos.

### Cambio requerido

**`cogs/music_cog.py`** — `_publish_now_playing`:
```python
# Antes: editar si existe
if s.now_playing_message is not None:
    await s.now_playing_message.edit(embed=embed, view=view)
    return s.now_playing_message

# Después: borrar siempre y enviar nuevo
if s.now_playing_message is not None:
    try:
        await s.now_playing_message.delete()
    except Exception:
        pass
    s.now_playing_message = None

s.now_playing_message = await ctx.send(embed=embed, view=view)
return s.now_playing_message
```

### Criterios de aceptación
- Al cambiar de canción, el mensaje "Ahora reproduciendo" anterior desaparece y aparece uno nuevo al final del chat.
- `_finalize_now_playing` sigue funcionando (edita el último mensaje enviado).

---

## Tests requeridos

- `build_added_to_queue_embed` con `thumbnail` → `embed.thumbnail.url` tiene el valor correcto.
- `build_added_to_queue_embed` sin `thumbnail` → embed válido, sin thumbnail.
- `_publish_now_playing` llamado dos veces → el primer mensaje fue eliminado, se envió uno nuevo.
- `build_now_playing_embed` con `duration` y `webpage_url` → campos presentes en el embed.

---

## Archivos a modificar

- `utils/ui.py` — `build_added_to_queue_embed`
- `cogs/music_cog.py` — construcción del dict `song` (2 lugares), `_publish_now_playing`
