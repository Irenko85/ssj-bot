from cogs.music_cog import GuildState


def test_guild_state_starts_without_now_playing_message():
    state = GuildState()

    assert state.now_playing_message is None
