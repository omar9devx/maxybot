from __future__ import annotations
from typing import TYPE_CHECKING, Optional, List
import discord
from discord import app_commands
from discord.ext import commands, tasks
import datetime
from datetime import datetime as dt, UTC
import random
import re

if TYPE_CHECKING:
    from ..bot import MaxyBot

from .utils import cog_command_error

class Giveaways(commands.Cog, name="Giveaways"):
    def __init__(self, bot: MaxyBot):
        self.bot = bot
        self.check_giveaways.start()

    def cog_unload(self):
        self.check_giveaways.cancel()

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        await cog_command_error(interaction, error)

    class GiveawayJoinView(discord.ui.View):
        def __init__(self, bot: 'MaxyBot', message_id: int, required_role: Optional[int] = None):
            super().__init__(timeout=None)
            self.bot = bot
            self.message_id = message_id
            self.required_role = required_role
            self.add_item(discord.ui.Button(label="Join", style=discord.ButtonStyle.success, custom_id=f"join_giveaway_{message_id}", emoji="🎉"))

        async def interaction_check(self, interaction: discord.Interaction) -> bool:
            if interaction.data['custom_id'] != f"join_giveaway_{self.message_id}":
                return False

            await interaction.response.defer(ephemeral=True)

            if interaction.user.bot:
                await interaction.followup.send("Bots can’t join giveaways!", ephemeral=True)
                return False

            if self.required_role and self.required_role not in [r.id for r in interaction.user.roles]:
                await interaction.followup.send("You don’t meet the role requirement to join this giveaway!", ephemeral=True)
                return False

            is_entrant = await self.bot.db.fetchone("SELECT 1 FROM giveaway_entrants WHERE message_id = ? AND user_id = ?", (self.message_id, interaction.user.id))
            if is_entrant:
                await interaction.followup.send("You already entered this giveaway!", ephemeral=True)
                return False

            await self.bot.db.execute("INSERT INTO giveaway_entrants (message_id, user_id) VALUES (?, ?)", (self.message_id, interaction.user.id))
            await interaction.followup.send("✅ You successfully joined the giveaway!", ephemeral=True)
            return False

    # Utility: parse duration
    def parse_duration(self, duration: str) -> Optional[int]:
        units = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
        seconds = 0
        match = re.findall(r"(\d+)([smhdw])", duration.lower())
        if not match:
            return None
        for value, unit in match:
            seconds += int(value) * units[unit]
        return seconds

    @app_commands.command(name="g-start", description="[Admin] Start a new giveaway.")
    @app_commands.describe(duration="Duration (e.g., 10m, 1h, 2d).", winners="Number of winners.", prize="Prize.", required_role="Role required to join (optional).")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def g_start(self, interaction: discord.Interaction, duration: str, winners: app_commands.Range[int, 1, 20], prize: str, required_role: Optional[discord.Role] = None):
        seconds = self.parse_duration(duration)
        if not seconds:
            return await interaction.response.send_message("Invalid duration format.", ephemeral=True)

        end_time = dt.now(UTC) + datetime.timedelta(seconds=seconds)
        end_timestamp = int(end_time.timestamp())

        embed = discord.Embed(title=f"🎉 GIVEAWAY: {prize}", description=f"Click the button to enter!\nEnds: <t:{end_timestamp}:R> (<t:{end_timestamp}:F>)\nHosted by: {interaction.user.mention}", color=discord.Color.gold())
        embed.set_footer(text=f"{winners} winner(s) | Ends at")
        embed.timestamp = end_time

        await interaction.response.send_message("Giveaway created!", ephemeral=True)
        message = await interaction.channel.send(embed=embed)

        view = self.GiveawayJoinView(self.bot, message.id, required_role.id if required_role else None)
        self.bot.add_view(view, message_id=message.id)

        await self.bot.db.execute("INSERT INTO giveaways (message_id, guild_id, channel_id, prize, end_timestamp, winner_count, required_role, is_ended) VALUES (?, ?, ?, ?, ?, ?, ?, 0)", (message.id, interaction.guild.id, interaction.channel.id, prize, end_time.timestamp(), winners, required_role.id if required_role else None))

    @app_commands.command(name="g-end", description="[Admin] End a giveaway early.")
    @app_commands.describe(message_id="Giveaway message ID")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def g_end(self, interaction: discord.Interaction, message_id: str):
        g = await self.bot.db.fetchone("SELECT * FROM giveaways WHERE message_id = ?", (message_id,))
        if not g or g['is_ended']:
            return await interaction.response.send_message("No active giveaway found with that ID.", ephemeral=True)

        await self._end_giveaway(g)
        await interaction.response.send_message("Giveaway ended early.", ephemeral=True)

    @app_commands.command(name="g-reroll", description="[Admin] Reroll winners for a giveaway.")
    @app_commands.describe(message_id="Giveaway message ID")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def g_reroll(self, interaction: discord.Interaction, message_id: str):
        g = await self.bot.db.fetchone("SELECT * FROM giveaways WHERE message_id = ?", (message_id,))
        if not g or not g['is_ended']:
            return await interaction.response.send_message("This giveaway has not ended yet.", ephemeral=True)

        entrants = await self.bot.db.fetchall("SELECT user_id FROM giveaway_entrants WHERE message_id = ?", (g['message_id'],))
        if not entrants:
            return await interaction.response.send_message("No entrants for this giveaway.", ephemeral=True)

        entrant_ids = [e['user_id'] for e in entrants]
        winners = random.sample(entrant_ids, k=min(g['winner_count'], len(entrant_ids)))
        mentions = ', '.join(f"<@{w}>" for w in winners)
        await interaction.response.send_message(f"🎉 New winners: {mentions}")

    @app_commands.command(name="g-list", description="List active giveaways.")
    async def g_list(self, interaction: discord.Interaction):
        active = await self.bot.db.fetchall("SELECT * FROM giveaways WHERE is_ended = 0 AND guild_id = ?", (interaction.guild.id,))
        if not active:
            return await interaction.response.send_message("No active giveaways.", ephemeral=True)

        desc = "\n".join([f"**{g['prize']}** (ID: {g['message_id']}) - Ends <t:{int(g['end_timestamp'])}:R>" for g in active])
        embed = discord.Embed(title="Active Giveaways", description=desc, color=discord.Color.blurple())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _end_giveaway(self, g):
        channel = self.bot.get_channel(g['channel_id'])
        if not channel:
            await self.bot.db.execute("UPDATE giveaways SET is_ended = 1 WHERE message_id = ?", (g['message_id'],))
            return

        try:
            message = await channel.fetch_message(g['message_id'])
        except discord.NotFound:
            await self.bot.db.execute("UPDATE giveaways SET is_ended = 1 WHERE message_id = ?", (g['message_id'],))
            return

        entrants = await self.bot.db.fetchall("SELECT user_id FROM giveaway_entrants WHERE message_id = ?", (g['message_id'],))
        entrant_ids = [e['user_id'] for e in entrants]
        winner_count = min(g['winner_count'], len(entrant_ids))
        winners = random.sample(entrant_ids, k=winner_count) if entrant_ids else []
        winner_mentions = [f"<@{w_id}>" for w_id in winners]

        new_embed = message.embeds[0].to_dict()
        new_embed['title'] = f"🎉 GIVEAWAY ENDED: {g['prize']}"
        new_embed['description'] = f"Winners: {', '.join(winner_mentions) if winners else 'No one!'}\nHosted by: {new_embed['description'].split('Hosted by: ')[1]}"
        new_embed['color'] = discord.Color.dark_grey().value

        await message.edit(embed=discord.Embed.from_dict(new_embed), view=None)

        if winners:
            await message.reply(f"🎉 Congratulations {', '.join(winner_mentions)}! You won **{g['prize']}**!")
        else:
            await message.reply(f"The giveaway for **{g['prize']}** ended, but there were no entrants.")

        await self.bot.db.execute("UPDATE giveaways SET is_ended = 1 WHERE message_id = ?", (g['message_id'],))

    @tasks.loop(seconds=15)
    async def check_giveaways(self):
        giveaways = await self.bot.db.fetchall("SELECT * FROM giveaways WHERE is_ended = 0 AND end_timestamp < ?", (dt.now(UTC).timestamp(),))
        for g in giveaways:
            await self._end_giveaway(g)

    @check_giveaways.before_loop
    async def before_check_giveaways(self):
        await self.bot.wait_until_ready()

async def setup(bot: MaxyBot):
    await bot.add_cog(Giveaways(bot))
