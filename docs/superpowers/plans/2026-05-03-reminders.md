# Reminders Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Agregar sistema de recordatorios al bot con modal de Discord, persistencia en Supabase y disparo automático a la hora programada.

**Architecture:** Nuevo cog `reminders_cog.py` con slash command `/remind` que abre un modal, más `utils/reminders_store.py` para la lógica de Supabase. Al arrancar el bot se recargan los recordatorios pendientes y se reprograman con asyncio.

**Tech Stack:** discord.py 2.7.1, supabase-py>=2.0.0, Python 3.12, pytest-asyncio

---

**Working branch:** `docs/reminders-design-spec`

## Contexto relevante (del codebase)

- `bot.py:12-15` — el proyecto ya carga variables de entorno con `load_dotenv()` y usa `os.getenv()` como patrón base.
- `bot.py:48-55` — `SSJBot.setup_hook()` ya se usa para registrar una `View` global; es el lugar correcto para mover la carga del nuevo cog.
- `bot.py:154-167` — hoy los cogs se cargan antes de `bot.start()`, así que Task 6 debe reubicar esta responsabilidad dentro de `setup_hook`.
- `cogs/music_cog.py:680-1104` — el repositorio ya usa comandos híbridos, pero para abrir un modal conviene un slash command puro con `app_commands`.
- `cogs/music_cog.py:1238-1239` — el patrón de extensión actual es `async def setup(bot): await bot.add_cog(...)`; el nuevo cog debe seguirlo.
- `utils/ui.py:21-42` — ya existen helpers de embeds (`build_error_embed`, `build_info_embed`) reutilizables para respuestas efímeras.
- `utils/ui.py:201-387` — el proyecto ya usa `discord.ui.View` con `custom_id` estables; esto sirve como referencia para botones de cancelar.
- `tests/test_app_command_error.py:11-56` — los tests usan `AsyncMock`/`MagicMock` para interacciones Discord; conviene copiar ese estilo para el nuevo cog.
- `tests/test_music_control_view.py:70-226` — ya hay pruebas de callbacks de `View` y de `setup_hook`; Task 6 debe actualizar esta cobertura.
- `docs/superpowers/specs/2026-05-03-reminders-design.md:40-157` — define tabla Supabase, inputs aceptados, mensajes de error, persistencia y exclusiones de scope.

## Decisiones de diseño

1. **Usar `app_commands.command` en vez de `hybrid_command` para `/remind` y `/reminders`** — abrir un modal requiere `Interaction.response.send_modal()`, así que un slash command puro reduce adaptación innecesaria.
2. **Mantener la lógica de parseo y almacenamiento separada** — `utils/reminders_store.py` contendrá parseo + store porque el spec lo pide, mientras el cog solo orquesta Discord/UI/scheduler.
3. **Crear el cliente async de Supabase de forma lazy** — `RemindersStore.__init__()` no puede hacer `await`; un helper async interno facilita tests con mocks y evita side effects al importar módulos.
4. **Usar helpers puros en `cogs/reminders_cog.py` para formato y mapeo** — así se pueden testear embeds, menciones y filtrado sin tests de integración de Discord.
5. **Scheduler en memoria con `asyncio.Task` por recordatorio** — cumple el spec, es simple, y se recupera tras reinicio con `cog_load()` + `get_pending()`. La alternativa de jobs externos se descarta por YAGNI.
6. **No mover lógica de recordatorios a `utils/ui.py`** — ese archivo hoy está centrado en música; mezclar dominios distintos aumentaría acoplamiento innecesario.

## Mapa de archivos

- **Create:** `utils/reminders_store.py` — parseo de fecha/hora y acceso async a Supabase.
- **Create:** `cogs/reminders_cog.py` — comandos `/remind` y `/reminders`, modal, scheduler y botones cancelar.
- **Create:** `tests/test_reminder_parsing.py` — cobertura de parseo.
- **Create:** `tests/test_reminders_store.py` — cobertura del store con mocks de Supabase.
- **Create:** `tests/test_reminders_cog.py` — cobertura de helpers puros del cog.
- **Create:** `tests/test_reminders_scheduler.py` — cobertura de scheduler/cancelación sin integración real con Discord.
- **Create:** `tests/test_reminders_listing.py` — cobertura de listado y view de cancelación múltiple.
- **Modify:** `bot.py` — mover carga de cogs a `setup_hook`.
- **Modify:** `.env.example` — variables nuevas de recordatorios.
- **Modify:** `requirements.txt` — agregar `supabase>=2.0.0`.
- **Modify:** `tests/test_music_control_view.py` — adaptar test de `setup_hook` al nuevo comportamiento.

---

### Task 1: reminders_store.py — parseo de fecha/hora

**Files:**
- Create: `utils/reminders_store.py`
- Test: `tests/test_reminder_parsing.py`

- [ ] **Step 1: Write the failing test**

```python
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from utils import reminders_store

TZ = "America/Santiago"


def _fixed_now() -> datetime:
    return datetime(2026, 5, 3, 10, 30, tzinfo=ZoneInfo(TZ))


def _patch_now(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(reminders_store, "_now_in_timezone", lambda tz: _fixed_now())


def test_parse_when_accepts_hoy(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_now(monkeypatch)

    result = reminders_store.parse_when("hoy", "21:00", TZ)

    expected = datetime(2026, 5, 3, 21, 0, tzinfo=ZoneInfo(TZ)).astimezone(
        timezone.utc
    )
    assert result == expected


def test_parse_when_accepts_manana(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_now(monkeypatch)

    result = reminders_store.parse_when("mañana", "08:15", TZ)

    expected = datetime(2026, 5, 4, 8, 15, tzinfo=ZoneInfo(TZ)).astimezone(
        timezone.utc
    )
    assert result == expected


def test_parse_when_accepts_dd_mm(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_now(monkeypatch)

    result = reminders_store.parse_when("25/05", "21:00", TZ)

    expected = datetime(2026, 5, 25, 21, 0, tzinfo=ZoneInfo(TZ)).astimezone(
        timezone.utc
    )
    assert result == expected


def test_parse_when_rejects_invalid_hour(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_now(monkeypatch)

    with pytest.raises(
        ValueError, match=r"Hora inválida\. Formato: hh:mm \(ej: 21:00\)"
    ):
        reminders_store.parse_when("hoy", "25:99", TZ)


def test_parse_when_rejects_invalid_date(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_now(monkeypatch)

    with pytest.raises(
        ValueError, match=r"Fecha inválida\. Usa: hoy, mañana, o dd/mm"
    ):
        reminders_store.parse_when("32/05", "21:00", TZ)


def test_parse_when_rejects_past_date(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_now(monkeypatch)

    with pytest.raises(ValueError, match=r"Esa fecha ya pasó 😅"):
        reminders_store.parse_when("hoy", "09:00", TZ)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
& "C:\Users\Irenko\Desktop\ssj-bot\venv\Scripts\python.exe" -m pytest tests/test_reminder_parsing.py -v
```

Expected: `FAIL` porque `utils/reminders_store.py` todavía no existe.

- [ ] **Step 3: Write minimal implementation**

```python
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

REMINDER_DATE_ERROR = "Fecha inválida. Usa: hoy, mañana, o dd/mm"
REMINDER_TIME_ERROR = "Hora inválida. Formato: hh:mm (ej: 21:00)"
REMINDER_PAST_ERROR = "Esa fecha ya pasó 😅"


def _now_in_timezone(tz: str) -> datetime:
    return datetime.now(ZoneInfo(tz))


def _parse_date_token(fecha: str, now_local: datetime) -> datetime.date:
    token = fecha.strip().lower()

    if token == "hoy":
        return now_local.date()

    if token == "mañana":
        return (now_local + timedelta(days=1)).date()

    parts = token.split("/")
    if len(parts) != 2:
        raise ValueError(REMINDER_DATE_ERROR)

    try:
        day = int(parts[0])
        month = int(parts[1])
    except ValueError as exc:
        raise ValueError(REMINDER_DATE_ERROR) from exc

    try:
        return datetime(now_local.year, month, day, tzinfo=now_local.tzinfo).date()
    except ValueError as exc:
        raise ValueError(REMINDER_DATE_ERROR) from exc


def _parse_time_token(hora: str) -> time:
    token = hora.strip()
    parts = token.split(":")
    if len(parts) != 2:
        raise ValueError(REMINDER_TIME_ERROR)

    try:
        hours = int(parts[0])
        minutes = int(parts[1])
    except ValueError as exc:
        raise ValueError(REMINDER_TIME_ERROR) from exc

    if hours not in range(24) or minutes not in range(60):
        raise ValueError(REMINDER_TIME_ERROR)

    return time(hour=hours, minute=minutes)


def parse_when(fecha: str, hora: str, tz: str) -> datetime:
    zone = ZoneInfo(tz)
    now_local = _now_in_timezone(tz)
    reminder_date = _parse_date_token(fecha, now_local)
    reminder_time = _parse_time_token(hora)

    local_fire_at = datetime.combine(reminder_date, reminder_time, tzinfo=zone)
    if local_fire_at <= now_local:
        raise ValueError(REMINDER_PAST_ERROR)

    return local_fire_at.astimezone(timezone.utc)
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
& "C:\Users\Irenko\Desktop\ssj-bot\venv\Scripts\python.exe" -m pytest tests/test_reminder_parsing.py -v
```

Expected: `6 passed`.

---

### Task 2: reminders_store.py — cliente Supabase

**Files:**
- Modify: `utils/reminders_store.py`
- Test: `tests/test_reminders_store.py`

- [ ] **Step 1: Write the failing test**

