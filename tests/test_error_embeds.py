"""Tests verifying error and warning messages use embeds instead of plain text.

Phase RED — current code sends plain text; these tests assert embed= is used,
so they MUST fail until music_cog.py is updated to use build_error_embed,
build_warning_embed, or build_info_embed.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cogs.music_cog import Music


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _assert_sent_error_embed(send_mock):
    """Assert that send was called with an error embed (title='❌ Error')."""
    send_mock.assert_awaited_once()
    kwargs = send_mock.call_args.kwargs
    assert "embed" in kwargs, (
        f"Expected embed= in send, got args={send_mock.call_args.args!r}"
    )
    embed = kwargs["embed"]
    assert embed.title == "❌ Error", (
        f"Expected error embed title '❌ Error', got {embed.title!r}"
    )


def _assert_sent_warning_or_info_embed(send_mock):
    """Assert that send was called with an embed (not plain text)."""
    send_mock.assert_awaited_once()
    kwargs = send_mock.call_args.kwargs
    assert "embed" in kwargs, (
        f"Expected embed= in send, got args={send_mock.call_args.args!r}"
    )


# ---------------------------------------------------------------------------
# Test A — Error "no estás en un canal de voz"
#   join_voice_channel envía texto plano cuando ctx.author.voice es None
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_join_voice_channel_no_voice_sends_error_embed():
    """El usuario NO está en un canal de voz → debe recibir embed de error."""
    cog = Music.__new__(Music)

    ctx = MagicMock()
    ctx.author.voice = None       # ← usuario sin canal de voz
    ctx.send = AsyncMock()

    await cog.join_voice_channel(ctx)

    _assert_sent_error_embed(ctx.send)


# ---------------------------------------------------------------------------
# Test B — Mensaje de inactividad (desconexión automática)
#   check_inactivity envía texto plano al desconectar
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@patch("cogs.music_cog.time", return_value=1000.0)
async def test_inactivity_disconnect_sends_embed(mock_time):
    """Tras 300s de inactividad, el mensaje de desconexión debe ser embed."""
    cog = Music.__new__(Music)
    cog.bot = MagicMock()
    cog.states = {}  # __init__ not called by __new__

    guild_id = 1
    guild = MagicMock(id=guild_id)

    voice_client = MagicMock()
    voice_client.is_connected.return_value = True
    voice_client.is_playing.return_value = False
    voice_client.is_paused.return_value = False
    voice_client.disconnect = AsyncMock()

    # Canal con al menos un usuario no-bot
    member = MagicMock()
    member.bot = False
    voice_client.channel = MagicMock()
    voice_client.channel.members = [member]

    # discord.utils.get necesita que voice_client.guild == guild
    voice_client.guild = guild

    cog.bot.get_guild.return_value = guild
    cog.bot.voice_clients = [voice_client]

    # Crear el estado manualmente
    state = cog._state(guild)
    state.last_activity = 699.0          # 301s antes que time() = 1000
    state.inactivity_warned = True       # evita la rama del warning
    state.inactivity_channel = MagicMock()
    state.inactivity_channel.send = AsyncMock()
    state.queue = []                      # cola vacía (sin actividad)

    # Ejecutar el callback del loop de inactividad
    await cog.check_inactivity()

    # Verificar que el mensaje de desconexión usa embed
    _assert_sent_warning_or_info_embed(state.inactivity_channel.send)


@pytest.mark.asyncio
@patch("cogs.music_cog.time", return_value=1000.0)
async def test_inactivity_warning_sends_warning_embed(mock_time):
    """Tras 240s de inactividad, la advertencia debe ser embed (no texto)."""
    cog = Music.__new__(Music)
    cog.bot = MagicMock()
    cog.states = {}  # __init__ not called by __new__

    guild_id = 1
    guild = MagicMock(id=guild_id)

    voice_client = MagicMock()
    voice_client.is_connected.return_value = True
    voice_client.is_playing.return_value = False
    voice_client.is_paused.return_value = False
    voice_client.disconnect = AsyncMock()

    member = MagicMock()
    member.bot = False
    voice_client.channel = MagicMock()
    voice_client.channel.members = [member]
    voice_client.guild = guild

    cog.bot.get_guild.return_value = guild
    cog.bot.voice_clients = [voice_client]

    state = cog._state(guild)
    state.last_activity = 740.0          # 260s antes → >240 pero <300
    state.inactivity_warned = False
    state.inactivity_channel = MagicMock()
    state.inactivity_channel.send = AsyncMock()
    state.queue = []

    await cog.check_inactivity()

    # No se desconecta (260 < 300), pero SÍ envía warning
    voice_client.disconnect.assert_not_awaited()
    _assert_sent_warning_or_info_embed(state.inactivity_channel.send)


@pytest.mark.asyncio
@patch("cogs.music_cog.time", return_value=1000.0)
async def test_empty_channel_disconnect_sends_embed(mock_time):
    """Canal vacío (solo bot) → mensaje de desconexión debe ser embed."""
    cog = Music.__new__(Music)
    cog.bot = MagicMock()
    cog.states = {}  # __init__ not called by __new__

    guild_id = 1
    guild = MagicMock(id=guild_id)

    voice_client = MagicMock()
    voice_client.is_connected.return_value = True
    voice_client.is_playing.return_value = False
    voice_client.is_paused.return_value = False
    voice_client.disconnect = AsyncMock()

    # Canal SIN miembros no-bot
    voice_client.channel = MagicMock()
    voice_client.channel.members = []    # ← vacío
    voice_client.guild = guild

    cog.bot.get_guild.return_value = guild
    cog.bot.voice_clients = [voice_client]

    state = cog._state(guild)
    state.last_activity = 500.0          # cualquier valor, se desconecta por canal vacío
    state.inactivity_warned = False
    state.inactivity_channel = MagicMock()
    state.inactivity_channel.send = AsyncMock()
    state.queue = []

    await cog.check_inactivity()

    _assert_sent_warning_or_info_embed(state.inactivity_channel.send)


# ---------------------------------------------------------------------------
# Test C — Error "no hay nada reproduciendo" (skip / pause sin música)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_skip_no_voice_client_sends_error_embed():
    """!skip sin voice_client → debe enviar embed de error, no texto."""
    cog = Music.__new__(Music)
    cog.update_activity = MagicMock()

    ctx = MagicMock()
    ctx.voice_client = None
    ctx.send = AsyncMock()

    await cog.skip.callback(cog, ctx)

    _assert_sent_error_embed(ctx.send)


@pytest.mark.asyncio
async def test_skip_not_playing_sends_error_embed():
    """!skip con voice_client pero sin reproducción → embed de error."""
    cog = Music.__new__(Music)
    cog.update_activity = MagicMock()

    ctx = MagicMock()
    ctx.voice_client = MagicMock()
    ctx.voice_client.is_playing.return_value = False
    ctx.send = AsyncMock()

    await cog.skip.callback(cog, ctx)

    _assert_sent_error_embed(ctx.send)


@pytest.mark.asyncio
async def test_pause_no_voice_client_sends_error_embed():
    """!pause sin voice_client → debe enviar embed de error, no texto."""
    cog = Music.__new__(Music)
    cog.update_activity = MagicMock()

    ctx = MagicMock()
    ctx.voice_client = None
    ctx.send = AsyncMock()

    await cog.pause.callback(cog, ctx)

    _assert_sent_error_embed(ctx.send)


@pytest.mark.asyncio
async def test_pause_not_playing_sends_error_embed():
    """!pause con voice_client pero sin reproducción → embed de error."""
    cog = Music.__new__(Music)
    cog.update_activity = MagicMock()

    ctx = MagicMock()
    ctx.voice_client = MagicMock()
    ctx.voice_client.is_playing.return_value = False
    ctx.send = AsyncMock()

    await cog.pause.callback(cog, ctx)

    _assert_sent_error_embed(ctx.send)


# ---------------------------------------------------------------------------
# Extras — otros casos de texto plano que deberían ser embeds
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stop_happy_path_uses_info_embed():
    """!stop exitoso debe usar embed (info), no texto plano."""
    cog = Music.__new__(Music)
    cog._cleanup_state = MagicMock()
    cog.states = {}

    ctx = MagicMock()
    ctx.guild = MagicMock(id=1)
    ctx.voice_client = MagicMock()
    ctx.voice_client.stop = MagicMock()
    ctx.voice_client.disconnect = AsyncMock()
    ctx.send = AsyncMock()

    await cog.stop.callback(cog, ctx)

    ctx.send.assert_awaited_once()
    kwargs = ctx.send.call_args.kwargs
    assert "embed" in kwargs, (
        f"Expected embed= in stop, got args={ctx.send.call_args.args!r}"
    )
    # The embed doesn't have to be an error embed here; just not plain text
    assert hasattr(kwargs["embed"], "title"), "stop message should be an Embed"


@pytest.mark.asyncio
async def test_resume_no_voice_client_sends_error_embed():
    """!resume sin voice_client → debe enviar embed de error, no texto."""
    cog = Music.__new__(Music)
    cog.update_activity = MagicMock()

    ctx = MagicMock()
    ctx.voice_client = None
    ctx.send = AsyncMock()

    await cog.resume.callback(cog, ctx)

    _assert_sent_error_embed(ctx.send)


@pytest.mark.asyncio
async def test_resume_not_paused_sends_error_embed():
    """!resume sin nada pausado → debe enviar embed de error."""
    cog = Music.__new__(Music)
    cog.update_activity = MagicMock()

    ctx = MagicMock()
    ctx.voice_client = MagicMock()
    ctx.voice_client.is_paused.return_value = False
    ctx.send = AsyncMock()

    await cog.resume.callback(cog, ctx)

    _assert_sent_error_embed(ctx.send)
