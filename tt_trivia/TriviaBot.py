import discord
import asyncio


class TriviaBot(discord.Client):

    async def on_ready(self):
        print(f"{self.user} logged on.")