```python
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from utils import reminders_store
from utils.reminders_store import RemindersStore


@pytest.mark.asyncio
async def test_create_inserts_row_and_returns_inserted_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = MagicMock()
    query = MagicMock()
    query.execute = AsyncMock(
        return_value=SimpleNamespace(
            data=[
                {
                    "id": "rem-1",
                    "message": "ver la peli",
                    "target_ids": ["111", "222"],
                    "fire_at": "2026-05-26T01:00:00+00:00",
                    "channel_id": "333",
                    "created_by": "444",
                    "done": False,
                }
            ]
        )
    )
    table = MagicMock()
    table.insert.return_value = query
    client.table.return_value = table

    async def fake_create_client(url: str, key: str):
        assert url == "https://example.supabase.co"
        assert key == "test-key"
        return client

    monkeypatch.setattr(
        reminders_store, "_create_async_supabase_client", fake_create_client
    )

    store = RemindersStore("https://example.supabase.co", "test-key")
    fire_at = datetime(2026, 5, 26, 1, 0, tzinfo=timezone.utc)

    result = await store.create(
        message="ver la peli",
        target_ids=["111", "222"],
        fire_at=fire_at,
        channel_id="333",
        created_by="444",
    )

    client.table.assert_called_once_with("reminders")
    table.insert.assert_called_once_with(
        {
            "message": "ver la peli",
            "target_ids": ["111", "222"],
            "fire_at": "2026-05-26T01:00:00+00:00",
            "channel_id": "333",
            "created_by": "444",
            "done": False,
        }
    )
    assert result["id"] == "rem-1"


@pytest.mark.asyncio
async def test_get_pending_returns_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    client = MagicMock()
    query = MagicMock()
    query.eq.return_value = query
    query.gt.return_value = query
    query.order.return_value = query
    query.execute = AsyncMock(
        return_value=SimpleNamespace(
            data=[
                {
                    "id": "rem-1",
                    "message": "ver la peli",
                    "target_ids": ["111"],
                    "fire_at": "2026-05-26T01:00:00+00:00",
                    "channel_id": "333",
                    "created_by": "444",
                    "done": False,
                }
            ]
        )
    )
    table = MagicMock()
    table.select.return_value = query
    client.table.return_value = table

    async def fake_create_client(url: str, key: str):
        return client

    monkeypatch.setattr(
        reminders_store, "_create_async_supabase_client", fake_create_client
    )

    store = RemindersStore("https://example.supabase.co", "test-key")

    result = await store.get_pending()

    client.table.assert_called_once_with("reminders")
    table.select.assert_called_once_with("*")
    query.eq.assert_called_once_with("done", False)
    assert query.gt.call_args.args[0] == "fire_at"
    query.order.assert_called_once_with("fire_at")
    assert result[0]["id"] == "rem-1"


@pytest.mark.asyncio
async def test_mark_done_updates_row(monkeypatch: pytest.MonkeyPatch) -> None:
    client = MagicMock()
    query = MagicMock()
    query.eq.return_value = query
    query.execute = AsyncMock(return_value=SimpleNamespace(data=[]))
    table = MagicMock()
    table.update.return_value = query
    client.table.return_value = table

    async def fake_create_client(url: str, key: str):
        return client

    monkeypatch.setattr(
        reminders_store, "_create_async_supabase_client", fake_create_client
    )

    store = RemindersStore("https://example.supabase.co", "test-key")

    await store.mark_done("rem-1")

    client.table.assert_called_once_with("reminders")
    table.update.assert_called_once_with({"done": True})
    query.eq.assert_called_once_with("id", "rem-1")
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
& "C:\Users\Irenko\Desktop\ssj-bot\venv\Scripts\python.exe" -m pytest tests/test_reminders_store.py -v
```

Expected: `FAIL` porque `RemindersStore` aún no existe.

- [ ] **Step 3: Write minimal implementation**

```python
from __future__ import annotations

import asyncio
from datetime import datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

REMINDER_DATE_ERROR = "Fecha inválida. Usa: hoy, mañana, o dd/mm"
REMINDER_TIME_ERROR = "Hora inválida. Formato: hh:mm (ej: 21:00)"
REMINDER_PAST_ERROR = "Esa fecha ya pasó 😅"


def _now_in_timezone(tz: str) -> datetime:
    return datetime.now(ZoneInfo(tz))


def _parse_date_token(fecha: str, now_local: datetime) -> datetime.date:
    token = fecha.strip().lower()

    if token == "hoy":
        return now_local.date()

    if token == "mañana":
        return (now_local + timedelta(days=1)).date()

    parts = token.split("/")
    if len(parts) != 2:
        raise ValueError(REMINDER_DATE_ERROR)

    try:
        day = int(parts[0])
        month = int(parts[1])
    except ValueError as exc:
        raise ValueError(REMINDER_DATE_ERROR) from exc

    try:
        return datetime(now_local.year, month, day, tzinfo=now_local.tzinfo).date()
    except ValueError as exc:
        raise ValueError(REMINDER_DATE_ERROR) from exc


def _parse_time_token(hora: str) -> time:
    token = hora.strip()
    parts = token.split(":")
    if len(parts) != 2:
        raise ValueError(REMINDER_TIME_ERROR)

    try:
        hours = int(parts[0])
        minutes = int(parts[1])
    except ValueError as exc:
        raise ValueError(REMINDER_TIME_ERROR) from exc

    if hours not in range(24) or minutes not in range(60):
        raise ValueError(REMINDER_TIME_ERROR)

    return time(hour=hours, minute=minutes)


def parse_when(fecha: str, hora: str, tz: str) -> datetime:
    zone = ZoneInfo(tz)
    now_local = _now_in_timezone(tz)
    reminder_date = _parse_date_token(fecha, now_local)
    reminder_time = _parse_time_token(hora)

    local_fire_at = datetime.combine(reminder_date, reminder_time, tzinfo=zone)
    if local_fire_at <= now_local:
        raise ValueError(REMINDER_PAST_ERROR)

    return local_fire_at.astimezone(timezone.utc)


async def _create_async_supabase_client(supabase_url: str, supabase_key: str):
    from supabase import acreate_client

    return await acreate_client(supabase_url, supabase_key)


class RemindersStore:
    def __init__(self, supabase_url: str, supabase_key: str) -> None:
        self.supabase_url = supabase_url
        self.supabase_key = supabase_key
        self._client: Any | None = None
        self._client_lock = asyncio.Lock()

    async def _get_client(self):
        if self._client is not None:
            return self._client

        async with self._client_lock:
            if self._client is None:
                self._client = await _create_async_supabase_client(
                    self.supabase_url, self.supabase_key
                )

        return self._client

    async def create(
        self,
        message: str,
        target_ids: list[str],
        fire_at: datetime,
        channel_id: str,
        created_by: str,
    ) -> dict:
        client = await self._get_client()
        payload = {
            "message": message,
            "target_ids": [str(target_id) for target_id in target_ids],
            "fire_at": fire_at.astimezone(timezone.utc).isoformat(),
            "channel_id": str(channel_id),
            "created_by": str(created_by),
            "done": False,
        }
        response = await client.table("reminders").insert(payload).execute()
        return response.data[0]

    async def get_pending(self) -> list[dict]:
        client = await self._get_client()
        now_utc = datetime.now(timezone.utc).isoformat()
        response = (
            await client.table("reminders")
            .select("*")
            .eq("done", False)
            .gt("fire_at", now_utc)
            .order("fire_at")
            .execute()
        )
        return list(response.data or [])

    async def mark_done(self, id: str) -> None:
        client = await self._get_client()
        await client.table("reminders").update({"done": True}).eq("id", id).execute()
```

- [ ] **Step 4: Run store tests**

Run:

```powershell
& "C:\Users\Irenko\Desktop\ssj-bot\venv\Scripts\python.exe" -m pytest tests/test_reminders_store.py -v
```

Expected: `3 passed`.

- [ ] **Step 5: Re-run parsing regression**

Run:

```powershell
& "C:\Users\Irenko\Desktop\ssj-bot\venv\Scripts\python.exe" -m pytest tests/test_reminder_parsing.py tests/test_reminders_store.py -v
```

Expected: `9 passed`.

---

### Task 3: reminders_cog.py — modal y comando /remind

**Files:**
- Create: `cogs/reminders_cog.py`
- Test: `tests/test_reminders_cog.py`

- [ ] **Step 1: Write the failing test for pure helper logic**

```python
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import discord
import pytest

from cogs.reminders_cog import (
    DISPLAY_TZ,
    build_reminder_confirmation_embed,
    build_reminder_delivery_embed,
    build_target_mentions,
    format_reminder_datetime,
    normalize_target_choice,
    resolve_target_ids,
    short_reminder_id,
)


def _sample_reminder() -> dict:
    fire_at = datetime(2026, 5, 25, 21, 0, tzinfo=ZoneInfo(DISPLAY_TZ)).astimezone(
        timezone.utc
    )
    return {
        "id": "12345678-abcd-efgh-ijkl-1234567890ab",
        "message": "ver la peli",
        "target_ids": ["111", "222"],
        "fire_at": fire_at,
        "channel_id": "333",
        "created_by": "444",
        "done": False,
    }


def test_normalize_target_choice_accepts_trimmed_input() -> None:
    assert normalize_target_choice(" Ambos ") == "ambos"


def test_normalize_target_choice_rejects_invalid_value() -> None:
    with pytest.raises(
        ValueError, match=r"Valor inválido en 'Para'\. Usa: yo, ella o ambos"
    ):
        normalize_target_choice("nosotros")


def test_resolve_target_ids_for_ambos() -> None:
    assert resolve_target_ids("ambos", "111", "222") == ["111", "222"]


def test_build_target_mentions_joins_ids() -> None:
    assert build_target_mentions(["111", "222"]) == "<@111> <@222>"


def test_short_reminder_id_uses_first_uuid_segment() -> None:
    assert short_reminder_id("12345678-abcd-efgh") == "12345678"


def test_format_reminder_datetime_uses_spanish_format() -> None:
    reminder = _sample_reminder()

    result = format_reminder_datetime(reminder["fire_at"], DISPLAY_TZ)

    assert result == "lunes 25 de mayo · 21:00"


def test_build_reminder_confirmation_embed_contains_fields() -> None:
    embed = build_reminder_confirmation_embed(_sample_reminder())

    assert isinstance(embed, discord.Embed)
    assert embed.title == "✅ Recordatorio creado"
    assert embed.fields[0].name == "📝 Mensaje"
    assert embed.fields[0].value == "ver la peli"
    assert embed.fields[1].name == "🕐 Cuándo"
    assert embed.fields[1].value == "lunes 25 de mayo · 21:00"
    assert embed.fields[2].name == "👥 Para"
    assert embed.fields[2].value == "<@111> <@222>"


def test_build_reminder_delivery_embed_contains_message() -> None:
    embed = build_reminder_delivery_embed(_sample_reminder())

    assert isinstance(embed, discord.Embed)
    assert embed.title == "⏰ Recordatorio"
    assert embed.description == "ver la peli"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
& "C:\Users\Irenko\Desktop\ssj-bot\venv\Scripts\python.exe" -m pytest tests/test_reminders_cog.py -v
```

