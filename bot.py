import os
import sys
import asyncio
import logging
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

# Load environment variables from the .env file
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")


def _parse_guild_ids(raw: str | None) -> list[int]:
    """Parse comma-separated guild IDs from env var. Skips invalid tokens."""
    if not raw:
        return []
    out: list[int] = []
    for piece in raw.split(","):
        piece = piece.strip()
        if not piece:
            continue
        try:
            out.append(int(piece))
        except ValueError:
            logging.getLogger("ssj-bot").warning(
                "Ignorando GUILD_IDS inválido: %r", piece
            )
    return out


GUILD_IDS = _parse_guild_ids(os.getenv("GUILD_IDS"))

# Configure logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("ssj-bot")

# Set intents to receive message content and member events
intents = discord.Intents.all()

# Initialize the bot with a command prefix and intents
bot = commands.Bot(command_prefix=commands.when_mentioned, intents=intents)


@bot.event
async def on_ready():
    """Event triggered when the bot has connected to Discord."""
    logger.info(f"{bot.user.name} conectado en {len(bot.guilds)} servidor(es).")
    await _sync_app_commands()


async def _sync_app_commands():
    """Sync slash commands. Per-guild if GUILD_IDS set, else global.

    Hybrid commands register globally in bot.tree by default. To make
    them appear instantly per-guild we must copy_global_to(guild=X)
    before sync(guild=X). Otherwise the per-guild sync registers an
    empty list silently and users see no slash commands.
    """
    if GUILD_IDS:
        success = 0
        for gid in GUILD_IDS:
            try:
                guild_obj = discord.Object(id=gid)
                bot.tree.copy_global_to(guild=guild_obj)
                synced = await bot.tree.sync(guild=guild_obj)
                logger.info("Sync guild %s: %d comandos.", gid, len(synced))
                success += 1
            except Exception as e:
                logger.warning("Sync falló para guild %s: %s", gid, e)
        logger.info(
            "Slash commands sincronizados en %d/%d guild(s).",
            success,
            len(GUILD_IDS),
        )
    else:
        try:
            synced = await bot.tree.sync()
            logger.info(
                "Slash commands sincronizados globalmente: %d comandos "
                "(puede tardar hasta 1h en aparecer).",
                len(synced),
            )
        except Exception as e:
            logger.error("Sync global falló: %s", e)


@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError,
):
    """Catch unhandled errors from slash commands."""
    logger.error(
        "Error en slash command %s: %s",
        interaction.command.name if interaction.command else "?",
        error,
        exc_info=True,
    )
    msg = "Ocurrió un error inesperado."
    try:
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)
    except Exception as e:
        logger.error("No pude enviar mensaje de error al usuario: %s", e)


async def handle_command_error(ctx, error):
    """Global handler for prefix/mention command errors.

    Silences CommandNotFound (typos like !d, !aaa) to avoid log spam now
    that the prefix is disabled. Re-raises everything else so real bugs
    still get logged by discord.py's default behavior.
    """
    if isinstance(error, commands.CommandNotFound):
        return
    raise error


bot.add_listener(handle_command_error, "on_command_error")


async def load_cogs():
    """Loads all the necessary cogs for the bot."""
    await bot.load_extension("cogs.music_cog")


async def main():
    if not TOKEN:
        logger.error("DISCORD_TOKEN no está configurado en el entorno.")
        sys.exit(1)

    logger.info("Cargando cogs...")
    await load_cogs()
    logger.info("Cogs cargados correctamente.")
    await bot.start(TOKEN)


if __name__ == "__main__":
    sys.stdout.reconfigure(line_buffering=True)
    asyncio.run(main())
