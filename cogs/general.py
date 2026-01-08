from __future__ import annotations
from typing import TYPE_CHECKING, Optional, List, Union
import io
import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord import Embed, Color
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
SUPPORT_SERVER = "https://discord.gg/Wnnqj4qaKp"  # حط هنا رابط سيرفر الدعم
class General(commands.Cog, name="General"):
    def __init__(self, bot: MaxyBot):
        self.bot = bot
        self.http_session = bot.http_session

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        await cog_command_error(interaction, error)

    @app_commands.command(name="ping", description="Checks the bot's latency and response time.")
    async def ping(self, interaction: discord.Interaction):
        latency = round(self.bot.latency * 1000)
        embed = discord.Embed(title="🏓 Pong!", description=f"**API Latency:** `{latency}ms`", color=discord.Color.green())
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="stats", description="Displays detailed statistics about the bot.")
    async def stats(self, interaction: discord.Interaction):
        process = psutil.Process(os.getpid())
        mem_usage = process.memory_info().rss
        uptime_delta = dt.now(UTC) - self.bot.start_time
        uptime_str = humanize.naturaldelta(uptime_delta)
        embed = discord.Embed(title=f"{self.bot.user.name} Statistics", color=discord.Color.blurple())
        embed.set_thumbnail(url=self.bot.user.avatar.url)
        embed.add_field(name="📊 Servers", value=f"`{len(self.bot.guilds)}`", inline=True)
        embed.add_field(name="👥 Users", value=f"`{len(self.bot.users)}`", inline=True)
        embed.add_field(name="💻 CPU Usage", value=f"`{psutil.cpu_percent()}%`", inline=True)
        embed.add_field(name="🧠 Memory", value=f"`{humanize.naturalsize(mem_usage)}`", inline=True)
        embed.add_field(name="⬆️ Uptime", value=f"`{uptime_str}`", inline=True)
        embed.add_field(name="🏓 Ping", value=f"`{round(self.bot.latency * 1000)}ms`", inline=True)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="userinfo", description="Shows detailed information about a user.")
    @app_commands.describe(user="The user to get info about. Defaults to you.")
    async def userinfo(self, interaction: discord.Interaction, user: Optional[discord.Member] = None):
        target = user or interaction.user
        embed = discord.Embed(title=f"User Information: {target.display_name}", color=target.color)
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="Full Name", value=f"`{target}`", inline=True)
        embed.add_field(name="User ID", value=f"`{target.id}`", inline=True)
        embed.add_field(name="Nickname", value=f"`{target.nick}`" if target.nick else "None", inline=True)
        embed.add_field(name="Account Created", value=discord.utils.format_dt(target.created_at, style='R'), inline=True)
        embed.add_field(name="Joined Server", value=discord.utils.format_dt(target.joined_at, style='R'), inline=True)
        roles = [role.mention for role in reversed(target.roles) if role.name != "@everyone"]
        role_str = ", ".join(roles) if roles else "None"
        embed.add_field(name=f"Roles [{len(roles)}]", value=role_str if len(role_str) < 1024 else f"{len(roles)} roles", inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="serverinfo", description="Shows detailed information about the current server.")
    async def serverinfo(self, interaction: discord.Interaction):
        guild = interaction.guild
        embed = discord.Embed(title=f"Server Info: {guild.name}", color=discord.Color.blue())
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        embed.add_field(name="Owner", value=guild.owner.mention, inline=True)
        embed.add_field(name="Server ID", value=f"`{guild.id}`", inline=True)
        embed.add_field(name="Created On", value=discord.utils.format_dt(guild.created_at, style='D'), inline=True)
        embed.add_field(name="Members", value=f"**Total:** {guild.member_count}\n**Humans:** {len([m for m in guild.members if not m.bot])}\n**Bots:** {len([m for m in guild.members if m.bot])}", inline=True)
        embed.add_field(name="Channels", value=f"**Text:** {len(guild.text_channels)}\n**Voice:** {len(guild.voice_channels)}", inline=True)
        embed.add_field(name="Roles", value=str(len(guild.roles)), inline=True)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="avatar", description="Displays a user's avatar in high resolution.")
    @app_commands.describe(user="The user whose avatar to show.")
    async def avatar(self, interaction: discord.Interaction, user: Optional[discord.Member] = None):
        target = user or interaction.user
        embed = discord.Embed(title=f"{target.display_name}'s Avatar", color=target.color)
        embed.set_image(url=target.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="snipe", description="Shows the most recently deleted message in the channel.")
    async def snipe(self, interaction: discord.Interaction):
        snipe_data = self.bot.snipe_data.get(interaction.channel.id)
        if not snipe_data:
            return await interaction.response.send_message("There's nothing to snipe!", ephemeral=True)
        embed = discord.Embed(description=snipe_data['content'], color=snipe_data['author'].color, timestamp=snipe_data['timestamp'])
        embed.set_author(name=snipe_data['author'].display_name, icon_url=snipe_data['author'].avatar.url)
        if snipe_data['attachments']:
            embed.set_image(url=snipe_data['attachments'][0])
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="editsnipe", description="Shows the original content of the most recently edited message.")
    async def editsnipe(self, interaction: discord.Interaction):
        snipe_data = self.bot.editsnipe_data.get(interaction.channel.id)
        if not snipe_data:
            return await interaction.response.send_message("There's no edited message to snipe!", ephemeral=True)
        embed = discord.Embed(color=snipe_data['author'].color, timestamp=snipe_data['timestamp'])
        embed.set_author(name=snipe_data['author'].display_name, icon_url=snipe_data['author'].avatar.url)
        embed.add_field(name="Before", value=snipe_data['before_content'], inline=False)
        embed.add_field(name="After", value=snipe_data['after_content'], inline=False)
        await interaction.response.send_message(embed=embed)

