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

class Moderation(commands.Cog, name="Moderation"):
    def __init__(self, bot: MaxyBot):
        self.bot = bot

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        await cog_command_error(interaction, error)

    @app_commands.command(name="purge", description="Deletes a specified number of messages.")
    @app_commands.describe(amount="The number of messages to delete (1-100).", user="Optional: The user whose messages to delete.")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def purge(self, interaction: discord.Interaction, amount: app_commands.Range[int, 1, 100], user: Optional[discord.Member] = None):
        await interaction.response.defer(ephemeral=True)
        
        deleted = []
        if user:
            # If a user is specified, create a check function
            check = lambda m: m.author == user
            deleted = await interaction.channel.purge(limit=amount, check=check)
        else:
            # If no user is specified, don't use a check function
            deleted = await interaction.channel.purge(limit=amount)
            
        user_str = f" from {user.mention}" if user else ""
        await interaction.followup.send(f"✅ Successfully deleted {len(deleted)} messages{user_str}.", ephemeral=True)

    @app_commands.command(name="kick", description="Kicks a member from the server.")
    @app_commands.describe(member="The member to kick.", reason="The reason for the kick.")
    @app_commands.checks.has_permissions(kick_members=True)
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = "No reason provided."):
        if member.id == interaction.user.id:
            return await interaction.response.send_message("You cannot kick yourself.", ephemeral=True)
        if member.top_role >= interaction.user.top_role and interaction.guild.owner.id != interaction.user.id:
            return await interaction.response.send_message("You cannot kick a member with a higher or equal role.", ephemeral=True)

        try:
            await member.kick(reason=f"{reason} (Kicked by {interaction.user})")
            await interaction.response.send_message(f"👢 Kicked {member.mention}. Reason: {reason}", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("I don't have permission to kick this member.", ephemeral=True)

    @app_commands.command(name="ban", description="Bans a member from the server.")
    @app_commands.describe(member="The member to ban.", reason="The reason for the ban.")
    @app_commands.checks.has_permissions(ban_members=True)
    async def ban(self, interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = "No reason provided."):
        if member.id == interaction.user.id:
            return await interaction.response.send_message("You cannot ban yourself.", ephemeral=True)
        if member.top_role >= interaction.user.top_role and interaction.guild.owner.id != interaction.user.id:
            return await interaction.response.send_message("You cannot ban a member with a higher or equal role.", ephemeral=True)

        try:
            await member.ban(reason=f"{reason} (Banned by {interaction.user})")
            await interaction.response.send_message(f"🔨 Banned {member.mention}. Reason: {reason}", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("I don't have permission to ban this member.", ephemeral=True)

    @app_commands.command(name="timeout", description="Mutes a member for a specified duration (e.g., 10m, 1h, 2d).")
    @app_commands.describe(member="The member to mute.", duration="Duration (e.g. 5m, 1h, 2d, 1w). Max 28 days.", reason="The reason for the mute.")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def timeout(self, interaction: discord.Interaction, member: discord.Member, duration: str, reason: Optional[str] = "No reason provided."):
        units = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
        seconds = 0
        match = re.findall(r"(\d+)([smhdw])", duration.lower())
        if not match:
            return await interaction.response.send_message("Invalid duration format. Use `10s`, `5m`, `2h`, `3d`, `1w`.", ephemeral=True)

        for value, unit in match:
            seconds += int(value) * units[unit]

        if seconds <= 0 or seconds > 2419200:
            return await interaction.response.send_message("Invalid duration. Duration must be between 1 second and 28 days.", ephemeral=True)

        delta = datetime.timedelta(seconds=seconds)
        try:
            await member.timeout(delta, reason=f"{reason} (Timed out by {interaction.user})")
            await interaction.response.send_message(f"🤫 Timed out {member.mention} for {humanize.naturaldelta(delta)}. Reason: {reason}", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("I don't have permission to timeout this member.", ephemeral=True)

    @app_commands.command(name="untimeout", description="Removes a timeout from a member.")
    @app_commands.describe(member="The member to untimeout.", reason="The reason for removing the timeout.")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def untimeout(self, interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = "No reason provided."):
        try:
            await member.timeout(None, reason=f"{reason} (Timeout removed by {interaction.user})")
            await interaction.response.send_message(f"😊 Removed timeout for {member.mention}.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("I don't have permission to manage this member's timeout.", ephemeral=True)

    @app_commands.command(name="unban", description="Unbans a user from the server.")
    @app_commands.describe(user_id="The ID of the user to unban.", reason="The reason for the unban.")
    @app_commands.checks.has_permissions(ban_members=True)
    async def unban(self, interaction: discord.Interaction, user_id: str, reason: Optional[str] = "No reason provided."):
        try:
            user = await self.bot.fetch_user(int(user_id))
            await interaction.guild.unban(user, reason=f"{reason} (Unbanned by {interaction.user})")
            await interaction.response.send_message(f"✅ Unbanned {user.mention}.", ephemeral=True)
        except (ValueError, TypeError):
            await interaction.response.send_message("Invalid User ID provided.", ephemeral=True)
        except discord.NotFound:
            await interaction.response.send_message("This user is not banned.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("I don't have permission to unban users.", ephemeral=True)

    @app_commands.command(name="warn", description="Warns a member and records it.")
    @app_commands.describe(member="The member to warn.", reason="The reason for the warning.")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def warn(self, interaction: discord.Interaction, member: discord.Member, reason: str):
        await self.bot.db.execute("INSERT INTO warnings (guild_id, user_id, moderator_id, reason) VALUES (?, ?, ?, ?)", (interaction.guild.id, member.id, interaction.user.id, reason))
        try:
            await member.send(f"You have been warned in **{interaction.guild.name}** for: `{reason}`")
        except discord.Forbidden:
            pass
        await interaction.response.send_message(f"⚠️ Warned {member.mention}. Reason: {reason}", ephemeral=True)

    @app_commands.command(name="warnings", description="Checks the warnings for a member.")
    @app_commands.describe(member="The member whose warnings to check.")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def warnings(self, interaction: discord.Interaction, member: discord.Member):
        results = await self.bot.db.fetchall("SELECT moderator_id, reason, timestamp, warn_id FROM warnings WHERE guild_id = ? AND user_id = ? ORDER BY timestamp DESC", (interaction.guild.id, member.id))
        if not results:
            return await interaction.response.send_message(f"{member.display_name} has no warnings.", ephemeral=True)

        embed = discord.Embed(title=f"Warnings for {member.display_name}", color=discord.Color.orange())
        for row in results[:10]:
            moderator = interaction.guild.get_member(row['moderator_id'])
            mod_name = moderator.mention if moderator else f"ID: {row['moderator_id']}"
            timestamp_dt = dt.fromisoformat(row['timestamp'])
            embed.add_field(name=f"Warn ID: {row['warn_id']} | {discord.utils.format_dt(timestamp_dt, style='R')}", value=f"**Reason:** {row['reason']}\n**Moderator:** {mod_name}", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="rmwarn", description="Removes a specific warning from a user.")
    @app_commands.describe(warn_id="The ID of the warning to remove.")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def rmwarn(self, interaction: discord.Interaction, warn_id: int):
        warning = await self.bot.db.fetchone("SELECT * FROM warnings WHERE warn_id = ? AND guild_id = ?", (warn_id, interaction.guild.id))
        if not warning:
            return await interaction.response.send_message("No warning found with that ID in this server.", ephemeral=True)

        await self.bot.db.execute("DELETE FROM warnings WHERE warn_id = ?", (warn_id,))
        await interaction.response.send_message(f"✅ Removed warning ID `{warn_id}`.", ephemeral=True)

    @app_commands.command(name="lock", description="Locks the current channel.")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def lock(self, interaction: discord.Interaction):
        channel = interaction.channel
        await channel.set_permissions(interaction.guild.default_role, send_messages=False)
        await interaction.response.send_message(f"🔒 Channel {channel.mention} has been locked.")

    @app_commands.command(name="unlock", description="Unlocks the current channel.")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def unlock(self, interaction: discord.Interaction):
        channel = interaction.channel
        await channel.set_permissions(interaction.guild.default_role, send_messages=None)
        await interaction.response.send_message(f"🔓 Channel {channel.mention} has been unlocked.")

    @app_commands.command(name="slowmode", description="Sets the slowmode for the current channel.")
    @app_commands.describe(seconds="The slowmode delay in seconds (0 to disable).")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def slowmode(self, interaction: discord.Interaction, seconds: app_commands.Range[int, 0, 21600]):
        await interaction.channel.edit(slowmode_delay=seconds)
        if seconds == 0:
            await interaction.response.send_message("Slowmode has been disabled for this channel.")
        else:
            await interaction.response.send_message(f"Slowmode has been set to {seconds} seconds.")

async def setup(bot: MaxyBot):
    await bot.add_cog(Moderation(bot))