Expected: `FAIL` porque `cogs/reminders_cog.py` todavía no existe.

- [ ] **Step 3: Write the modal, pure helpers, cancel button and `/remind`**

```python
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands

from utils.reminders_store import RemindersStore, parse_when
from utils.ui import COLOR_INFO, COLOR_SUCCESS, build_error_embed, build_info_embed

logger = logging.getLogger(__name__)
DISPLAY_TZ = "America/Santiago"
TARGET_CHOICE_ERROR = "Valor inválido en 'Para'. Usa: yo, ella o ambos"
MISSING_YO_ID_ERROR = "Falta configurar REMINDER_USER_YO_ID"
MISSING_ELLA_ID_ERROR = "Falta configurar REMINDER_USER_ELLA_ID"

SPANISH_WEEKDAYS = [
    "lunes",
    "martes",
    "miércoles",
    "jueves",
    "viernes",
    "sábado",
    "domingo",
]

SPANISH_MONTHS = {
    1: "enero",
    2: "febrero",
    3: "marzo",
    4: "abril",
    5: "mayo",
    6: "junio",
    7: "julio",
    8: "agosto",
    9: "septiembre",
    10: "octubre",
    11: "noviembre",
    12: "diciembre",
}


def coerce_utc_datetime(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        fire_at = value
    else:
        fire_at = datetime.fromisoformat(value.replace("Z", "+00:00"))

    if fire_at.tzinfo is None:
        fire_at = fire_at.replace(tzinfo=timezone.utc)

    return fire_at.astimezone(timezone.utc)


def normalize_target_choice(value: str) -> str:
    choice = value.strip().lower()
    if choice not in {"yo", "ella", "ambos"}:
        raise ValueError(TARGET_CHOICE_ERROR)
    return choice


def resolve_target_ids(
    choice: str, yo_id: str | None, ella_id: str | None
) -> list[str]:
    if choice == "yo":
        if not yo_id:
            raise ValueError(MISSING_YO_ID_ERROR)
        return [str(yo_id)]

    if choice == "ella":
        if not ella_id:
            raise ValueError(MISSING_ELLA_ID_ERROR)
        return [str(ella_id)]

    if not yo_id:
        raise ValueError(MISSING_YO_ID_ERROR)
    if not ella_id:
        raise ValueError(MISSING_ELLA_ID_ERROR)

    return [str(yo_id), str(ella_id)]


def build_target_mentions(target_ids: list[str]) -> str:
    return " ".join(f"<@{target_id}>" for target_id in target_ids)


def short_reminder_id(reminder_id: str) -> str:
    return reminder_id.split("-")[0][:8]


def format_reminder_datetime(fire_at: datetime | str, tz: str = DISPLAY_TZ) -> str:
    local_fire_at = coerce_utc_datetime(fire_at).astimezone(ZoneInfo(tz))
    weekday = SPANISH_WEEKDAYS[local_fire_at.weekday()]
    month = SPANISH_MONTHS[local_fire_at.month]
    return f"{weekday} {local_fire_at.day} de {month} · {local_fire_at:%H:%M}"


def build_reminder_confirmation_embed(reminder: dict) -> discord.Embed:
    embed = discord.Embed(
        title="✅ Recordatorio creado",
        colour=COLOR_SUCCESS,
    )
    embed.add_field(name="📝 Mensaje", value=reminder["message"], inline=False)
    embed.add_field(
        name="🕐 Cuándo",
        value=format_reminder_datetime(reminder["fire_at"], DISPLAY_TZ),
        inline=False,
    )
    embed.add_field(
        name="👥 Para",
        value=build_target_mentions(reminder["target_ids"]),
        inline=False,
    )
    return embed


def build_reminder_delivery_embed(reminder: dict) -> discord.Embed:
    return discord.Embed(
        title="⏰ Recordatorio",
        description=reminder["message"],
        colour=COLOR_INFO,
    )


class CancelReminderButton(discord.ui.Button):
    def __init__(self, reminder_id: str, label: str) -> None:
        super().__init__(
            label=label,
            emoji="🗑️",
            style=discord.ButtonStyle.danger,
            custom_id=f"reminder:cancel:{reminder_id}",
        )
        self.reminder_id = reminder_id

    async def callback(self, interaction: discord.Interaction) -> None:
        assert self.view is not None
        view = self.view
        assert isinstance(view, ReminderActionsView)

        await view.cog.cancel_reminder(self.reminder_id)

        for child in view.children:
            if child.custom_id == self.custom_id:
                child.disabled = True

        await interaction.response.edit_message(view=view)
        await interaction.followup.send(
            embed=build_info_embed(
                "🗑️ Recordatorio cancelado",
                f"Se canceló `{short_reminder_id(self.reminder_id)}`.",
            ),
            ephemeral=True,
        )


class ReminderActionsView(discord.ui.View):
    def __init__(self, cog: "Reminders", reminders: list[dict], owner_id: str) -> None:
        super().__init__(timeout=None)
        self.cog = cog
        self.owner_id = str(owner_id)

        for reminder in reminders:
            reminder_id = str(reminder["id"])
            label = "Cancelar"
            if len(reminders) > 1:
                label = f"Cancelar {short_reminder_id(reminder_id)}"
            self.add_item(CancelReminderButton(reminder_id, label))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if str(interaction.user.id) != self.owner_id:
            await interaction.response.send_message(
                embed=build_error_embed(
                    "Solo quien creó el recordatorio puede cancelarlo."
                ),
                ephemeral=True,
            )
            return False
        return True


class ReminderModal(discord.ui.Modal):
    def __init__(self, cog: "Reminders") -> None:
        super().__init__(title="Crear recordatorio")
        self.cog = cog

        self.message_input = discord.ui.TextInput(
            label="Mensaje",
            placeholder="ver la peli",
            required=True,
            max_length=300,
            style=discord.TextStyle.paragraph,
        )
        self.date_input = discord.ui.TextInput(
            label="Fecha",
            placeholder="hoy, mañana o 25/05",
            required=True,
            max_length=20,
        )
        self.time_input = discord.ui.TextInput(
            label="Hora",
            placeholder="21:00",
            required=True,
            max_length=5,
        )
        self.target_input = discord.ui.TextInput(
            label="Para",
            placeholder="yo, ella o ambos",
            required=True,
            max_length=10,
        )

        self.add_item(self.message_input)
        self.add_item(self.date_input)
        self.add_item(self.time_input)
        self.add_item(self.target_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.cog.handle_modal_submit(
            interaction=interaction,
            message=self.message_input.value,
            fecha=self.date_input.value,
            hora=self.time_input.value,
            para=self.target_input.value,
        )


class Reminders(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.supabase_url = os.getenv("SUPABASE_URL", "")
        self.supabase_key = os.getenv("SUPABASE_KEY", "")
        self.reminders_channel_id = os.getenv("REMINDERS_CHANNEL_ID")
        self.reminder_user_yo_id = os.getenv("REMINDER_USER_YO_ID")
        self.reminder_user_ella_id = os.getenv("REMINDER_USER_ELLA_ID")
        self.store = RemindersStore(self.supabase_url, self.supabase_key)

    def is_configured(self) -> bool:
        return bool(
            self.supabase_url and self.supabase_key and self.reminders_channel_id
        )

    @app_commands.command(name="remind", description="Crea un recordatorio")
    async def remind(self, interaction: discord.Interaction) -> None:
        if not self.is_configured():
            await interaction.response.send_message(
                embed=build_error_embed(
                    "Falta configuración de recordatorios en el bot."
                ),
                ephemeral=True,
            )
            return

        await interaction.response.send_modal(ReminderModal(self))

    async def handle_modal_submit(
        self,
        interaction: discord.Interaction,
        message: str,
        fecha: str,
        hora: str,
        para: str,
    ) -> None:
        try:
            fire_at = parse_when(fecha, hora, DISPLAY_TZ)
            target_choice = normalize_target_choice(para)
            target_ids = resolve_target_ids(
                target_choice,
                self.reminder_user_yo_id,
                self.reminder_user_ella_id,
            )
        except ValueError as exc:
            await interaction.response.send_message(
                embed=build_error_embed(str(exc)),
                ephemeral=True,
            )
            return

        try:
            reminder = await self.store.create(
                message=message.strip(),
                target_ids=target_ids,
                fire_at=fire_at,
                channel_id=str(self.reminders_channel_id),
                created_by=str(interaction.user.id),
            )
        except Exception:
            logger.exception("No se pudo guardar el recordatorio")
            await interaction.response.send_message(
                embed=build_error_embed(
                    "No se pudo guardar el recordatorio, intenta de nuevo"
                ),
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            embed=build_reminder_confirmation_embed(reminder),
            view=ReminderActionsView(
                self, [reminder], owner_id=str(interaction.user.id)
            ),
            ephemeral=True,
        )

    async def cancel_reminder(self, reminder_id: str) -> None:
        await self.store.mark_done(reminder_id)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Reminders(bot))
```

- [ ] **Step 4: Run helper tests**

Run:

```powershell
& "C:\Users\Irenko\Desktop\ssj-bot\venv\Scripts\python.exe" -m pytest tests/test_reminders_cog.py -v
```

Expected: `8 passed`.

---

### Task 4: reminders_cog.py — scheduler y disparo

**Files:**
- Modify: `cogs/reminders_cog.py`
- Create: `tests/test_reminders_scheduler.py`

- [ ] **Step 1: Write the failing scheduler tests**

