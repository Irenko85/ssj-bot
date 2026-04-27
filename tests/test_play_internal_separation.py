"""Tests for the public/internal split of the play command."""
import inspect
from unittest.mock import AsyncMock, MagicMock

import pytest

from cogs.music_cog import Music


def test_play_command_does_not_expose_silent():
    """The public hybrid `play` command must not expose a `silent` parameter."""
    sig = inspect.signature(Music.play.callback)
    assert "silent" not in sig.parameters, (
        "silent must not be a slash command parameter"
    )


def test_play_internal_exists_and_accepts_silent():
    """`_play_internal` must exist with a `silent` keyword argument."""
    assert hasattr(Music, "_play_internal"), "missing _play_internal helper"
    sig = inspect.signature(Music._play_internal)
    assert "silent" in sig.parameters, "_play_internal must accept silent"
    assert sig.parameters["silent"].default is False
