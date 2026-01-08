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

class Configuration(commands.Cog, name="Configuration"):
    def __init__(self, bot: MaxyBot):
        self.bot = bot

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        await cog_command_error(interaction, error)

    @app_commands.command(name="set-prefix", description="[Admin] Sets the legacy command prefix for the bot.")
    @app_commands.describe(prefix="The new prefix to use.")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_prefix(self, interaction: discord.Interaction, prefix: str):
        if len(prefix) > 5:
            return await interaction.response.send_message("Prefix cannot be longer than 5 characters.", ephemeral=True)
        conf = self.bot.get_guild_config(interaction.guild.id)
        conf['prefix'] = prefix
        self.bot.config_data[str(interaction.guild.id)] = conf
        await self.bot.save_config()
        self.bot.config_cache.pop(interaction.guild.id, None)
        await interaction.response.send_message(f"✅ My prefix has been updated to `{prefix}`.", ephemeral=True)

    @app_commands.command(name="setup-welcome", description="[Admin] Configures the welcome message system.")
    @app_commands.describe(channel="The channel for welcome messages.", message="The welcome message. Use {user.mention}, {user.name}, {guild.name}.")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_welcome(self, interaction: discord.Interaction, channel: discord.TextChannel, message: str):
        conf = self.bot.get_guild_config(interaction.guild.id)
        conf['welcome']['channel_id'] = channel.id
        conf['welcome']['message'] = message
        conf['welcome']['enabled'] = True
        self.bot.config_data[str(interaction.guild.id)] = conf
        await self.bot.save_config()
        self.bot.config_cache.pop(interaction.guild.id, None)
        await interaction.response.send_message(f"✅ Welcome messages will now be sent to {channel.mention}.", ephemeral=True)

    @app_commands.command(name="setup-logs", description="[Admin] Configures the server logging system.")
    @app_commands.describe(channel="The channel for logging server events.")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_logs(self, interaction: discord.Interaction, channel: discord.TextChannel):
        conf = self.bot.get_guild_config(interaction.guild.id)
        conf['logging']['channel_id'] = channel.id
        conf['logging']['enabled'] = True
        self.bot.config_data[str(interaction.guild.id)] = conf
        await self.bot.save_config()
        self.bot.config_cache.pop(interaction.guild.id, None)
        await interaction.response.send_message(f"✅ Server events will now be logged in {channel.mention}.", ephemeral=True)

    @app_commands.command(name="autorole-human", description="[Admin] Sets a role to be automatically given to new human members.")
    @app_commands.describe(role="The role to assign.")
    @app_commands.checks.has_permissions(administrator=True)
    async def autorole_human(self, interaction: discord.Interaction, role: discord.Role):
        conf = self.bot.get_guild_config(interaction.guild.id)
        if role.is_default() or role.is_bot_managed() or role.is_premium_subscriber() or role.is_integration():
            return await interaction.response.send_message("You cannot assign this type of role.", ephemeral=True)

        conf['autorole']['human_role_id'] = role.id
        conf['autorole']['enabled'] = True
        message = f"✅ New human members will now automatically receive the {role.mention} role."

        self.bot.config_data[str(interaction.guild.id)] = conf
        await self.bot.save_config()
        self.bot.config_cache.pop(interaction.guild.id, None)
        await interaction.response.send_message(message, ephemeral=True)

async def setup(bot: MaxyBot):
    await bot.add_cog(Configuration(bot))