```python
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from cogs import reminders_cog
from cogs.reminders_cog import Reminders


def _future_reminder() -> dict:
    return {
        "id": "12345678-abcd-efgh-ijkl-1234567890ab",
        "message": "ver la peli",
        "target_ids": ["111", "222"],
        "fire_at": (datetime.now(timezone.utc) + timedelta(seconds=60)).isoformat(),
        "channel_id": "333",
        "created_by": "444",
        "done": False,
    }


@pytest.mark.asyncio
async def test_schedule_reminder_delivers_message_and_marks_done(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bot = MagicMock()
    channel = MagicMock()
    channel.send = AsyncMock()
    bot.get_channel.return_value = channel

    cog = Reminders(bot)
    cog.store = MagicMock()
    cog.store.mark_done = AsyncMock()

    fake_sleep = AsyncMock()
    monkeypatch.setattr(reminders_cog.asyncio, "sleep", fake_sleep)

    reminder = _future_reminder()

    task = cog.schedule_reminder(reminder)
    assert task is not None

    await task

    fake_sleep.assert_awaited_once()
    channel.send.assert_awaited_once()
    assert channel.send.call_args.kwargs["content"] == "<@111> <@222>"
    assert channel.send.call_args.kwargs["embed"].title == "⏰ Recordatorio"
    cog.store.mark_done.assert_awaited_once_with(reminder["id"])


@pytest.mark.asyncio
async def test_cancel_reminder_cancels_task_and_marks_done() -> None:
    bot = MagicMock()
    cog = Reminders(bot)
    cog.store = MagicMock()
    cog.store.mark_done = AsyncMock()

    blocker = asyncio.Event()
    task = asyncio.create_task(blocker.wait())
    cog.tasks["rem-1"] = task

    await cog.cancel_reminder("rem-1")

    assert task.cancelled() is True
    cog.store.mark_done.assert_awaited_once_with("rem-1")
    assert "rem-1" not in cog.tasks


@pytest.mark.asyncio
async def test_cog_load_reschedules_pending_reminders() -> None:
    bot = MagicMock()
    cog = Reminders(bot)
    cog.supabase_url = "https://example.supabase.co"
    cog.supabase_key = "test-key"
    cog.reminders_channel_id = "333"
    cog.store = MagicMock()
    cog.store.get_pending = AsyncMock(return_value=[_future_reminder(), _future_reminder()])
    cog.schedule_reminder = MagicMock()

    await cog.cog_load()

    assert cog.schedule_reminder.call_count == 2
```

- [ ] **Step 2: Fix missing import in the test before running**

```python
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from cogs import reminders_cog
from cogs.reminders_cog import Reminders


def _future_reminder() -> dict:
    return {
        "id": "12345678-abcd-efgh-ijkl-1234567890ab",
        "message": "ver la peli",
        "target_ids": ["111", "222"],
        "fire_at": (datetime.now(timezone.utc) + timedelta(seconds=60)).isoformat(),
        "channel_id": "333",
        "created_by": "444",
        "done": False,
    }


@pytest.mark.asyncio
async def test_schedule_reminder_delivers_message_and_marks_done(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bot = MagicMock()
    channel = MagicMock()
    channel.send = AsyncMock()
    bot.get_channel.return_value = channel

    cog = Reminders(bot)
    cog.store = MagicMock()
    cog.store.mark_done = AsyncMock()

    fake_sleep = AsyncMock()
    monkeypatch.setattr(reminders_cog.asyncio, "sleep", fake_sleep)

    reminder = _future_reminder()

    task = cog.schedule_reminder(reminder)
    assert task is not None

    await task

    fake_sleep.assert_awaited_once()
    channel.send.assert_awaited_once()
    assert channel.send.call_args.kwargs["content"] == "<@111> <@222>"
    assert channel.send.call_args.kwargs["embed"].title == "⏰ Recordatorio"
    cog.store.mark_done.assert_awaited_once_with(reminder["id"])


@pytest.mark.asyncio
async def test_cancel_reminder_cancels_task_and_marks_done() -> None:
    bot = MagicMock()
    cog = Reminders(bot)
    cog.store = MagicMock()
    cog.store.mark_done = AsyncMock()

    blocker = asyncio.Event()
    task = asyncio.create_task(blocker.wait())
    cog.tasks["rem-1"] = task

    await cog.cancel_reminder("rem-1")

    assert task.cancelled() is True
    cog.store.mark_done.assert_awaited_once_with("rem-1")
    assert "rem-1" not in cog.tasks


@pytest.mark.asyncio
async def test_cog_load_reschedules_pending_reminders() -> None:
    bot = MagicMock()
    cog = Reminders(bot)
    cog.supabase_url = "https://example.supabase.co"
    cog.supabase_key = "test-key"
    cog.reminders_channel_id = "333"
    cog.store = MagicMock()
    cog.store.get_pending = AsyncMock(
        return_value=[_future_reminder(), _future_reminder()]
    )
    cog.schedule_reminder = MagicMock()

    await cog.cog_load()

    assert cog.schedule_reminder.call_count == 2
```

- [ ] **Step 3: Run test to verify it fails**

Run:

```powershell
& "C:\Users\Irenko\Desktop\ssj-bot\venv\Scripts\python.exe" -m pytest tests/test_reminders_scheduler.py -v
```

Expected: `FAIL` porque `Reminders` aún no tiene scheduler ni `cog_load()`.

- [ ] **Step 4: Add scheduler, reload-on-start and cancellation of in-memory tasks**