from typing import TYPE_CHECKING, Optional, List
import discord
from discord import app_commands, Embed, Color, Interaction
from discord.ext import commands

if TYPE_CHECKING:
    from ..bot import MaxyBot

# رابط سيرفر الدعم
SUPPORT_SERVER = "https://discord.gg/Wnnqj4qaKp"  # غيره لرابط سيرفرك

# ------------------ Paginated Help View ------------------
class PaginatedHelp(discord.ui.View):
    def __init__(self, bot: commands.Bot, cog_name: str, commands_list: List[str], cogs: List[str], per_page: int = 10):
        super().__init__(timeout=None)
        self.bot = bot
        self.cog_name = cog_name
        self.commands_list = commands_list
        self.cogs = cogs
        self.per_page = per_page
        self.current_page = 0
        self.total_pages = (len(commands_list) - 1) // per_page + 1

        self.prev_button = discord.ui.Button(label="⏮ Previous", style=discord.ButtonStyle.secondary)
        self.next_button = discord.ui.Button(label="Next ⏭", style=discord.ButtonStyle.secondary)
        self.back_button = discord.ui.Button(label="🔙 Back to Cogs", style=discord.ButtonStyle.danger)

        self.prev_button.callback = self.prev_page
        self.next_button.callback = self.next_page
        self.back_button.callback = self.go_back

        self.add_item(self.prev_button)
        self.add_item(self.next_button)
        self.add_item(self.back_button)

    def get_page_embed(self):
        start = self.current_page * self.per_page
        end = start + self.per_page
        page_commands = self.commands_list[start:end]
        embed = Embed(title=f"📜 {self.cog_name} Commands", color=Color.blurple())
        embed.description = "\n".join(page_commands) if page_commands else "No commands available."
        embed.add_field(name="🛠 Support Server", value=SUPPORT_SERVER, inline=False)
        embed.set_footer(text=f"Page {self.current_page+1}/{self.total_pages}")
        return embed

    async def prev_page(self, interaction: Interaction):
        self.current_page = (self.current_page - 1) % self.total_pages
        await interaction.response.edit_message(embed=self.get_page_embed(), view=self)

    async def next_page(self, interaction: Interaction):
        self.current_page = (self.current_page + 1) % self.total_pages
        await interaction.response.edit_message(embed=self.get_page_embed(), view=self)

    async def go_back(self, interaction: Interaction):
        view = HelpMenu(self.bot, self.cogs)
        first_cog = self.cogs[0]
        cog_obj = self.bot.cogs[first_cog]
        get_cmds = getattr(cog_obj, "get_app_commands", None)
        commands_list = []
        if callable(get_cmds):
            for cmd in get_cmds():
                if isinstance(cmd, app_commands.Command):
                    commands_list.append(f"`/{cmd.name}` - {cmd.description or 'No description'}")
        embed = Embed(title=f"📜 {first_cog} Commands", description="\n".join(commands_list), color=Color.blurple())
        embed.add_field(name="🛠 Support Server", value=f"[Click Here]({SUPPORT_SERVER})", inline=False)
        await interaction.response.edit_message(embed=embed, view=view)

