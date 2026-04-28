# Code Review: visual-messages — Issues pendientes

**Feature:** `feature/visual-messages`
**Review date:** 2026-04-27
**Reviewer verdict:** No listo para merge

---

## 🔴 Crítico

### 1. `MusicControlView` nunca se registra como persistent view

- **Archivos:** `bot.py` (startup), `utils/ui.py:140-145`
- **Problema:** la vista se define con `timeout=None` y `custom_id`s fijos (requerimiento de persistent views de discord.py), pero el bot nunca llama `bot.add_view(MusicControlView(...))` en el evento `on_ready` o durante la carga del cog.
- **Consecuencia:** tras un restart del proceso del bot, los mensajes "Now Playing" siguen visibles en Discord pero los botones dejan de responder por completo.
- **Fix:**
  1. Desacoplar `MusicControlView` de `ctx` para que pueda instanciarse sin contexto en startup.
  2. Registrar la vista en `on_ready`: `bot.add_view(MusicControlView(bot=bot))`.
  3. Adaptar los callbacks de los botones para reconstruir el contexto desde `interaction` (ya disponible en el callback).
- **Tests requeridos:**
  - Verificar que `bot.add_view` se llama durante startup con una instancia de `MusicControlView`.
  - Verificar que los callbacks de botones funcionan recibiendo un `interaction` sin `ctx`.

---

## 🟡 Importante

### 2. `_finalize_now_playing` no se llama en `stop`, inactividad y canal vacío

- **Archivos:** `cogs/music_cog.py` — métodos `stop` (~línea 640-648), `check_inactivity` (~línea 781-786 y 808-813)
- **Problema:** esos caminos limpian el estado (`_cleanup_state`) o desconectan el bot sin llamar `_finalize_now_playing`. El mensaje Now Playing queda con botones activos aunque no haya reproducción ni estado.
- **Fix:** llamar `await self._finalize_now_playing(ctx, "Reproducción detenida.")` (o el mensaje apropiado) **antes** de `_cleanup_state` en cada uno de esos caminos. Para inactividad, el `ctx` no está disponible directamente — usar el canal almacenado en `state.inactivity_channel` para editar el mensaje.
- **Tests requeridos:**
  - `stop` → `state.now_playing_message.edit` fue llamado con botones deshabilitados.
  - Inactividad → idem.
  - Canal vacío → idem.

### 3. `entries` puede quedar `UnboundLocalError` en el comando `search`

- **Archivo:** `cogs/music_cog.py:835-843` (aprox.)
- **Problema:** si `_extract_info()` lanza excepción, se envía un embed de error pero el flujo continúa hacia el código que usa `entries`, que nunca fue asignada → `UnboundLocalError`.
- **Fix:** inicializar `entries = []` antes del bloque `try`, o añadir `return` dentro del `except`.
- **Tests requeridos:**
  - `search` con `_extract_info()` que lanza excepción → `ctx.send` llamado con embed de error y ningún crash posterior.

### 4. `utils/ui.py` importa y usa `AsyncMock`/`MagicMock` en código de producción

- **Archivo:** `utils/ui.py` — imports (~líneas 3-6) y método `stop()` de `MusicControlView` (~líneas 234-239)
- **Problema:** el método `stop()` contiene una rama que detecta si `interaction.response` es un `MagicMock` para evitar await. Código de test mezclado en producción.
- **Fix:**
  1. Eliminar `from unittest.mock import AsyncMock, MagicMock` de `utils/ui.py`.
  2. Reemplazar la rama de detección de mock por código limpio: simplemente `await interaction.response.defer(ephemeral=True)`.
  3. Adaptar los tests de `MusicControlView` para que provean doubles correctos (un `AsyncMock` real para `interaction.response.defer`).
- **Tests requeridos:** los tests existentes deben seguir pasando tras la limpieza.

### 5. Mensajes user-facing que siguen siendo texto plano

- **Archivos principales:** `bot.py` (~línea 107-112), `cogs/music_cog.py` (~líneas 190-191, 309-310, 391-392, 430, 445, 503, 574-582, 638, 656-676, 687, 696, 701, 711, 722, 839-843, 885-899, 905-907, 913, 922-925, 943-945)
- **Problema:** ~15+ rutas siguen usando `ctx.send("texto")` sin embed. Rutas notables:
  - `on_app_command_error` en `bot.py` (handler de slash commands) → sin embed
  - `SearchSelect.callback` → confirmación de selección sin embed
  - Varios guards de "ya en canal" / "no conectado" / etc. en `music_cog.py`
- **Fix:** pasar cada envío por el builder apropiado de `utils/ui.py` (`build_error_embed`, `build_info_embed`, `build_warning_embed`) o usar el helper `_send_embed`. Priorizar `on_app_command_error` y `SearchSelect` por ser visibles al usuario.
- **Tests requeridos:**
  - `on_app_command_error` con `AppCommandError` → `interaction.response.send_message` (o `followup.send`) llamado con `embed=`.
  - `SearchSelect.callback` → `ctx.send` llamado con `embed=`.

---

## 🔵 Menor

### 6. `build_queue_embed` renderiza `▶ Ahora: None` cuando no hay canción activa

- **Archivo:** `utils/ui.py:91-120` y `cogs/music_cog.py:685`
- **Problema:** si `s.actual_song` es `None`, el embed de cola muestra literalmente `▶ Ahora: None`.
- **Fix:** en `build_queue_embed` (o en la llamada), usar `actual_song or "Nada"` (o no mostrar el campo si es None).
- **Tests requeridos:** test con `actual_song=None` → el embed no contiene la cadena `"None"`.

---

## Tests adicionales recomendados por el reviewer

- Registro de persistent view en startup.
- Callbacks de botones funcionando desde `interaction` sin `ctx`.
- `stop`/inactividad → `now_playing_message.edit` con botones deshabilitados.
- `search` con `_extract_info()` fallando → error embed sin crash.
- `on_app_command_error` → embed.
- `SearchSelect` confirmación → embed.

---

## Estado

- [ ] Issue 1 (crítico): persistent view registration
- [ ] Issue 2 (importante): finalizar now-playing al parar/inactividad
- [ ] Issue 3 (importante): UnboundLocalError en search
- [ ] Issue 4 (importante): limpiar mocks de producción en utils/ui.py
- [ ] Issue 5 (importante): cubrir plain-text restante con embeds
- [ ] Issue 6 (menor): queue embed None