```python
from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands

from utils.reminders_store import RemindersStore, parse_when
from utils.ui import COLOR_INFO, COLOR_SUCCESS, build_error_embed, build_info_embed

logger = logging.getLogger(__name__)
DISPLAY_TZ = "America/Santiago"
TARGET_CHOICE_ERROR = "Valor inválido en 'Para'. Usa: yo, ella o ambos"
MISSING_YO_ID_ERROR = "Falta configurar REMINDER_USER_YO_ID"
MISSING_ELLA_ID_ERROR = "Falta configurar REMINDER_USER_ELLA_ID"

SPANISH_WEEKDAYS = [
    "lunes",
    "martes",
    "miércoles",
    "jueves",
    "viernes",
    "sábado",
    "domingo",
]

SPANISH_MONTHS = {
    1: "enero",
    2: "febrero",
    3: "marzo",
    4: "abril",
    5: "mayo",
    6: "junio",
    7: "julio",
    8: "agosto",
    9: "septiembre",
    10: "octubre",
    11: "noviembre",
    12: "diciembre",
}


def coerce_utc_datetime(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        fire_at = value
    else:
        fire_at = datetime.fromisoformat(value.replace("Z", "+00:00"))

    if fire_at.tzinfo is None:
        fire_at = fire_at.replace(tzinfo=timezone.utc)

    return fire_at.astimezone(timezone.utc)


def normalize_target_choice(value: str) -> str:
    choice = value.strip().lower()
    if choice not in {"yo", "ella", "ambos"}:
        raise ValueError(TARGET_CHOICE_ERROR)
    return choice


def resolve_target_ids(
    choice: str, yo_id: str | None, ella_id: str | None
) -> list[str]:
    if choice == "yo":
        if not yo_id:
            raise ValueError(MISSING_YO_ID_ERROR)
        return [str(yo_id)]

    if choice == "ella":
        if not ella_id:
            raise ValueError(MISSING_ELLA_ID_ERROR)
        return [str(ella_id)]

    if not yo_id:
        raise ValueError(MISSING_YO_ID_ERROR)
    if not ella_id:
        raise ValueError(MISSING_ELLA_ID_ERROR)

    return [str(yo_id), str(ella_id)]


def build_target_mentions(target_ids: list[str]) -> str:
    return " ".join(f"<@{target_id}>" for target_id in target_ids)


def short_reminder_id(reminder_id: str) -> str:
    return reminder_id.split("-")[0][:8]


def format_reminder_datetime(fire_at: datetime | str, tz: str = DISPLAY_TZ) -> str:
    local_fire_at = coerce_utc_datetime(fire_at).astimezone(ZoneInfo(tz))
    weekday = SPANISH_WEEKDAYS[local_fire_at.weekday()]
    month = SPANISH_MONTHS[local_fire_at.month]
    return f"{weekday} {local_fire_at.day} de {month} · {local_fire_at:%H:%M}"


def build_reminder_confirmation_embed(reminder: dict) -> discord.Embed:
    embed = discord.Embed(
        title="✅ Recordatorio creado",
        colour=COLOR_SUCCESS,
    )
    embed.add_field(name="📝 Mensaje", value=reminder["message"], inline=False)
    embed.add_field(
        name="🕐 Cuándo",
        value=format_reminder_datetime(reminder["fire_at"], DISPLAY_TZ),
        inline=False,
    )
    embed.add_field(
        name="👥 Para",
        value=build_target_mentions(reminder["target_ids"]),
        inline=False,
    )
    return embed


def build_reminder_delivery_embed(reminder: dict) -> discord.Embed:
    return discord.Embed(
        title="⏰ Recordatorio",
        description=reminder["message"],
        colour=COLOR_INFO,
    )


class CancelReminderButton(discord.ui.Button):
    def __init__(self, reminder_id: str, label: str) -> None:
        super().__init__(
            label=label,
            emoji="🗑️",
            style=discord.ButtonStyle.danger,
            custom_id=f"reminder:cancel:{reminder_id}",
        )
        self.reminder_id = reminder_id

    async def callback(self, interaction: discord.Interaction) -> None:
        assert self.view is not None
        view = self.view
        assert isinstance(view, ReminderActionsView)

        await view.cog.cancel_reminder(self.reminder_id)

        for child in view.children:
            if child.custom_id == self.custom_id:
                child.disabled = True

        await interaction.response.edit_message(view=view)
        await interaction.followup.send(
            embed=build_info_embed(
                "🗑️ Recordatorio cancelado",
                f"Se canceló `{short_reminder_id(self.reminder_id)}`.",
            ),
            ephemeral=True,
        )


class ReminderActionsView(discord.ui.View):
    def __init__(self, cog: "Reminders", reminders: list[dict], owner_id: str) -> None:
        super().__init__(timeout=None)
        self.cog = cog
        self.owner_id = str(owner_id)

        for reminder in reminders:
            reminder_id = str(reminder["id"])
            label = "Cancelar"
            if len(reminders) > 1:
                label = f"Cancelar {short_reminder_id(reminder_id)}"
            self.add_item(CancelReminderButton(reminder_id, label))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if str(interaction.user.id) != self.owner_id:
            await interaction.response.send_message(
                embed=build_error_embed(
                    "Solo quien creó el recordatorio puede cancelarlo."
                ),
                ephemeral=True,
            )
            return False
        return True


class ReminderModal(discord.ui.Modal):
    def __init__(self, cog: "Reminders") -> None:
        super().__init__(title="Crear recordatorio")
        self.cog = cog

        self.message_input = discord.ui.TextInput(
            label="Mensaje",
            placeholder="ver la peli",
            required=True,
            max_length=300,
            style=discord.TextStyle.paragraph,
        )
        self.date_input = discord.ui.TextInput(
            label="Fecha",
            placeholder="hoy, mañana o 25/05",
            required=True,
            max_length=20,
        )
        self.time_input = discord.ui.TextInput(
            label="Hora",
            placeholder="21:00",
            required=True,
            max_length=5,
        )
        self.target_input = discord.ui.TextInput(
            label="Para",
            placeholder="yo, ella o ambos",
            required=True,
            max_length=10,
        )

        self.add_item(self.message_input)
        self.add_item(self.date_input)
        self.add_item(self.time_input)
        self.add_item(self.target_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.cog.handle_modal_submit(
            interaction=interaction,
            message=self.message_input.value,
            fecha=self.date_input.value,
            hora=self.time_input.value,
            para=self.target_input.value,
        )


class Reminders(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.supabase_url = os.getenv("SUPABASE_URL", "")
        self.supabase_key = os.getenv("SUPABASE_KEY", "")
        self.reminders_channel_id = os.getenv("REMINDERS_CHANNEL_ID")
        self.reminder_user_yo_id = os.getenv("REMINDER_USER_YO_ID")
        self.reminder_user_ella_id = os.getenv("REMINDER_USER_ELLA_ID")
        self.store = RemindersStore(self.supabase_url, self.supabase_key)
        self.tasks: dict[str, asyncio.Task[None]] = {}

    def is_configured(self) -> bool:
        return bool(
            self.supabase_url and self.supabase_key and self.reminders_channel_id
        )

    async def cog_load(self) -> None:
        if not self.is_configured():
            logger.warning("Reminders deshabilitados: falta configuración")
            return

        try:
            pending = await self.store.get_pending()
        except Exception:
            logger.exception("No se pudieron recargar los recordatorios pendientes")
            return

        for reminder in pending:
            self.schedule_reminder(reminder)

    async def cog_unload(self) -> None:
        for task in self.tasks.values():
            task.cancel()
        self.tasks.clear()

    def _forget_task(self, reminder_id: str, task: asyncio.Task[None]) -> None:
        if self.tasks.get(reminder_id) is task:
            self.tasks.pop(reminder_id, None)

    def schedule_reminder(self, reminder: dict) -> asyncio.Task[None] | None:
        reminder_id = str(reminder["id"])
        fire_at = coerce_utc_datetime(reminder["fire_at"])
        delay = (fire_at - datetime.now(timezone.utc)).total_seconds()

        if delay <= 0:
            return None

        existing = self.tasks.pop(reminder_id, None)
        if existing is not None:
            existing.cancel()

        task = asyncio.create_task(
            self._run_scheduled_reminder(reminder, delay),
            name=f"reminder:{reminder_id}",
        )
        self.tasks[reminder_id] = task
        task.add_done_callback(
            lambda finished_task, rid=reminder_id: self._forget_task(rid, finished_task)
        )
        return task

    async def _run_scheduled_reminder(self, reminder: dict, delay: float) -> None:
        try:
            await asyncio.sleep(delay)
            await self._deliver_reminder(reminder)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Falló la ejecución del recordatorio %s", reminder["id"])

    async def _deliver_reminder(self, reminder: dict) -> None:
        channel = None
        channel_id = str(reminder["channel_id"])
        if channel_id.isdigit():
            channel = self.bot.get_channel(int(channel_id))
            if channel is None:
                with contextlib.suppress(
                    discord.HTTPException, discord.Forbidden, discord.NotFound
                ):
                    channel = await self.bot.fetch_channel(int(channel_id))

        if channel is None:
            logger.error("No se encontró el canal de recordatorios %s", channel_id)
            return

        await channel.send(
            content=build_target_mentions(reminder["target_ids"]),
            embed=build_reminder_delivery_embed(reminder),
        )
        await self.store.mark_done(str(reminder["id"]))

    @app_commands.command(name="remind", description="Crea un recordatorio")
    async def remind(self, interaction: discord.Interaction) -> None:
        if not self.is_configured():
            await interaction.response.send_message(
                embed=build_error_embed(
                    "Falta configuración de recordatorios en el bot."
                ),
                ephemeral=True,
            )
            return

        await interaction.response.send_modal(ReminderModal(self))

    async def handle_modal_submit(
        self,
        interaction: discord.Interaction,
        message: str,
        fecha: str,
        hora: str,
        para: str,
    ) -> None:
        try:
            fire_at = parse_when(fecha, hora, DISPLAY_TZ)
            target_choice = normalize_target_choice(para)
            target_ids = resolve_target_ids(
                target_choice,
                self.reminder_user_yo_id,
                self.reminder_user_ella_id,
            )
        except ValueError as exc:
            await interaction.response.send_message(
                embed=build_error_embed(str(exc)),
                ephemeral=True,
            )
            return

        try:
            reminder = await self.store.create(
                message=message.strip(),
                target_ids=target_ids,
                fire_at=fire_at,
                channel_id=str(self.reminders_channel_id),
                created_by=str(interaction.user.id),
            )
        except Exception:
            logger.exception("No se pudo guardar el recordatorio")
            await interaction.response.send_message(
                embed=build_error_embed(
                    "No se pudo guardar el recordatorio, intenta de nuevo"
                ),
                ephemeral=True,
            )
            return

        self.schedule_reminder(reminder)

        await interaction.response.send_message(
            embed=build_reminder_confirmation_embed(reminder),
            view=ReminderActionsView(
                self, [reminder], owner_id=str(interaction.user.id)
            ),
            ephemeral=True,
        )

    async def cancel_reminder(self, reminder_id: str) -> None:
        task = self.tasks.pop(reminder_id, None)
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

        await self.store.mark_done(reminder_id)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Reminders(bot))
```

- [ ] **Step 5: Run scheduler tests**

Run:

```powershell
& "C:\Users\Irenko\Desktop\ssj-bot\venv\Scripts\python.exe" -m pytest tests/test_reminders_scheduler.py -v
```

Expected: `3 passed`.

- [ ] **Step 6: Run previous reminders tests to avoid regression**

Run:

```powershell
& "C:\Users\Irenko\Desktop\ssj-bot\venv\Scripts\python.exe" -m pytest tests/test_reminder_parsing.py tests/test_reminders_store.py tests/test_reminders_cog.py tests/test_reminders_scheduler.py -v
```

Expected: all `passed`.

---

### Task 5: comando /reminders

**Files:**
- Modify: `cogs/reminders_cog.py`
- Create: `tests/test_reminders_listing.py`

- [ ] **Step 1: Write the failing listing tests**

```python
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import discord

from cogs.reminders_cog import (
    DISPLAY_TZ,
    ReminderActionsView,
    build_reminders_list_embed,
    filter_user_reminders,
)


def _reminder(reminder_id: str, created_by: str) -> dict:
    fire_at = datetime(2026, 5, 25, 21, 0, tzinfo=ZoneInfo(DISPLAY_TZ)).astimezone(
        timezone.utc
    )
    return {
        "id": reminder_id,
        "message": "ver la peli",
        "target_ids": ["111", "222"],
        "fire_at": fire_at,
        "channel_id": "333",
        "created_by": created_by,
        "done": False,
    }


def test_filter_user_reminders_keeps_only_current_user() -> None:
    reminders = [
        _reminder("12345678-abcd-0000", "42"),
        _reminder("87654321-abcd-0000", "99"),
    ]

    result = filter_user_reminders(reminders, user_id=42)

    assert [item["id"] for item in result] == ["12345678-abcd-0000"]


def test_build_reminders_list_embed_renders_ids_and_mentions() -> None:
    embed = build_reminders_list_embed(
        [
            _reminder("12345678-abcd-0000", "42"),
            _reminder("87654321-abcd-0000", "42"),
        ]
    )

    assert isinstance(embed, discord.Embed)
    assert embed.title == "⏰ Tus recordatorios"
    assert "12345678" in embed.description
    assert "87654321" in embed.description
    assert "<@111> <@222>" in embed.description


def test_build_reminders_list_embed_handles_empty_list() -> None:
    embed = build_reminders_list_embed([])

    assert embed.title == "⏰ Tus recordatorios"
    assert embed.description == "No tienes recordatorios pendientes."


def test_reminder_actions_view_creates_one_button_per_reminder() -> None:
    class DummyCog:
        async def cancel_reminder(self, reminder_id: str) -> None:
            return None

    view = ReminderActionsView(
        DummyCog(),
        [
            _reminder("12345678-abcd-0000", "42"),
            _reminder("87654321-abcd-0000", "42"),
        ],
        owner_id="42",
    )

    assert len(view.children) == 2
    assert view.children[0].label == "Cancelar 12345678"
    assert view.children[1].label == "Cancelar 87654321"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
& "C:\Users\Irenko\Desktop\ssj-bot\venv\Scripts\python.exe" -m pytest tests/test_reminders_listing.py -v
```

Expected: `FAIL` porque aún no existen `filter_user_reminders`, `build_reminders_list_embed` y `/reminders`.

- [ ] **Step 3: Add list helpers and `/reminders` command**

