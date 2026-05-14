from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
import asyncio
from typing import Any

REMINDER_DATE_ERROR = "Fecha inválida. Usa: hoy, mañana, o dd/mm"
REMINDER_TIME_ERROR = "Hora inválida. Formato: hh:mm (ej: 21:00)"
REMINDER_PAST_ERROR = "Esa fecha ya pasó 😅"


def _now_in_timezone(tz: str) -> datetime:
    return datetime.now(ZoneInfo(tz))


def _parse_date_token(fecha: str, now_local: datetime) -> date:
    token = fecha.strip().lower()

    if token == "hoy":
        return now_local.date()

    if token == "mañana":
        return (now_local + timedelta(days=1)).date()

    parts = token.split("/")
    if len(parts) != 2:
        raise ValueError(REMINDER_DATE_ERROR)

    if not (len(parts[0]) == 2 and len(parts[1]) == 2):
        raise ValueError(REMINDER_DATE_ERROR)

    try:
        day = int(parts[0])
        month = int(parts[1])
    except ValueError as exc:
        raise ValueError(REMINDER_DATE_ERROR) from exc

    try:
        date_this_year = datetime(now_local.year, month, day, tzinfo=now_local.tzinfo).date()
    except ValueError as exc:
        raise ValueError(REMINDER_DATE_ERROR) from exc

    if date_this_year < now_local.date():
        return datetime(now_local.year + 1, month, day, tzinfo=now_local.tzinfo).date()
    return date_this_year


def _parse_time_token(hora: str) -> time:
    token = hora.strip()
    parts = token.split(":")
    if len(parts) != 2:
        raise ValueError(REMINDER_TIME_ERROR)

    if not (len(parts[0]) == 2 and len(parts[1]) == 2):
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
        if fire_at.tzinfo is None:
            raise ValueError("fire_at debe ser timezone-aware")

        client = await self._get_client()
        payload = {
            "message": message,
            "target_ids": [str(t) for t in target_ids],
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

    async def mark_done(self, reminder_id: str) -> None:
        client = await self._get_client()
        await (
            client.table("reminders")
            .update({"done": True})
            .eq("id", reminder_id)
            .execute()
        )
