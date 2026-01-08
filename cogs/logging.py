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

class Logging(commands.Cog, name="Logging"):
    def __init__(self, bot: MaxyBot):
        self.bot = bot

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        await cog_command_error(interaction, error)

    async def get_log_channel(self, guild_id: int) -> Optional[discord.TextChannel]:
        conf = self.bot.get_guild_config(guild_id)
        log_conf = conf.get('logging', {})
        if not log_conf.get('enabled'):
            return None

        channel_id = log_conf.get('channel_id')
        if not channel_id:
            return None
        try:
            channel = self.bot.get_channel(int(channel_id))
            if isinstance(channel, discord.TextChannel):
                return channel
        except (ValueError, TypeError):
            return None
        return None

    async def log_message_delete(self, message: discord.Message):
        if not message.guild: return
        log_channel = await self.get_log_channel(message.guild.id)
        if not log_channel: return

        embed = discord.Embed(title="Message Deleted", description=f"Message sent by {message.author.mention} in {message.channel.mention} was deleted.", color=discord.Color.red(), timestamp=dt.now(UTC))
        content = message.content if message.content else "No message content (might be an embed or image)."
        embed.add_field(name="Content", value=f"```{content[:1020]}```", inline=False)
        embed.set_footer(text=f"Author ID: {message.author.id} | Message ID: {message.id}")
        await log_channel.send(embed=embed)

    async def log_message_edit(self, before: discord.Message, after: discord.Message):
        if not before.guild: return
        log_channel = await self.get_log_channel(before.guild.id)
        if not log_channel: return

        embed = discord.Embed(title="Message Edited", description=f"Message by {before.author.mention} in {before.channel.mention} was edited. [Jump to Message]({after.jump_url})", color=discord.Color.orange(), timestamp=dt.now(UTC))
        before_content = before.content if before.content else "N/A"
        after_content = after.content if after.content else "N/A"
        embed.add_field(name="Before", value=f"```{before_content[:1020]}```", inline=False)
        embed.add_field(name="After", value=f"```{after_content[:1020]}```", inline=False)
        embed.set_footer(text=f"Author ID: {before.author.id} | Message ID: {before.id}")
        await log_channel.send(embed=embed)

    async def log_member_update(self, before: discord.Member, after: discord.Member):
        log_channel = await self.get_log_channel(before.guild.id)
        if not log_channel: return

        if before.nick != after.nick:
            embed = discord.Embed(color=discord.Color.blue(), timestamp=dt.now(UTC))
            embed.set_author(name=f"{after} ({after.id})", icon_url=after.display_avatar.url)
            embed.title = "Nickname Changed"
            embed.add_field(name="Before", value=f"`{before.nick}`", inline=True)
            embed.add_field(name="After", value=f"`{after.nick}`", inline=True)
            await log_channel.send(embed=embed)

        if before.roles != after.roles:
            embed = discord.Embed(color=discord.Color.blue(), timestamp=dt.now(UTC))
            embed.set_author(name=f"{after} ({after.id})", icon_url=after.display_avatar.url)
            embed.title = "Roles Updated"
            added_roles = [r.mention for r in after.roles if r not in before.roles]
            removed_roles = [r.mention for r in before.roles if r not in after.roles]

            if added_roles:
                embed.add_field(name="Added Roles", value=", ".join(added_roles), inline=False)
            if removed_roles:
                embed.add_field(name="Removed Roles", value=", ".join(removed_roles), inline=False)

            if added_roles or removed_roles:
                await log_channel.send(embed=embed)

    async def log_role_create(self, role: discord.Role):
        log_channel = await self.get_log_channel(role.guild.id)
        if not log_channel: return
        embed = discord.Embed(title="Role Created", description=f"Role {role.mention} (`{role.name}`) was created.", color=discord.Color.green(), timestamp=dt.now(UTC))
        await log_channel.send(embed=embed)

    async def log_role_delete(self, role: discord.Role):
        log_channel = await self.get_log_channel(role.guild.id)
        if not log_channel: return
        embed = discord.Embed(title="Role Deleted", description=f"Role `{role.name}` was deleted.", color=discord.Color.red(), timestamp=dt.now(UTC))
        await log_channel.send(embed=embed)

    async def log_role_update(self, before: discord.Role, after: discord.Role):
        log_channel = await self.get_log_channel(before.guild.id)
        if not log_channel: return
        if before.name == after.name and before.color == after.color and before.permissions == after.permissions: return

        description = f"Role {after.mention} was updated."
        embed = discord.Embed(title="Role Updated", description=description, color=discord.Color.blue(), timestamp=dt.now(UTC))
        if before.name != after.name:
            embed.add_field(name="Name Change", value=f"`{before.name}` -> `{after.name}`", inline=False)
        if before.color != after.color:
            embed.add_field(name="Color Change", value=f"`{before.color}` -> `{after.color}`", inline=False)
        if before.permissions != after.permissions:
            embed.add_field(name="Permissions Changed", value="Use audit log for details.", inline=False)
        await log_channel.send(embed=embed)

    async def log_channel_create(self, channel: discord.abc.GuildChannel):
        log_channel = await self.get_log_channel(channel.guild.id)
        if not log_channel: return
        embed = discord.Embed(title="Channel Created", description=f"Channel {channel.mention} (`{channel.name}`) was created.", color=discord.Color.green(), timestamp=dt.now(UTC))
        await log_channel.send(embed=embed)

    async def log_channel_delete(self, channel: discord.abc.GuildChannel):
        log_channel = await self.get_log_channel(channel.guild.id)
        if not log_channel: return
        embed = discord.Embed(title="Channel Deleted", description=f"Channel `{channel.name}` was deleted.", color=discord.Color.red(), timestamp=dt.now(UTC))
        await log_channel.send(embed=embed)

    async def log_channel_update(self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel):
        log_channel = await self.get_log_channel(before.guild.id)
        if not log_channel: return
        embed = discord.Embed(title="Channel Updated", description=f"Channel {after.mention} was updated.", color=discord.Color.blue(), timestamp=dt.now(UTC))
        if before.name != after.name:
            embed.add_field(name="Name Change", value=f"`{before.name}` -> `{after.name}`", inline=False)
        if isinstance(before, discord.TextChannel) and isinstance(after, discord.TextChannel) and before.topic != after.topic:
            embed.add_field(name="Topic Change", value="Topic was updated.", inline=False)
        if len(embed.fields) > 0:
            await log_channel.send(embed=embed)

    async def log_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        log_channel = await self.get_log_channel(member.guild.id)
        if not log_channel: return
        embed = discord.Embed(timestamp=dt.now(UTC))
        embed.set_author(name=member, icon_url=member.display_avatar.url)
        if not before.channel and after.channel:
            embed.title = "Member Joined Voice"
            embed.description = f"{member.mention} joined voice channel {after.channel.mention}"
            embed.color = discord.Color.green()
            await log_channel.send(embed=embed)
        elif before.channel and not after.channel:
            embed.title = "Member Left Voice"
            embed.description = f"{member.mention} left voice channel {before.channel.mention}"
            embed.color = discord.Color.red()
            await log_channel.send(embed=embed)
        elif before.channel and after.channel and before.channel != after.channel:
            embed.title = "Member Moved Voice"
            embed.description = f"{member.mention} moved from {before.channel.mention} to {after.channel.mention}"
            embed.color = discord.Color.blue()
            await log_channel.send(embed=embed)

async def setup(bot: MaxyBot):
    await bot.add_cog(Logging(bot))