---

# Design: /remind — Recordatorios con modal Discord

**Fecha:** 2026-05-03
**Estado:** Aprobado

## Resumen

Feature de recordatorios para ssj-bot. El usuario ejecuta `/remind`, se abre un modal de Discord con 4 campos, completa los datos y el bot programa un mensaje que se dispara a la hora indicada mencionando a las personas elegidas. Los recordatorios persisten en Supabase.

## Contexto del proyecto

- Bot de Discord en Python 3.12+ con discord.py 2.7.1
- Un único cog existente: `cogs/music_cog.py` (no se toca)
- Ya usa `discord.ui` para botones (MusicControlView, SearchView, etc.)
- Docker con `TZ=America/Santiago`
- No hay scheduler ni sistema de notificaciones proactivas actualmente
- El usuario tiene un proyecto Supabase existente (app to-do list con su pareja)

## Arquitectura

### Archivos nuevos

```
cogs/
  reminders_cog.py       # Cog con el slash command /remind y /reminders
utils/
  reminders_store.py     # Lógica de Supabase: CRUD de recordatorios
```

### Archivos modificados

```
.env.example             # Agregar SUPABASE_URL, SUPABASE_KEY, REMINDERS_CHANNEL_ID
bot.py                   # Cargar reminders_cog en setup_hook
requirements.txt         # Agregar supabase>=2.0.0
```

## Storage — Supabase

Tabla `reminders` en el proyecto Supabase existente del usuario:

```sql
create table reminders (
  id          uuid primary key default gen_random_uuid(),
  message     text not null,
  target_ids  text[] not null,        -- array de Discord user IDs a mencionar
  fire_at     timestamptz not null,   -- cuándo disparar (UTC)
  channel_id  text not null,          -- Discord channel ID donde mandar
  created_by  text not null,          -- Discord user ID de quien creó
  done        boolean default false,  -- true cuando ya se disparó
  created_at  timestamptz default now()
);
```

El bot usa `supabase-py` (cliente async). Operaciones:
- `create_reminder(data)` → INSERT
- `get_pending_reminders()` → SELECT WHERE done = false AND fire_at > now()
- `mark_done(id)` → UPDATE SET done = true

## Configuración (.env)

```env
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_KEY=tu-anon-key
REMINDERS_CHANNEL_ID=123456789012345678
```

## Flujo de usuario

### Crear recordatorio

1. Usuario escribe `/remind`
2. Discord abre un modal con 4 campos:
   - **Mensaje** (texto libre, requerido)
   - **Fecha** — acepta: `hoy`, `mañana`, `dd/mm` (ej: `25/05`)
   - **Hora** — formato `hh:mm` (ej: `21:00`)
   - **Para** — acepta: `yo`, `ella`, `ambos`
3. Usuario completa y confirma
4. El bot parsea los campos, resuelve la fecha/hora con timezone `America/Santiago`
5. El bot responde con embed de confirmación (efímero) + botón 🗑️ Cancelar:

```
✅ Recordatorio creado
━━━━━━━━━━━━━━━━━━━━━━━
📝  ver la peli
🕐  domingo 25 de mayo · 21:00
👥  @yo @ella
━━━━━━━━━━━━━━━━━━━━━━━
                [🗑️ Cancelar]
```

6. El bot guarda en Supabase y programa un `asyncio.create_task` con `asyncio.sleep`

### Cuando dispara

El bot manda al `REMINDERS_CHANNEL_ID`:

```
⏰ Recordatorio
━━━━━━━━━━━━━━━
ver la peli
━━━━━━━━━━━━━━━
@yo @ella
```

### Ver recordatorios activos

`/reminders` → embed efímero listando los pendientes con su ID corto y botón 🗑️ por cada uno.

### Cancelar

Botón 🗑️ en el embed de confirmación o en `/reminders` → marca `done = true` en Supabase y cancela el task de asyncio si sigue pendiente.

## Manejo de errores

| Caso | Comportamiento |
|------|---------------|
| Fecha inválida | Respuesta efímera: "Fecha inválida. Usa: hoy, mañana, o dd/mm" |
| Hora inválida | Respuesta efímera: "Hora inválida. Formato: hh:mm (ej: 21:00)" |
| Fecha/hora en el pasado | Respuesta efímera: "Esa fecha ya pasó 😅" |
| Supabase no disponible | Log de error + respuesta efímera: "No se pudo guardar el recordatorio, intenta de nuevo" |
| Bot reiniciado | Al arrancar, `get_pending_reminders()` y reprograma todos con `asyncio.sleep` |

## Resolución de "Para"

El campo "Para" mapea a Discord user IDs configurados en `.env`:

```env
REMINDER_USER_YO_ID=111111111111111111
REMINDER_USER_ELLA_ID=222222222222222222
```

| Valor | Menciona |
|-------|---------|
| `yo` | `<@REMINDER_USER_YO_ID>` |
| `ella` | `<@REMINDER_USER_ELLA_ID>` |
| `ambos` | `<@YO_ID> <@ELLA_ID>` |

## Dependencias nuevas

| Paquete | Versión | Para qué |
|---------|---------|---------|
| `supabase` | `>=2.0.0` | Cliente Python para Supabase |

## Scope excluido (YAGNI)

- Recordatorios recurrentes (cada viernes, etc.) — se puede agregar después
- Editar un recordatorio ya creado
- Integración con la app to-do list existente
- Múltiples servidores (el bot se usa en 2 servers privados)

## Tests

- `test_reminder_parsing.py`: testear parseo de fecha/hora con casos borde (hoy, mañana, dd/mm, hora inválida, fecha pasada)
- `test_reminders_store.py`: mockear Supabase client y testear create/get/mark_done