```python
from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands

from utils.reminders_store import RemindersStore, parse_when
from utils.ui import COLOR_INFO, COLOR_SUCCESS, build_error_embed, build_info_embed

logger = logging.getLogger(__name__)
DISPLAY_TZ = "America/Santiago"
TARGET_CHOICE_ERROR = "Valor inválido en 'Para'. Usa: yo, ella o ambos"
MISSING_YO_ID_ERROR = "Falta configurar REMINDER_USER_YO_ID"
MISSING_ELLA_ID_ERROR = "Falta configurar REMINDER_USER_ELLA_ID"

SPANISH_WEEKDAYS = [
    "lunes",
    "martes",
    "miércoles",
    "jueves",
    "viernes",
    "sábado",
    "domingo",
]

SPANISH_MONTHS = {
    1: "enero",
    2: "febrero",
    3: "marzo",
    4: "abril",
    5: "mayo",
    6: "junio",
    7: "julio",
    8: "agosto",
    9: "septiembre",
    10: "octubre",
    11: "noviembre",
    12: "diciembre",
}


def coerce_utc_datetime(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        fire_at = value
    else:
        fire_at = datetime.fromisoformat(value.replace("Z", "+00:00"))

    if fire_at.tzinfo is None:
        fire_at = fire_at.replace(tzinfo=timezone.utc)

    return fire_at.astimezone(timezone.utc)


def normalize_target_choice(value: str) -> str:
    choice = value.strip().lower()
    if choice not in {"yo", "ella", "ambos"}:
        raise ValueError(TARGET_CHOICE_ERROR)
    return choice


def resolve_target_ids(
    choice: str, yo_id: str | None, ella_id: str | None
) -> list[str]:
    if choice == "yo":
        if not yo_id:
            raise ValueError(MISSING_YO_ID_ERROR)
        return [str(yo_id)]

    if choice == "ella":
        if not ella_id:
            raise ValueError(MISSING_ELLA_ID_ERROR)
        return [str(ella_id)]

    if not yo_id:
        raise ValueError(MISSING_YO_ID_ERROR)
    if not ella_id:
        raise ValueError(MISSING_ELLA_ID_ERROR)

    return [str(yo_id), str(ella_id)]


def build_target_mentions(target_ids: list[str]) -> str:
    return " ".join(f"<@{target_id}>" for target_id in target_ids)


def short_reminder_id(reminder_id: str) -> str:
    return reminder_id.split("-")[0][:8]


def format_reminder_datetime(fire_at: datetime | str, tz: str = DISPLAY_TZ) -> str:
    local_fire_at = coerce_utc_datetime(fire_at).astimezone(ZoneInfo(tz))
    weekday = SPANISH_WEEKDAYS[local_fire_at.weekday()]
    month = SPANISH_MONTHS[local_fire_at.month]
    return f"{weekday} {local_fire_at.day} de {month} · {local_fire_at:%H:%M}"


def build_reminder_confirmation_embed(reminder: dict) -> discord.Embed:
    embed = discord.Embed(
        title="✅ Recordatorio creado",
        colour=COLOR_SUCCESS,
    )
    embed.add_field(name="📝 Mensaje", value=reminder["message"], inline=False)
    embed.add_field(
        name="🕐 Cuándo",
        value=format_reminder_datetime(reminder["fire_at"], DISPLAY_TZ),
        inline=False,
    )
    embed.add_field(
        name="👥 Para",
        value=build_target_mentions(reminder["target_ids"]),
        inline=False,
    )
    return embed


def build_reminder_delivery_embed(reminder: dict) -> discord.Embed:
    return discord.Embed(
        title="⏰ Recordatorio",
        description=reminder["message"],
        colour=COLOR_INFO,
    )


def filter_user_reminders(reminders: list[dict], user_id: int | str) -> list[dict]:
    return [
        reminder
        for reminder in reminders
        if str(reminder.get("created_by")) == str(user_id)
    ]


def build_reminders_list_embed(reminders: list[dict]) -> discord.Embed:
    if not reminders:
        return discord.Embed(
            title="⏰ Tus recordatorios",
            description="No tienes recordatorios pendientes.",
            colour=COLOR_INFO,
        )

    lines = []
    for reminder in reminders:
        lines.append(
            f"**{short_reminder_id(str(reminder['id']))}** · {reminder['message']}\n"
            f"{format_reminder_datetime(reminder['fire_at'], DISPLAY_TZ)} · "
            f"{build_target_mentions(reminder['target_ids'])}"
        )

    return discord.Embed(
        title="⏰ Tus recordatorios",
        description="\n\n".join(lines),
        colour=COLOR_INFO,
    )


class CancelReminderButton(discord.ui.Button):
    def __init__(self, reminder_id: str, label: str) -> None:
        super().__init__(
            label=label,
            emoji="🗑️",
            style=discord.ButtonStyle.danger,
            custom_id=f"reminder:cancel:{reminder_id}",
        )
        self.reminder_id = reminder_id

    async def callback(self, interaction: discord.Interaction) -> None:
        assert self.view is not None
        view = self.view
        assert isinstance(view, ReminderActionsView)

        await view.cog.cancel_reminder(self.reminder_id)

        for child in view.children:
            if child.custom_id == self.custom_id:
                child.disabled = True

        await interaction.response.edit_message(view=view)
        await interaction.followup.send(
            embed=build_info_embed(
                "🗑️ Recordatorio cancelado",
                f"Se canceló `{short_reminder_id(self.reminder_id)}`.",
            ),
            ephemeral=True,
        )


class ReminderActionsView(discord.ui.View):
    def __init__(self, cog: "Reminders", reminders: list[dict], owner_id: str) -> None:
        super().__init__(timeout=None)
        self.cog = cog
        self.owner_id = str(owner_id)

        for reminder in reminders:
            reminder_id = str(reminder["id"])
            label = "Cancelar"
            if len(reminders) > 1:
                label = f"Cancelar {short_reminder_id(reminder_id)}"
            self.add_item(CancelReminderButton(reminder_id, label))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if str(interaction.user.id) != self.owner_id:
            await interaction.response.send_message(
                embed=build_error_embed(
                    "Solo quien creó el recordatorio puede cancelarlo."
                ),
                ephemeral=True,
            )
            return False
        return True


class ReminderModal(discord.ui.Modal):
    def __init__(self, cog: "Reminders") -> None:
        super().__init__(title="Crear recordatorio")
        self.cog = cog

        self.message_input = discord.ui.TextInput(
            label="Mensaje",
            placeholder="ver la peli",
            required=True,
            max_length=300,
            style=discord.TextStyle.paragraph,
        )
        self.date_input = discord.ui.TextInput(
            label="Fecha",
            placeholder="hoy, mañana o 25/05",
            required=True,
            max_length=20,
        )
        self.time_input = discord.ui.TextInput(
            label="Hora",
            placeholder="21:00",
            required=True,
            max_length=5,
        )
        self.target_input = discord.ui.TextInput(
            label="Para",
            placeholder="yo, ella o ambos",
            required=True,
            max_length=10,
        )

        self.add_item(self.message_input)
        self.add_item(self.date_input)
        self.add_item(self.time_input)
        self.add_item(self.target_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.cog.handle_modal_submit(
            interaction=interaction,
            message=self.message_input.value,
            fecha=self.date_input.value,
            hora=self.time_input.value,
            para=self.target_input.value,
        )


class Reminders(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.supabase_url = os.getenv("SUPABASE_URL", "")
        self.supabase_key = os.getenv("SUPABASE_KEY", "")
        self.reminders_channel_id = os.getenv("REMINDERS_CHANNEL_ID")
        self.reminder_user_yo_id = os.getenv("REMINDER_USER_YO_ID")
        self.reminder_user_ella_id = os.getenv("REMINDER_USER_ELLA_ID")
        self.store = RemindersStore(self.supabase_url, self.supabase_key)
        self.tasks: dict[str, asyncio.Task[None]] = {}

    def is_configured(self) -> bool:
        return bool(
            self.supabase_url and self.supabase_key and self.reminders_channel_id
        )

    async def cog_load(self) -> None:
        if not self.is_configured():
            logger.warning("Reminders deshabilitados: falta configuración")
            return

        try:
            pending = await self.store.get_pending()
        except Exception:
            logger.exception("No se pudieron recargar los recordatorios pendientes")
            return

        for reminder in pending:
            self.schedule_reminder(reminder)

    async def cog_unload(self) -> None:
        for task in self.tasks.values():
            task.cancel()
        self.tasks.clear()

    def _forget_task(self, reminder_id: str, task: asyncio.Task[None]) -> None:
        if self.tasks.get(reminder_id) is task:
            self.tasks.pop(reminder_id, None)

    def schedule_reminder(self, reminder: dict) -> asyncio.Task[None] | None:
        reminder_id = str(reminder["id"])
        fire_at = coerce_utc_datetime(reminder["fire_at"])
        delay = (fire_at - datetime.now(timezone.utc)).total_seconds()

        if delay <= 0:
            return None

        existing = self.tasks.pop(reminder_id, None)
        if existing is not None:
            existing.cancel()

        task = asyncio.create_task(
            self._run_scheduled_reminder(reminder, delay),
            name=f"reminder:{reminder_id}",
        )
        self.tasks[reminder_id] = task
        task.add_done_callback(
            lambda finished_task, rid=reminder_id: self._forget_task(rid, finished_task)
        )
        return task

    async def _run_scheduled_reminder(self, reminder: dict, delay: float) -> None:
        try:
            await asyncio.sleep(delay)
            await self._deliver_reminder(reminder)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Falló la ejecución del recordatorio %s", reminder["id"])

    async def _deliver_reminder(self, reminder: dict) -> None:
        channel = None
        channel_id = str(reminder["channel_id"])
        if channel_id.isdigit():
            channel = self.bot.get_channel(int(channel_id))
            if channel is None:
                with contextlib.suppress(
                    discord.HTTPException, discord.Forbidden, discord.NotFound
                ):
                    channel = await self.bot.fetch_channel(int(channel_id))

        if channel is None:
            logger.error("No se encontró el canal de recordatorios %s", channel_id)
            return

        await channel.send(
            content=build_target_mentions(reminder["target_ids"]),
            embed=build_reminder_delivery_embed(reminder),
        )
        await self.store.mark_done(str(reminder["id"]))

    @app_commands.command(name="remind", description="Crea un recordatorio")
    async def remind(self, interaction: discord.Interaction) -> None:
        if not self.is_configured():
            await interaction.response.send_message(
                embed=build_error_embed(
                    "Falta configuración de recordatorios en el bot."
                ),
                ephemeral=True,
            )
            return

        await interaction.response.send_modal(ReminderModal(self))

    @app_commands.command(
        name="reminders", description="Muestra tus recordatorios pendientes"
    )
    async def show_reminders(self, interaction: discord.Interaction) -> None:
        if not self.is_configured():
            await interaction.response.send_message(
                embed=build_error_embed(
                    "Falta configuración de recordatorios en el bot."
                ),
                ephemeral=True,
            )
            return

        try:
            pending = await self.store.get_pending()
        except Exception:
            logger.exception("No se pudieron listar los recordatorios")
            await interaction.response.send_message(
                embed=build_error_embed(
                    "No se pudo cargar la lista de recordatorios."
                ),
                ephemeral=True,
            )
            return

        reminders = filter_user_reminders(pending, interaction.user.id)
        if not reminders:
            await interaction.response.send_message(
                embed=build_reminders_list_embed([]),
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            embed=build_reminders_list_embed(reminders),
            view=ReminderActionsView(
                self, reminders, owner_id=str(interaction.user.id)
            ),
            ephemeral=True,
        )

    async def handle_modal_submit(
        self,
        interaction: discord.Interaction,
        message: str,
        fecha: str,
        hora: str,
        para: str,
    ) -> None:
        try:
            fire_at = parse_when(fecha, hora, DISPLAY_TZ)
            target_choice = normalize_target_choice(para)
            target_ids = resolve_target_ids(
                target_choice,
                self.reminder_user_yo_id,
                self.reminder_user_ella_id,
            )
        except ValueError as exc:
            await interaction.response.send_message(
                embed=build_error_embed(str(exc)),
                ephemeral=True,
            )
            return

        try:
            reminder = await self.store.create(
                message=message.strip(),
                target_ids=target_ids,
                fire_at=fire_at,
                channel_id=str(self.reminders_channel_id),
                created_by=str(interaction.user.id),
            )
        except Exception:
            logger.exception("No se pudo guardar el recordatorio")
            await interaction.response.send_message(
                embed=build_error_embed(
                    "No se pudo guardar el recordatorio, intenta de nuevo"
                ),
                ephemeral=True,
            )
            return

        self.schedule_reminder(reminder)

        await interaction.response.send_message(
            embed=build_reminder_confirmation_embed(reminder),
            view=ReminderActionsView(
                self, [reminder], owner_id=str(interaction.user.id)
            ),
            ephemeral=True,
        )

    async def cancel_reminder(self, reminder_id: str) -> None:
        task = self.tasks.pop(reminder_id, None)
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

        await self.store.mark_done(reminder_id)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Reminders(bot))
```

