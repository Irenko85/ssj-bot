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
            task = self.schedule_reminder(reminder)
            if task is None:
                # Recordatorio vencido: entregar de inmediato
                asyncio.create_task(
                    self._deliver_reminder(reminder),
                    name=f"reminder:overdue:{reminder['id']}",
                )

    def cog_unload(self) -> None:
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
        clean_message = message.strip()
        if not clean_message:
            await interaction.response.send_message(
                embed=build_error_embed("El mensaje no puede estar vacío."),
                ephemeral=True,
            )
            return

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
                message=clean_message,
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
