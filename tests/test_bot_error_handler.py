"""Tests para el manejador global de errores de comandos prefix/mention.

Estos tests verifican que `handle_command_error` envia embeds informativos
(en lugar de re-lanzar) para errores como MissingRequiredArgument,
BadArgument y excepciones inesperadas.
"""

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord.ext import commands

from bot import handle_command_error


# ── MissingRequiredArgument ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_missing_required_argument_sends_error_embed():
    """Al faltar un argumento requerido se debe enviar un embed de error."""
    ctx = MagicMock()
    ctx.send = AsyncMock()
    param = MagicMock()
    param.name = "cancion"
    error = commands.MissingRequiredArgument(param)

    await handle_command_error(ctx, error)

    ctx.send.assert_called_once()
    _, kwargs = ctx.send.call_args
    assert "embed" in kwargs, (
        "ctx.send debe llamarse con embed=build_error_embed(...)"
    )
    embed = kwargs["embed"]
    assert isinstance(embed, discord.Embed)
    assert embed.title == "❌ Error"
    assert embed.colour == discord.Colour(0x922B21)
    assert "cancion" in embed.description, (
        "El embed debe mencionar el nombre del argumento faltante"
    )


# ── BadArgument ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_bad_argument_sends_error_embed():
    """Al pasar un argumento de tipo incorrecto se debe enviar un embed de error."""
    ctx = MagicMock()
    ctx.send = AsyncMock()
    error = commands.BadArgument("no se pudo convertir el argumento")

    await handle_command_error(ctx, error)

    ctx.send.assert_called_once()
    _, kwargs = ctx.send.call_args
    assert "embed" in kwargs, (
        "ctx.send debe llamarse con embed=build_error_embed(...)"
    )
    embed = kwargs["embed"]
    assert isinstance(embed, discord.Embed)
    assert embed.title == "❌ Error"
    assert embed.colour == discord.Colour(0x922B21)


# ── Errores inesperados (genéricos) ─────────────────────────────────────


@pytest.mark.asyncio
async def test_unexpected_error_sends_generic_embed():
    """Un error no manejado debe enviar un embed con mensaje genérico."""
    ctx = MagicMock()
    ctx.send = AsyncMock()
    error = RuntimeError("algo explotó internamente")

    await handle_command_error(ctx, error)

    ctx.send.assert_called_once()
    _, kwargs = ctx.send.call_args
    assert "embed" in kwargs, (
        "ctx.send debe llamarse con embed=build_error_embed(...)"
    )
    embed = kwargs["embed"]
    assert isinstance(embed, discord.Embed)
    assert embed.title == "❌ Error"
    assert embed.colour == discord.Colour(0x922B21)
    assert "error" in embed.description.lower(), (
        "El embed debe contener un mensaje de error genérico"
    )


# ── CommandInvokeError (wrapper de errores inesperados) ────────────────


@pytest.mark.asyncio
async def test_command_invoke_error_sends_error_embed():
    """Un CommandInvokeError que envuelve un error inesperado debe enviar embed."""
    ctx = MagicMock()
    ctx.send = AsyncMock()
    inner = ValueError("valor inválido en el comando")
    error = commands.CommandInvokeError(inner)

    await handle_command_error(ctx, error)

    ctx.send.assert_called_once()
    _, kwargs = ctx.send.call_args
    assert "embed" in kwargs
    embed = kwargs["embed"]
    assert isinstance(embed, discord.Embed)
    assert embed.title == "❌ Error"
    assert embed.colour == discord.Colour(0x922B21)


# ── CommandOnCooldown (opcional, edge case) ────────────────────────────


@pytest.mark.asyncio
async def test_command_on_cooldown_sends_error_embed():
    """Un comando en cooldown debe enviar un embed de error."""
    ctx = MagicMock()
    ctx.send = AsyncMock()
    # Construir un Cooldown con los atributos mínimos necesarios
    cooldown = type(
        "Cooldown",
        (),
        {"rate": 1, "per": 5.0, "type": commands.BucketType.default},
    )()
    error = commands.CommandOnCooldown(
        cooldown, retry_after=3.5, type=commands.BucketType.default
    )

    await handle_command_error(ctx, error)

    ctx.send.assert_called_once()
    _, kwargs = ctx.send.call_args
    assert "embed" in kwargs
    embed = kwargs["embed"]
    assert isinstance(embed, discord.Embed)
    assert embed.title == "❌ Error"
    assert embed.colour == discord.Colour(0x922B21)