- [ ] **Step 4: Run listing tests**

Run:

```powershell
& "C:\Users\Irenko\Desktop\ssj-bot\venv\Scripts\python.exe" -m pytest tests/test_reminders_listing.py -v
```

Expected: `4 passed`.

- [ ] **Step 5: Re-run all reminders-focused tests**

Run:

```powershell
& "C:\Users\Irenko\Desktop\ssj-bot\venv\Scripts\python.exe" -m pytest tests/test_reminder_parsing.py tests/test_reminders_store.py tests/test_reminders_cog.py tests/test_reminders_scheduler.py tests/test_reminders_listing.py -v
```

Expected: all `passed`.

---

### Task 6: integración en bot.py y .env.example

**Files:**
- Modify: `bot.py`
- Modify: `.env.example`
- Modify: `requirements.txt`
- Modify: `tests/test_music_control_view.py`

- [ ] **Step 1: Add the dependency**

```text
aiohappyeyeballs==2.4.3
aiohttp==3.10.10
aiosignal==1.3.1
attrs==24.2.0
audioop-lts==0.2.1; python_version >= "3.13"
Brotli==1.1.0
certifi==2024.8.30
cffi==1.17.1
charset-normalizer==3.4.0
colorama==0.4.6
davey==0.1.5
discord.py[voice]==2.7.1
frozenlist==1.5.0
idna==3.10
multidict==6.1.0
mutagen==1.47.0
propcache==0.2.0
pycparser==2.22
pycryptodomex==3.21.0
PyNaCl==1.5.0
python-dotenv==1.0.1
requests==2.32.3
supabase>=2.0.0
urllib3==2.2.3
websockets==13.1
yarl==1.17.1
yt-dlp==2026.1.31
yt-dlp-ejs==0.4.0
tzdata
```

- [ ] **Step 2: Update `.env.example`**

```env
DISCORD_TOKEN=your_bot_token_here
LOG_LEVEL=INFO

# Comma-separated guild IDs where slash commands are registered.
# Leave empty for global sync (takes up to 1 hour to propagate).
# Get a guild ID: enable Discord Developer Mode -> right-click server -> Copy ID.
GUILD_IDS=

# Supabase configuration for reminders.
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_KEY=tu-anon-key

# Discord channel where reminders are delivered.
REMINDERS_CHANNEL_ID=123456789012345678

# Discord user IDs used by the "Para" field.
REMINDER_USER_YO_ID=111111111111111111
REMINDER_USER_ELLA_ID=222222222222222222
```

- [ ] **Step 3: Move cog loading into `setup_hook`**

```python
import os
import sys
import asyncio
import logging
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from utils.ui import build_error_embed, MusicControlView

# Load environment variables from the .env file
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")


def _parse_guild_ids(raw: str | None) -> list[int]:
    """Parse comma-separated guild IDs from env var. Skips invalid tokens."""
    if not raw:
        return []
    out: list[int] = []
    for piece in raw.split(","):
        piece = piece.strip()
        if not piece:
            continue
        try:
            out.append(int(piece))
        except ValueError:
            logging.getLogger("ssj-bot").warning(
                "Ignorando GUILD_IDS inválido: %r", piece
            )
    return out


GUILD_IDS = _parse_guild_ids(os.getenv("GUILD_IDS"))

# Configure logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("ssj-bot")

# Set intents to receive message content and member events
intents = discord.Intents.all()


class SSJBot(commands.Bot):
    async def setup_hook(self):
        self.add_view(MusicControlView(bot=self))
        await self.load_extension("cogs.music_cog")
        await self.load_extension("cogs.reminders_cog")


# Initialize the bot with a command prefix and intents
bot = SSJBot(command_prefix=commands.when_mentioned, intents=intents)


@bot.event
async def on_ready():
    """Event triggered when the bot has connected to Discord."""
    logger.info(f"{bot.user.name} conectado en {len(bot.guilds)} servidor(es).")
    await _sync_app_commands()


async def _sync_app_commands():
    """Sync slash commands. Per-guild if GUILD_IDS set, else global.

    Hybrid commands register globally in bot.tree by default. To make
    them appear instantly per-guild we must copy_global_to(guild=X)
    before sync(guild=X). Otherwise the per-guild sync registers an
    empty list silently and users see no slash commands.
    """
    if GUILD_IDS:
        success = 0
        for gid in GUILD_IDS:
            try:
                guild_obj = discord.Object(id=gid)
                bot.tree.copy_global_to(guild=guild_obj)
                synced = await bot.tree.sync(guild=guild_obj)
                logger.info("Sync guild %s: %d comandos.", gid, len(synced))
                success += 1
            except Exception as e:
                logger.warning("Sync falló para guild %s: %s", gid, e)
        logger.info(
            "Slash commands sincronizados en %d/%d guild(s).",
            success,
            len(GUILD_IDS),
        )
    else:
        try:
            synced = await bot.tree.sync()
            logger.info(
                "Slash commands sincronizados globalmente: %d comandos "
                "(puede tardar hasta 1h en aparecer).",
                len(synced),
            )
        except Exception as e:
            logger.error("Sync global falló: %s", e)


@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError,
):
    """Catch unhandled errors from slash commands."""
    logger.error(
        "Error en slash command %s: %s",
        interaction.command.name if interaction.command else "?",
        error,
        exc_info=True,
    )
    embed = build_error_embed("Ocurrió un error inesperado.")
    try:
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)
    except Exception as e:
        logger.error("No pude enviar mensaje de error al usuario: %s", e)


async def handle_command_error(ctx, error):
    """Global handler for prefix/mention command errors.

    Silences CommandNotFound (typos like !d, !aaa) to avoid log spam now
    that the prefix is disabled. Sends user-friendly embeds for known
    errors and a generic message for unexpected ones.
    """
    if isinstance(error, commands.CommandNotFound):
        return

    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(embed=build_error_embed(f"Falta el argumento: `{error.param.name}`"))
        return

    if isinstance(error, commands.BadArgument):
        await ctx.send(embed=build_error_embed("Argumento inválido."))
        return

    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(embed=build_error_embed(f"Comando en cooldown. Intenta en {error.retry_after:.1f}s"))
        return

    if isinstance(error, commands.CommandInvokeError):
        await ctx.send(embed=build_error_embed("Ha ocurrido un error inesperado."))
        return

    await ctx.send(embed=build_error_embed("Ha ocurrido un error inesperado."))


bot.add_listener(handle_command_error, "on_command_error")


async def main():
    if not TOKEN:
        logger.error("DISCORD_TOKEN no está configurado en el entorno.")
        sys.exit(1)

    logger.info("Iniciando bot...")
    await bot.start(TOKEN)


if __name__ == "__main__":
    sys.stdout.reconfigure(line_buffering=True)
    asyncio.run(main())
```

- [ ] **Step 4: Update the existing setup-hook test**

