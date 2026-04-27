import os
import sys
import asyncio
import logging
import discord
from discord.ext import commands
from dotenv import load_dotenv

# Load environment variables from the .env file
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

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
bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    """Event triggered when the bot has connected to Discord."""
    logger.info(f"{bot.user.name} conectado en {len(bot.guilds)} servidor(es).")


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