# ------------------ Command Select Dropdown ------------------
class CommandSelect(discord.ui.Select):
    def __init__(self, bot: commands.Bot, cogs: List[str]):
        self.bot = bot
        self.cogs = cogs
        options = [discord.SelectOption(label=cog, description=f"Show commands for {cog}") for cog in cogs]
        super().__init__(placeholder="Select a category...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: Interaction):
        cog_name = self.values[0]
        cog = self.bot.cogs[cog_name]
        get_cmds = getattr(cog, "get_app_commands", None)
        commands_list = []
        if callable(get_cmds):
            for cmd in get_cmds():
                if isinstance(cmd, app_commands.Command):
                    commands_list.append(f"`/{cmd.name}` - {cmd.description or 'No description'}")
        view = PaginatedHelp(self.bot, cog_name, commands_list, self.cogs)
        await interaction.response.edit_message(embed=view.get_page_embed(), view=view)

# ------------------ Help Menu ------------------
class HelpMenu(discord.ui.View):
    def __init__(self, bot: commands.Bot, cogs: List[str]):
        super().__init__(timeout=None)
        self.bot = bot
        self.cogs = cogs
        self.add_item(CommandSelect(bot, cogs))

# ------------------ Help Command Cog ------------------
class HelpCommand(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.hidden_cogs = ["Bot Owner (cant use this commands!)", "CantDM", "BlockDM", "Logging", "HelpCommand", "Owner", "Utils", "CommandLister", "ErrorHandlerCog"]

    async def command_autocomplete(self, interaction: Interaction, current: str):
        suggestions = []
        for cog in self.bot.cogs.values():
            get_cmds = getattr(cog, "get_app_commands", None)
            if callable(get_cmds):
                for cmd in get_cmds():
                    if isinstance(cmd, app_commands.Command) and current.lower() in cmd.name.lower():
                        suggestions.append(app_commands.Choice(name=cmd.name, value=cmd.name))
        return suggestions[:25]

    @app_commands.command(name="help", description="Shows interactive help with autocomplete and pagination.")
    @app_commands.describe(command="Search for a command (autocomplete supported).")
    @app_commands.autocomplete(command=command_autocomplete)
    async def help(self, interaction: Interaction, command: Optional[str] = None):
        cogs = [c for c in sorted(self.bot.cogs.keys()) if c not in self.hidden_cogs]
        if command:
            for cog in self.bot.cogs.values():
                get_cmds = getattr(cog, "get_app_commands", None)
                if callable(get_cmds):
                    for cmd in get_cmds():
                        if isinstance(cmd, app_commands.Command) and cmd.name.lower() == command.lower():
                            embed = Embed(
                                title=f"📜 /{cmd.name} Command Info",
                                description=cmd.description or "No description provided.",
                                color=Color.blurple()
                            )
                            cog_name = cmd.cog.qualified_name if cmd.cog else "No Cog"
                            embed.add_field(name="Cog", value=cog_name, inline=True)
                            embed.add_field(name="Usage", value=f"`/{cmd.name}`", inline=True)
                            embed.add_field(name="🛠 Support Server", value=f"[Click Here]({SUPPORT_SERVER})", inline=False)
                            return await interaction.response.send_message(embed=embed, ephemeral=True)
            return await interaction.response.send_message(f"No command found with name `{command}`.", ephemeral=True)

        first_cog = self.bot.cogs[cogs[0]]
        get_cmds = getattr(first_cog, "get_app_commands", None)
        commands_list = []
        if callable(get_cmds):
            for cmd in get_cmds():
                if isinstance(cmd, app_commands.Command):
                    commands_list.append(f"`/{cmd.name}` - {cmd.description or 'No description'}")

        view = HelpMenu(self.bot, cogs)
        embed = Embed(title=f"📜 {cogs[0]} Commands", description="\n".join(commands_list), color=Color.blurple())
        embed.add_field(name="🛠 Support Server", value=f"[Click Here]({SUPPORT_SERVER})", inline=False)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

async def setup(bot: MaxyBot):
    await bot.add_cog(HelpCommand(bot))

async def setup(bot: MaxyBot):
    await bot.add_cog(General(bot))
    await bot.add_cog(HelpCommand(bot))
