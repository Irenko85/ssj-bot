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


@pytest.mark.asyncio
async def test_handle_modal_submit_rejects_blank_message() -> None:
    from unittest.mock import AsyncMock, MagicMock
    from cogs.reminders_cog import Reminders

    bot = MagicMock()
    cog = Reminders(bot)
    cog.reminder_user_yo_id = "111"
    cog.reminder_user_ella_id = "222"
    cog.store = MagicMock()
    cog.store.create = AsyncMock()

    interaction = MagicMock()
    interaction.response = MagicMock()
    interaction.response.send_message = AsyncMock()

    await cog.handle_modal_submit(
        interaction=interaction,
        message="   ",   # solo espacios
        fecha="hoy",
        hora="23:59",
        para="yo",
    )

    # Debe haber enviado mensaje de error efímero
    interaction.response.send_message.assert_awaited_once()
    call_kwargs = interaction.response.send_message.call_args.kwargs
    assert call_kwargs.get("ephemeral") is True

    # NO debe haber llamado a store.create
    cog.store.create.assert_not_awaited()
