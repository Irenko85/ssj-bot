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