```python
from unittest.mock import AsyncMock, MagicMock, call, patch

import discord
import pytest

from bot import bot
from utils.ui import MusicControlView, make_music_control_view


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


def make_music_cog():
    music_cog = MagicMock()
    music_cog._state = MagicMock(
        return_value=MagicMock(queue=[{"title": "Song 1"}], actual_song="Song 0")
    )
    music_cog.update_activity = MagicMock()
    music_cog._cleanup_state = MagicMock()
    return music_cog


def make_bot(music_cog=None):
    bot_mock = MagicMock()
    if music_cog is None:
        music_cog = make_music_cog()
    bot_mock.get_cog = MagicMock(return_value=music_cog)
    return bot_mock


def test_music_control_view_has_expected_buttons():
    view = MusicControlView(bot=make_bot())

    custom_ids = [child.custom_id for child in view.children]
    assert custom_ids == ["pause_resume", "skip", "stop", "view_queue", "shuffle"]


def test_factory_returns_fresh_instance():
    bot_mock = make_bot()
    v1 = make_music_control_view(bot_mock)
    v2 = make_music_control_view(bot_mock)
    assert v1 is not v2
    assert isinstance(v1, MusicControlView)
    assert isinstance(v2, MusicControlView)


def test_factory_sets_paused_state():
    bot_mock = make_bot()
    view = make_music_control_view(bot_mock, paused=True)
    pause_button = next(child for child in view.children if child.custom_id == "pause_resume")
    assert str(pause_button.emoji) == "▶️"


def test_factory_sets_disabled_state():
    bot_mock = make_bot()
    view = make_music_control_view(bot_mock, disabled=True)
    assert all(child.disabled for child in view.children)


@pytest.mark.asyncio
async def test_pause_resume_button_pauses_and_edits_message_with_fresh_view():
    bot_mock = make_bot()
    view = MusicControlView(bot=bot_mock)
    interaction = make_interaction()
    interaction.guild.voice_client.is_paused.return_value = False
    interaction.guild.voice_client.is_playing.return_value = True

    button = next(child for child in view.children if child.custom_id == "pause_resume")
    await button.callback(interaction)

    interaction.guild.voice_client.pause.assert_called_once()
    assert str(button.emoji) == "⏸"
    interaction.message.edit.assert_awaited_once()
    interaction.response.send_message.assert_awaited_once()
    bot_mock.get_cog.return_value.update_activity.assert_called_once_with(interaction.guild)

    _, kwargs = interaction.message.edit.call_args
    fresh_view = kwargs["view"]
    pause_button = next(
        child for child in fresh_view.children if child.custom_id == "pause_resume"
    )
    assert str(pause_button.emoji) == "▶️"


@pytest.mark.asyncio
async def test_skip_button_skips_and_updates_activity():
    bot_mock = make_bot()
    view = MusicControlView(bot=bot_mock)
    interaction = make_interaction()
    interaction.guild.voice_client.is_playing.return_value = True

    button = next(child for child in view.children if child.custom_id == "skip")
    await button.callback(interaction)

    interaction.guild.voice_client.stop.assert_called_once()
    interaction.response.send_message.assert_awaited_once()
    bot_mock.get_cog.return_value.update_activity.assert_called_once_with(interaction.guild)


@pytest.mark.asyncio
async def test_stop_button_disables_all_buttons_and_edits_message():
    bot_mock = make_bot()
    view = MusicControlView(bot=bot_mock)
    interaction = make_interaction()
    interaction.guild.voice_client.is_connected.return_value = True
    interaction.guild.voice_client.is_playing.return_value = True
    interaction.guild.voice_client.disconnect = AsyncMock()

    button = next(child for child in view.children if child.custom_id == "stop")
    await button.callback(interaction)

    assert not any(child.disabled for child in view.children)
    interaction.message.edit.assert_awaited_once()
    interaction.guild.voice_client.disconnect.assert_awaited_once()
    bot_mock.get_cog.return_value._cleanup_state.assert_called_once_with(interaction.guild.id)

    _, kwargs = interaction.message.edit.call_args
    fresh_view = kwargs["view"]
    assert all(child.disabled for child in fresh_view.children)


@pytest.mark.asyncio
async def test_view_queue_button_sends_ephemeral_embed():
    bot_mock = make_bot()
    view = MusicControlView(bot=bot_mock)
    interaction = make_interaction()

    button = next(child for child in view.children if child.custom_id == "view_queue")
    await button.callback(interaction)

    _, kwargs = interaction.response.send_message.call_args
    assert kwargs["ephemeral"] is True
    assert kwargs["embed"].title == "📋 Cola de reproducción"


@pytest.mark.asyncio
async def test_shuffle_button_warns_when_queue_has_zero_items():
    bot_mock = make_bot()
    bot_mock.get_cog.return_value._state.return_value = MagicMock(queue=[])
    view = MusicControlView(bot=bot_mock)
    interaction = make_interaction()

    button = next(child for child in view.children if child.custom_id == "shuffle")
    await button.callback(interaction)

    interaction.response.send_message.assert_awaited_once()
    _, kwargs = interaction.response.send_message.call_args
    assert kwargs["ephemeral"] is True
    assert "suficientes" in kwargs["embed"].description.lower()


@pytest.mark.asyncio
async def test_shuffle_button_warns_when_queue_has_one_item():
    bot_mock = make_bot()
    bot_mock.get_cog.return_value._state.return_value = MagicMock(queue=[{"title": "Song 1"}])
    view = MusicControlView(bot=bot_mock)
    interaction = make_interaction()

    button = next(child for child in view.children if child.custom_id == "shuffle")
    await button.callback(interaction)

    interaction.response.send_message.assert_awaited_once()
    _, kwargs = interaction.response.send_message.call_args
    assert kwargs["ephemeral"] is True
    assert "suficientes" in kwargs["embed"].description.lower()


@pytest.mark.asyncio
async def test_shuffle_button_shuffles_queue_with_two_or_more_items():
    bot_mock = make_bot()
    queue = [{"title": "Song 1"}, {"title": "Song 2"}, {"title": "Song 3"}]
    bot_mock.get_cog.return_value._state.return_value = MagicMock(queue=queue)
    view = MusicControlView(bot=bot_mock)
    interaction = make_interaction()

    with patch("random.shuffle") as mock_shuffle:
        button = next(child for child in view.children if child.custom_id == "shuffle")
        await button.callback(interaction)

    mock_shuffle.assert_called_once_with(queue)
    bot_mock.get_cog.return_value.update_activity.assert_called_once_with(interaction.guild)
    interaction.response.send_message.assert_awaited_once()
    _, kwargs = interaction.response.send_message.call_args
    assert kwargs["ephemeral"] is True
    assert kwargs["embed"].title == "🔀 Shuffle"


@pytest.mark.asyncio
async def test_button_callbacks_work_without_ctx():
    bot_mock = make_bot()
    view = MusicControlView(bot=bot_mock)

    interaction = make_interaction()
    interaction.guild.voice_client.is_paused.return_value = False
    interaction.guild.voice_client.is_playing.return_value = True

    button = next(child for child in view.children if child.custom_id == "pause_resume")
    await button.callback(interaction)

    interaction.guild.voice_client.pause.assert_called_once()
    bot_mock.get_cog.return_value.update_activity.assert_called_once_with(interaction.guild)


@pytest.mark.asyncio
async def test_bot_add_view_called_during_setup_hook():
    with patch.object(bot, "add_view") as mock_add_view, \
         patch.object(bot, "get_cog", return_value=make_music_cog()), \
         patch.object(bot, "load_extension", new=AsyncMock()) as mock_load_extension:
        await bot.setup_hook()

    mock_add_view.assert_called_once()
    view = mock_add_view.call_args[0][0]
    assert isinstance(view, MusicControlView)
    mock_load_extension.assert_has_awaits(
        [call("cogs.music_cog"), call("cogs.reminders_cog")]
    )
```

- [ ] **Step 5: Run the setup-hook test only**

Run:

```powershell
& "C:\Users\Irenko\Desktop\ssj-bot\venv\Scripts\python.exe" -m pytest tests/test_music_control_view.py -v
```

Expected: all tests in that file `passed`.

- [ ] **Step 6: Run the full suite smoke test**

Run:

```powershell
& "C:\Users\Irenko\Desktop\ssj-bot\venv\Scripts\python.exe" -m pytest tests/ -v
```

Expected: suite completa en `PASSED`.

---

## Riesgos y mitigaciones

- **`supabase` aún no está instalado en el entorno al empezar Tasks 1-5** — el import lazy en `utils/reminders_store.py` evita que falle el import del módulo antes de Task 6.
- **Discord limita componentes por mensaje** — `ReminderActionsView` sirve bien para pocos recordatorios; validar manualmente con varios registros y documentar si se necesita paginación después.
- **Fechas locales vs UTC** — centralizar parseo en `parse_when()` y formato en `format_reminder_datetime()`; no duplicar conversión horaria en el cog.
- **Botones de cancelar concurrentes** — `cancel_reminder()` elimina primero el task del dict y luego hace `mark_done`, reduciendo doble ejecución.
- **Canal de recordatorios inválido o ausente** — `_deliver_reminder()` registra error y evita crash del scheduler.
- **Reinicio del bot** — `cog_load()` rehidrata recordatorios pendientes desde Supabase al cargar el cog.

## Tests recomendados

- `tests/test_reminder_parsing.py` — hoy, mañana, `dd/mm`, hora inválida, fecha inválida, fecha pasada.
- `tests/test_reminders_store.py` — `create`, `get_pending`, `mark_done` con mocks del cliente async.
- `tests/test_reminders_cog.py` — helpers puros del cog: normalización, menciones, formateo, embeds.
- `tests/test_reminders_scheduler.py` — creación de `Task`, disparo, cancelación y recarga en `cog_load`.
- `tests/test_reminders_listing.py` — filtrado por usuario, embed de `/reminders` y botones por recordatorio.
- `tests/test_music_control_view.py` — asegurar que `setup_hook()` ahora registra la view existente y carga ambos cogs.

## Verificación final

- Verificar branch antes de tocar código:

```powershell
git branch --show-current
```

Expected: `docs/reminders-design-spec`

- Ejecutar tests de reminders:

```powershell
& "C:\Users\Irenko\Desktop\ssj-bot\venv\Scripts\python.exe" -m pytest tests/test_reminder_parsing.py tests/test_reminders_store.py tests/test_reminders_cog.py tests/test_reminders_scheduler.py tests/test_reminders_listing.py -v
```

- Ejecutar smoke test completo:

```powershell
& "C:\Users\Irenko\Desktop\ssj-bot\venv\Scripts\python.exe" -m pytest tests/ -v
```

## Fuera de alcance (lo que este plan NO cubre)

- Recordatorios recurrentes.
- Editar recordatorios existentes.
- Integración con la app externa de to-do list.
- Soporte multi-servidor más allá del canal configurado en `.env`.
- UI avanzada para paginar más de 25 botones de cancelación en `/reminders`.

Si quieres, en el siguiente paso puedo convertir esto en una versión más compacta lista para pegar directamente en el archivo Markdown.
</task_result>