import discord
from discord.ext import commands
import asyncio
import os
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger("bot")


class Bot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(command_prefix="!", intents=intents, help_command=None)

    async def setup_hook(self):
        cogs = ["giveaway", "invites", "help"]
        for cog in cogs:
            try:
                await self.load_extension(cog)
                log.info(f"Loaded: {cog}")
            except Exception:
                import traceback
                log.error(f"Failed to load {cog}:\n{traceback.format_exc()}")

    async def on_ready(self):
        log.info(f"Ready: {self.user} ({self.user.id})")
        for guild in self.guilds:
            await self.tree.sync(guild=guild)
        log.info(f"Slash commands synced to {len(self.guilds)} guild(s).")


async def main():
    token = os.getenv("TOKEN")
    if not token:
        log.critical("TOKEN no configurado.")
        return
    async with Bot() as bot:
        await bot.start(token)


if __name__ == "__main__":
    asyncio.run(main())
