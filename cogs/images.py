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

class Images(commands.Cog, name="Images"):
    def __init__(self, bot: MaxyBot):
        self.bot = bot
        self.font_path = str(self.bot.root_path / "assets" / "fonts" / "font.ttf")
        self.template_path = self.bot.root_path / "assets" / "images" / "templates"

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        await cog_command_error(interaction, error)

    async def get_avatar_bytes(self, user: discord.User) -> bytes:
        return await user.display_avatar.with_format("png").read()

    def generate_wanted_image(self, avatar_bytes: bytes) -> io.BytesIO:
        avatar = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA").resize((440, 440))
        template = Image.open(self.template_path / "wanted.png")

        template.paste(avatar, (145, 298), avatar)

        buffer = io.BytesIO()
        template.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer

    def process_image_effect(self, avatar_bytes: bytes, effect: str) -> io.BytesIO:
        image = Image.open(io.BytesIO(avatar_bytes))

        if effect == 'grayscale':
            image = image.convert("L").convert("RGB")
        elif effect == 'invert':
            image = ImageOps.invert(image.convert("RGB"))

        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer

    @app_commands.command(name="wanted", description="Generates a wanted poster for a user.")
    @app_commands.describe(user="The user to put on the poster. Defaults to you.")
    async def wanted(self, interaction: discord.Interaction, user: Optional[discord.Member] = None):
        target = user or interaction.user
        await interaction.response.defer()

        avatar_bytes = await self.get_avatar_bytes(target)

        loop = asyncio.get_event_loop()
        buffer = await loop.run_in_executor(None, self.generate_wanted_image, avatar_bytes)

        file = discord.File(fp=buffer, filename=f"wanted_{target.id}.png")
        await interaction.followup.send(file=file)

    @app_commands.command(name="grayscale", description="Applies a grayscale filter to a user's avatar.")
    @app_commands.describe(user="The user whose avatar to change. Defaults to you.")
    async def grayscale(self, interaction: discord.Interaction, user: Optional[discord.Member] = None):
        target = user or interaction.user
        await interaction.response.defer()

        avatar_bytes = await self.get_avatar_bytes(target)

        loop = asyncio.get_event_loop()
        buffer = await loop.run_in_executor(None, self.process_image_effect, avatar_bytes, 'grayscale')

        file = discord.File(fp=buffer, filename=f"grayscale_{target.id}.png")
        await interaction.followup.send(file=file)

    @app_commands.command(name="invert", description="Inverts the colors of a user's avatar.")
    @app_commands.describe(user="The user whose avatar to change. Defaults to you.")
    async def invert(self, interaction: discord.Interaction, user: Optional[discord.Member] = None):
        target = user or interaction.user
        await interaction.response.defer()

        avatar_bytes = await self.get_avatar_bytes(target)

        loop = asyncio.get_event_loop()
        buffer = await loop.run_in_executor(None, self.process_image_effect, avatar_bytes, 'invert')

        file = discord.File(fp=buffer, filename=f"invert_{target.id}.png")
        await interaction.followup.send(file=file)

async def setup(bot: MaxyBot):
    await bot.add_cog(Images(bot))