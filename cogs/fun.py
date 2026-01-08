from __future__ import annotations
from typing import TYPE_CHECKING, Optional, List, Union
import io
import discord
from discord import app_commands
from discord.ext import commands, tasks
import datetime
from datetime import datetime as dt, UTC
import random
import aiohttp
import os
import re
import humanize
import psutil
import time
import asyncio
import json
import math
import difflib
import yt_dlp
from PIL import Image, ImageDraw, ImageFont, ImageOps
import google.generativeai as genai

if TYPE_CHECKING:
    from ..bot import MaxyBot

from .utils import cog_command_error

class Fun(commands.Cog, name="Fun"):
    def __init__(self, bot: MaxyBot):
        self.bot = bot
        self.http_session = bot.http_session

    async def get_tenor_gif(self, query: str) -> Optional[str]:
        api_key = os.getenv("TENOR_API_KEY")
        if not api_key:
            return None
        url = f"https://tenor.googleapis.com/v2/search?q={query}&key={api_key}&limit=20&media_filter=minimal"
        async with self.http_session.get(url) as response:
            if response.status == 200:
                data = await response.json()
                if data['results']:
                    return random.choice(data['results'])['media_formats']['gif']['url']
        return None

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        await cog_command_error(interaction, error)

    @app_commands.command(name="8ball", description="Ask the magic 8-ball a question.")
    @app_commands.describe(question="The question you want to ask.")
    async def eight_ball(self, interaction: discord.Interaction, question: str):
        responses = [
            "It is certain.", "It is decidedly so.", "Without a doubt.", "Yes – definitely.", "You may rely on it.",
            "As I see it, yes.", "Most likely.", "Outlook good.", "Yes.", "Signs point to yes.",
            "Reply hazy, try again.", "Ask again later.", "Better not tell you now.", "Cannot predict now.", "Concentrate and ask again.",
            "Don't count on it.", "My reply is no.", "My sources say no.", "Outlook not so good.", "Very doubtful."
        ]
        embed = discord.Embed(title="🎱 The Magic 8-Ball Says...", color=discord.Color.blue())
        embed.add_field(name="Your Question", value=question, inline=False)
        embed.add_field(name="Answer", value=random.choice(responses), inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="coinflip", description="Flips a coin.")
    async def coinflip(self, interaction: discord.Interaction):
        result = random.choice(["Heads", "Tails"])
        embed = discord.Embed(title="🪙 Coin Flip", description=f"The coin landed on... **{result}**!", color=discord.Color.gold())
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="meme", description="Gets a random meme from Reddit.")
    async def meme(self, interaction: discord.Interaction):
        await interaction.response.defer()
        subreddits = ["memes", "dankmemes", "wholesomememes", "me_irl"]
        try:
            async with self.http_session.get(f"https://www.reddit.com/r/{random.choice(subreddits)}/random.json") as resp:
                if resp.status != 200:
                    return await interaction.followup.send("Could not fetch a meme, Reddit might be down.")
                data = await resp.json()
                post = data[0]['data']['children'][0]['data']
                embed = discord.Embed(title=post['title'], url=f"https://reddit.com{post['permalink']}", color=discord.Color.orange())
                embed.set_image(url=post['url'])
                embed.set_footer(text=f"👍 {post['ups']} | 💬 {post['num_comments']} | r/{post['subreddit']}")
                await interaction.followup.send(embed=embed)
        except Exception as e:
            await interaction.followup.send(f"An error occurred: {e}")

    @app_commands.command(name="gif", description="Searches for a GIF on Tenor.")
    @app_commands.describe(query="What to search for.")
    async def gif(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer()
        gif_url = await self.get_tenor_gif(query)
        if gif_url:
            await interaction.followup.send(gif_url)
        else:
            await interaction.followup.send(f"Could not find a GIF for '{query}'. The Tenor API key might be missing or invalid.")

    @app_commands.command(name="slap", description="Slap someone with a GIF.")
    @app_commands.describe(user="The user to slap.")
    async def slap(self, interaction: discord.Interaction, user: discord.Member):
        await interaction.response.defer()
        gif_url = await self.get_tenor_gif("anime slap")
        embed = discord.Embed(description=f"{interaction.user.mention} slaps {user.mention}!", color=discord.Color.red())
        if gif_url:
            embed.set_image(url=gif_url)
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="hug", description="Hug someone with a GIF.")
    @app_commands.describe(user="The user to hug.")
    async def hug(self, interaction: discord.Interaction, user: discord.Member):
        await interaction.response.defer()
        gif_url = await self.get_tenor_gif("anime hug")
        embed = discord.Embed(description=f"{interaction.user.mention} hugs {user.mention}!", color=discord.Color.pink())
        if gif_url:
            embed.set_image(url=gif_url)
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="ship", description="Calculates the love compatibility between two users.")
    @app_commands.describe(user1="The first user.", user2="The second user.")
    async def ship(self, interaction: discord.Interaction, user1: discord.Member, user2: Optional[discord.Member] = None):
        if user2 is None:
            user2 = interaction.user
        percentage = random.randint(0, 100)
        if percentage < 20: msg = "Not a great match... 💔"
        elif percentage < 50: msg = "Could be worse! 🤔"
        elif percentage < 80: msg = "There's definitely potential! 🥰"
        else: msg = "It's a match made in heaven! 💖"
        embed = discord.Embed(title="Love Calculator", description=f"**{user1.display_name}** + **{user2.display_name}** = **{percentage}%**\n\n{msg}", color=discord.Color.pink())
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="howgay", description="Calculates how gay a user is.")
    @app_commands.describe(user="The user to rate.")
    async def howgay(self, interaction: discord.Interaction, user: Optional[discord.Member] = None):
        target = user or interaction.user
        percentage = random.randint(0, 100)
        embed = discord.Embed(title="Gay-o-Meter", description=f"**{target.display_name}** is **{percentage}%** gay! 🏳️‍🌈", color=discord.Color.random())
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="rps", description="Play Rock, Paper, Scissors with the bot.")
    @app_commands.describe(choice="Your choice.")
    @app_commands.choices(choice=[
        app_commands.Choice(name="Rock", value="rock"),
        app_commands.Choice(name="Paper", value="paper"),
        app_commands.Choice(name="Scissors", value="scissors"),
    ])
    async def rps(self, interaction: discord.Interaction, choice: app_commands.Choice[str]):
        bot_choice = random.choice(["rock", "paper", "scissors"])
        user_choice = choice.value

        result = "It's a tie!"
        if (user_choice == "rock" and bot_choice == "scissors") or \
           (user_choice == "paper" and bot_choice == "rock") or \
           (user_choice == "scissors" and bot_choice == "paper"):
            result = "You win!"
        elif (bot_choice == "rock" and user_choice == "scissors") or \
             (bot_choice == "paper" and user_choice == "rock") or \
             (bot_choice == "scissors" and user_choice == "paper"):
            result = "You lose!"

        await interaction.response.send_message(f"You chose **{user_choice}**. I chose **{bot_choice}**. **{result}**")

async def setup(bot: MaxyBot):
    await bot.add_cog(Fun(bot))