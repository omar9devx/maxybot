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

class Music(commands.Cog, name="Music"):
    def __init__(self, bot: MaxyBot):
        self.bot = bot
        self.FFMPEG_OPTIONS = {'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5', 'options': '-vn'}
        self.ytdl = yt_dlp.YoutubeDL({
            'format': 'bestaudio/best', 'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
            'restrictfilenames': True, 'noplaylist': True, 'nocheckcertificate': True,
            'ignoreerrors': False, 'logtostderr': False, 'quiet': True, 'no_warnings': True,
            'default_search': 'auto', 'source_address': '0.0.0.0'
        })
        self.queues = {}
        self.current_song = {}
        self.loop_states = {}

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        await cog_command_error(interaction, error)

    def play_next(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        loop_state = self.loop_states.get(guild_id, 'none')

        if loop_state == 'song' and self.current_song.get(guild_id):
            song_to_play = self.current_song[guild_id]
        else:
            if guild_id not in self.queues or not self.queues[guild_id]:
                self.current_song.pop(guild_id, None)
                asyncio.run_coroutine_threadsafe(interaction.channel.send("Queue finished!"), self.bot.loop)
                return

            if loop_state == 'queue' and self.current_song.get(guild_id):
                self.queues[guild_id].append(self.current_song[guild_id])

            song_to_play = self.queues[guild_id].pop(0)

        self.current_song[guild_id] = song_to_play
        vc = interaction.guild.voice_client
        if vc:
            player = discord.FFmpegPCMAudio(song_to_play['url'], **self.FFMPEG_OPTIONS)
            vc.play(player, after=lambda e: self.play_next(interaction))

    @app_commands.command(name="play", description="Plays a song from YouTube or adds it to the queue.")
    @app_commands.describe(query="The song name or YouTube URL.")
    async def play(self, interaction: discord.Interaction, query: str):
        if not interaction.user.voice:
            return await interaction.response.send_message("You need to be in a voice channel to play music.", ephemeral=True)

        await interaction.response.defer()

        vc: discord.VoiceClient = interaction.guild.voice_client
        if not vc:
            vc = await interaction.user.voice.channel.connect()

        try:
            loop = self.bot.loop or asyncio.get_event_loop()
            data = await loop.run_in_executor(None, lambda: self.ytdl.extract_info(query, download=False))
            song = data['entries'][0] if 'entries' in data else data

            if interaction.guild.id not in self.queues:
                self.queues[interaction.guild.id] = []

            self.queues[interaction.guild.id].append(song)

            if not vc.is_playing():
                embed = discord.Embed(title="🎵 Now Playing", description=f"[{song['title']}]({song['webpage_url']})", color=discord.Color.green())
                embed.set_thumbnail(url=song.get('thumbnail'))
                await interaction.followup.send(embed=embed)
                self.play_next(interaction)
            else:
                embed = discord.Embed(title="✅ Added to Queue", description=f"[{song['title']}]({song['webpage_url']})", color=discord.Color.blue())
                embed.set_thumbnail(url=song.get('thumbnail'))
                await interaction.followup.send(embed=embed)
        except Exception as e:
            self.bot.logger.error(f"Music play error: {e}", exc_info=True)
            await interaction.followup.send(f"An error occurred while trying to play the song. It might be age-restricted or private.")

    @app_commands.command(name="stop", description="Stops the music and disconnects the bot.")
    async def stop(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        guild_id = interaction.guild.id
        if vc and vc.is_connected():
            if guild_id in self.queues: self.queues[guild_id].clear()
            self.current_song.pop(guild_id, None)
            self.loop_states.pop(guild_id, None)
            await vc.disconnect()
            await interaction.response.send_message("⏹️ Music stopped and disconnected.", ephemeral=True)
        else:
            await interaction.response.send_message("I'm not connected to a voice channel.", ephemeral=True)

    @app_commands.command(name="skip", description="Skips the current song.")
    async def skip(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        if vc and vc.is_playing():
            vc.stop()
            await interaction.response.send_message("⏭️ Skipped the current song.", ephemeral=True)
        else:
            await interaction.response.send_message("I'm not playing anything right now.", ephemeral=True)

    @app_commands.command(name="pause", description="Pauses the current song.")
    async def pause(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        if vc and vc.is_playing():
            vc.pause()
            await interaction.response.send_message("⏸️ Paused the music.", ephemeral=True)
        else:
            await interaction.response.send_message("I'm not playing anything to pause.", ephemeral=True)

    @app_commands.command(name="resume", description="Resumes the paused song.")
    async def resume(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        if vc and vc.is_paused():
            vc.resume()
            await interaction.response.send_message("▶️ Resumed the music.", ephemeral=True)
        else:
            await interaction.response.send_message("There's nothing to resume.", ephemeral=True)

    @app_commands.command(name="queue", description="Shows the current song queue.")
    async def queue(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        if not guild_id in self.queues or not self.queues[guild_id]:
            return await interaction.response.send_message("The queue is empty.", ephemeral=True)

        embed = discord.Embed(title="🎵 Music Queue", color=discord.Color.blue())
        queue_list = ""
        for i, song in enumerate(self.queues[guild_id][:10]):
            queue_list += f"`{i+1}.` {song['title']}\n"
        embed.description = queue_list
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="nowplaying", description="Shows the currently playing song.")
    async def nowplaying(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        song = self.current_song.get(guild_id)
        if not song or not interaction.guild.voice_client.is_playing():
            return await interaction.response.send_message("Nothing is playing right now.", ephemeral=True)

        embed = discord.Embed(title="🎵 Now Playing", description=f"[{song['title']}]({song['webpage_url']})", color=discord.Color.green())
        embed.set_thumbnail(url=song.get('thumbnail'))
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="shuffle", description="Shuffles the queue.")
    async def shuffle(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        if guild_id in self.queues and len(self.queues[guild_id]) > 1:
            random.shuffle(self.queues[guild_id])
            await interaction.response.send_message("🔀 Queue has been shuffled.", ephemeral=True)
        else:
            await interaction.response.send_message("Not enough songs in the queue to shuffle.", ephemeral=True)

    @app_commands.command(name="loop", description="Sets the loop mode.")
    @app_commands.describe(mode="The loop mode: none, song, or queue.")
    @app_commands.choices(mode=[
        app_commands.Choice(name="None", value="none"),
        app_commands.Choice(name="Current Song", value="song"),
        app_commands.Choice(name="Entire Queue", value="queue")
    ])
    async def loop(self, interaction: discord.Interaction, mode: app_commands.Choice[str]):
        self.loop_states[interaction.guild.id] = mode.value
        await interaction.response.send_message(f"🔄 Loop mode set to **{mode.name}**.", ephemeral=True)

async def setup(bot: MaxyBot):
    await bot.add_cog(Music(bot))