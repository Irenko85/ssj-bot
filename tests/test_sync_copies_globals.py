"""Tests for _sync_app_commands copying global hybrid commands per guild.

Hybrid commands register globally in bot.tree by default. Calling
tree.sync(guild=X) without first copying globals to guild X syncs an
empty list silently. Discord then shows zero slash commands for users.

These tests verify that when GUILD_IDS is set:
- copy_global_to(guild=X) is called BEFORE sync(guild=X) for each guild
- the per-guild call order is correct (copy then sync)
"""
from unittest.mock import AsyncMock, MagicMock, call, patch

import discord
import pytest

import bot as bot_module


@pytest.mark.asyncio
async def test_sync_copies_globals_before_per_guild_sync(monkeypatch):
    """copy_global_to must run before sync for each guild."""
    monkeypatch.setattr(bot_module, "GUILD_IDS", [111, 222])

    fake_tree = MagicMock()
    fake_tree.copy_global_to = MagicMock()
    fake_tree.sync = AsyncMock(return_value=[MagicMock(), MagicMock(), MagicMock()])

    fake_bot = MagicMock()
    fake_bot.tree = fake_tree
    monkeypatch.setattr(bot_module, "bot", fake_bot)

    await bot_module._sync_app_commands()

    # copy_global_to called once per guild with discord.Object(id=gid)
    assert fake_tree.copy_global_to.call_count == 2
    copy_calls = fake_tree.copy_global_to.call_args_list
    assert copy_calls[0].kwargs["guild"].id == 111
    assert copy_calls[1].kwargs["guild"].id == 222

    # sync called once per guild
    assert fake_tree.sync.call_count == 2
    sync_calls = fake_tree.sync.call_args_list
    assert sync_calls[0].kwargs["guild"].id == 111
    assert sync_calls[1].kwargs["guild"].id == 222


@pytest.mark.asyncio
async def test_sync_logs_command_count_per_guild(monkeypatch, caplog):
    """Per-guild sync should log how many commands were synced."""
    import logging
    monkeypatch.setattr(bot_module, "GUILD_IDS", [555])

    fake_tree = MagicMock()
    fake_tree.copy_global_to = MagicMock()
    # 13 commands synced
    fake_tree.sync = AsyncMock(return_value=[MagicMock() for _ in range(13)])

    fake_bot = MagicMock()
    fake_bot.tree = fake_tree
    monkeypatch.setattr(bot_module, "bot", fake_bot)

    with caplog.at_level(logging.INFO, logger="ssj-bot"):
        await bot_module._sync_app_commands()

    # Some log line must mention "13" and the guild id
    msgs = " ".join(r.getMessage() for r in caplog.records)
    assert "13" in msgs
    assert "555" in msgs
