# -*- coding: utf-8 -*-
import discord
from discord.ext import commands
from discord import app_commands
import os
from datetime import datetime
import traceback

class LeaveServer(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.log_file = "logs.txt"
        self.server_file = "servers.txt"

        if not os.path.exists(self.log_file):
            with open(self.log_file, "w", encoding="utf-8") as f:
                f.write("==== HighLogs Started ====\n")

        if not os.path.exists(self.server_file):
            with open(self.server_file, "w", encoding="utf-8") as f:
                f.write("==== Server Logs Started ====\n")

    def write_log(self, message: str, file: str = None):
        target_file = file if file else self.log_file
        with open(target_file, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}] {message}\n")

    # ✅ Slash Commands logging
    @commands.Cog.listener()
    async def on_app_command_completion(self, interaction: discord.Interaction, command: app_commands.Command):
        user = interaction.user
        guild_id = interaction.guild.id if interaction.guild else "DM"
        cog_name = command.callback.__module__
        log_message = (
            f"{user} used /{command.qualified_name} "
            f"[used id: {user.id}, guild id: {guild_id}, command from cog: {cog_name}]"
        )
        self.write_log(log_message)

    # ✅ Prefix Commands logging
    @commands.Cog.listener()
    async def on_command_completion(self, ctx: commands.Context):
        user = ctx.author
        guild_id = ctx.guild.id if ctx.guild else "DM"
        cog_name = ctx.command.cog_name
        log_message = (
            f"{user} used {ctx.command.qualified_name} "
            f"[used id: {user.id}, guild id: {guild_id}, command from cog: {cog_name}]"
        )
        self.write_log(log_message)

    # ❌ Errors logging
    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        user = ctx.author
        guild_id = ctx.guild.id if ctx.guild else "DM"
        log_message = (
            f"ERROR in {ctx.command.qualified_name if ctx.command else 'Unknown'} "
            f"[user: {user}, user id: {user.id}, guild id: {guild_id}] "
            f"=> {error}"
        )
        self.write_log(log_message)
        self.write_log("Traceback:\n" + "".join(traceback.format_exception(type(error), error, error.__traceback__)))

    @commands.Cog.listener()
    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        user = interaction.user
        guild_id = interaction.guild.id if interaction.guild else "DM"
        log_message = (
            f"ERROR in /{interaction.command.qualified_name if interaction.command else 'Unknown'} "
            f"[user: {user}, user id: {user.id}, guild id: {guild_id}] "
            f"=> {error}"
        )
        self.write_log(log_message)
        self.write_log("Traceback:\n" + "".join(traceback.format_exception(type(error), error, error.__traceback__)))

    # 🏠 Server Join logging
    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        owner = guild.owner
        created_at = guild.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
        roles_count = len(guild.roles) - 1  # طرح @everyone

        server_info = (
            f"Bot joined new server!\n"
            f" ├─ Server Name: {guild.name}\n"
            f" ├─ Server ID: {guild.id}\n"
            f" ├─ Owner: {owner} (ID: {owner.id if owner else 'Unknown'})\n"
            f" ├─ Members: {guild.member_count}\n"
            f" ├─ Roles: {roles_count}\n"
            f" ├─ Text Channels: {len(guild.text_channels)}\n"
            f" ├─ Voice Channels: {len(guild.voice_channels)}\n"
            f" └─ Created At: {created_at}\n"
            f"{'='*50}"
        )
        self.write_log(server_info, file=self.server_file)

    # ❌ Server Leave logging
    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        owner = guild.owner
        created_at = guild.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
        roles_count = len(guild.roles) - 1

        # مبدئيًا السبب Unknown (Kick/Ban/Leave)
        reason = "Unknown (Kick/Ban/Leave)"

        server_info = (
            f"Bot removed from server!\n"
            f" ├─ Server Name: {guild.name}\n"
            f" ├─ Server ID: {guild.id}\n"
            f" ├─ Owner: {owner} (ID: {owner.id if owner else 'Unknown'})\n"
            f" ├─ Members: {guild.member_count}\n"
            f" ├─ Roles: {roles_count}\n"
            f" ├─ Text Channels: {len(guild.text_channels)}\n"
            f" ├─ Voice Channels: {len(guild.voice_channels)}\n"
            f" ├─ Reason: {reason}\n"
            f" └─ Created At: {created_at}\n"
            f"{'='*50}"
        )
        self.write_log(server_info, file=self.server_file)

    # 🚪 /leave command
    @app_commands.command(name="leave", description="Make the bot leave the server safely (Admin only)")
    @app_commands.checks.has_permissions(administrator=True)
    async def leave_command(self, interaction: discord.Interaction):
        class Confirm(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=30)
                self.value = None

            @discord.ui.button(label="✅ Confirm", style=discord.ButtonStyle.danger)
            async def confirm(self, interaction2: discord.Interaction, button: discord.ui.Button):
                await interaction2.response.send_message("Leaving the server... 👋", ephemeral=True)
                await interaction2.guild.leave()

            @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.secondary)
            async def cancel(self, interaction2: discord.Interaction, button: discord.ui.Button):
                await interaction2.response.send_message("Leave cancelled.", ephemeral=True)
                self.stop()

        await interaction.response.send_message("⚠️ Are you sure you want me to leave this server?", view=Confirm(), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(LeaveServer(bot))
