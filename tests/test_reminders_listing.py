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
