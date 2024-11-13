import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from db import db

# Load environment variables from the .env file
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID"))  # Discord server ID, if required
TOURNAMENTS_CHANNEL_ID = int(os.getenv("TOURNAMENTS_CHANNEL_ID"))

# Set intents to receive message content and member events
intents = discord.Intents.all()

# Initialize the bot with a command prefix and intents
bot = commands.Bot(command_prefix="!", intents=intents)

# Ensure database tables are created if they don't exist
db.create_tables()


@bot.event
async def on_ready():
    """
    Event triggered when the bot has connected to Discord.
    """
    print(f"{bot.user.name} conectado.")
    guild = discord.utils.get(bot.guilds, id=GUILD_ID)
    if guild:
        print(f"Conectado al servidor {guild.name}.")
    else:
        print("Error al conectar con el servidor (Guild error).")

    # Get the channel and pass it to the cog
    channel = bot.get_channel(TOURNAMENTS_CHANNEL_ID)
    if channel:
        # Access the cog and set the channel
        wca_cog = bot.get_cog("WCA")
        if wca_cog:
            await wca_cog.set_channel(channel)
    else:
        print("Canal no encontrado.")


# Load cogs asynchronously
async def load_cogs():
    """
    Loads all the necessary cogs for the bot.
    """
    await bot.load_extension("cogs.wca_cog")  # Load the WCA cog
    await bot.load_extension("cogs.music_cog")  # Load the music cog


# Run the bot
if __name__ == "__main__":

    async def main():
        await load_cogs()  # Load all cogs before starting the bot
        await bot.start(TOKEN)

    import asyncio

    asyncio.run(main())
