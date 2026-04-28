"""Tests for on_app_command_error sending embeds instead of plain text."""
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord import app_commands

from bot import on_app_command_error


@pytest.mark.asyncio
async def test_app_command_error_sends_embed_when_not_responded():
    """When interaction.response.is_done() is False, send_message should receive embed."""
    interaction = MagicMock()
    interaction.command = MagicMock()
    interaction.command.name = "test"
    interaction.response.is_done.return_value = False
    interaction.response.send_message = AsyncMock()
    interaction.followup.send = AsyncMock()

    error = app_commands.AppCommandError("something went wrong")

    with patch("bot.logger"):
        await on_app_command_error(interaction, error)

    interaction.response.send_message.assert_awaited_once()
    _, kwargs = interaction.response.send_message.call_args
    assert "embed" in kwargs, "Expected embed= in send_message"
    embed = kwargs["embed"]
    assert isinstance(embed, discord.Embed)
    assert embed.title == "❌ Error"
    assert embed.colour == discord.Colour(0x922B21)


@pytest.mark.asyncio
async def test_app_command_error_sends_embed_via_followup_when_already_responded():
    """When interaction.response.is_done() is True, followup.send should receive embed."""
    interaction = MagicMock()
    interaction.command = MagicMock()
    interaction.command.name = "test"
    interaction.response.is_done.return_value = True
    interaction.response.send_message = AsyncMock()
    interaction.followup.send = AsyncMock()

    error = app_commands.AppCommandError("something went wrong")

    with patch("bot.logger"):
        await on_app_command_error(interaction, error)

    interaction.followup.send.assert_awaited_once()
    _, kwargs = interaction.followup.send.call_args
    assert "embed" in kwargs, "Expected embed= in followup.send"
    embed = kwargs["embed"]
    assert isinstance(embed, discord.Embed)
    assert embed.title == "❌ Error"
    assert embed.colour == discord.Colour(0x922B21)
