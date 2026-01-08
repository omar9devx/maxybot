from __future__ import annotations
from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands
from discord.ext import commands
import random
import time

if TYPE_CHECKING:
    from ..bot import MaxyBot

from .utils import cog_command_error

class Leveling(commands.Cog, name="Leveling"):
    def __init__(self, bot: MaxyBot):
        self.bot = bot
        # قاموس لتخزين أوقات آخر رسالة لكل مستخدم لمنع الإسبام
        # Structure: {guild_id: {user_id: last_message_timestamp}}
        self.cooldowns = {}

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        await cog_command_error(interaction, error)

    # --- NEW: دالة معالجة نقاط الخبرة (XP) ---
    async def process_xp(self, message: discord.Message):
        # تجاهل البوتات والرسائل الخاصة
        if message.author.bot or not message.guild:
            return

        conf = self.bot.get_guild_config(message.guild.id)
        # التأكد من أن نظام الليفلات مفعل في السيرفر
        if not conf['leveling'].get('enabled', False):
             return

        guild_id = message.guild.id
        user_id = message.author.id
        current_time = time.time()

        # تطبيق نظام الكول داون (Cooldown)
        if guild_id not in self.cooldowns:
            self.cooldowns[guild_id] = {}

        # 60 ثانية كول داون بين الرسائل التي تمنح XP
        if user_id in self.cooldowns[guild_id] and current_time - self.cooldowns[guild_id][user_id] < 60:
            return
        
        # تحديث وقت آخر رسالة للمستخدم
        self.cooldowns[guild_id][user_id] = current_time

        # منح كمية عشوائية من XP (مثلاً بين 15 و 25)
        xp_to_add = random.randint(15, 25)
        await self.add_xp(guild_id, user_id, xp_to_add, message.channel, message.author)


    def get_xp_for_level(self, level: int) -> int:
        if level <= 0: return 100
        return 5 * (level ** 2) + 50 * level + 100

    async def add_xp(self, guild_id: int, user_id: int, xp_to_add: int, channel: discord.TextChannel, user: discord.Member):
        current_data = await self.bot.db.fetchone("SELECT xp, level FROM leveling WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))

        if not current_data:
            await self.bot.db.execute("INSERT INTO leveling (guild_id, user_id, xp, level) VALUES (?, ?, ?, ?)", (guild_id, user_id, xp_to_add, 0))
            current_xp = xp_to_add
            current_level = 0
        else:
            current_xp = current_data['xp'] + xp_to_add
            current_level = current_data['level']
            await self.bot.db.execute("UPDATE leveling SET xp = ? WHERE guild_id = ? AND user_id = ?", (current_xp, guild_id, user_id))

        xp_needed_for_next_level = self.get_xp_for_level(current_level)

        if current_xp >= xp_needed_for_next_level:
            new_level = current_level + 1
            # احتساب الـ XP المتبقي بعد الترقية
            remaining_xp = current_xp - xp_needed_for_next_level
            await self.bot.db.execute("UPDATE leveling SET level = ?, xp = ? WHERE guild_id = ? AND user_id = ?", (new_level, remaining_xp, guild_id, user_id))

            conf = self.bot.get_guild_config(guild_id)
            levelup_msg = conf['leveling'].get('levelup_message', "🎉 Congrats {user.mention}, you reached **Level {level}**!")
            try:
                await channel.send(levelup_msg.format(user=user, level=new_level), allowed_mentions=discord.AllowedMentions(users=True))
            except discord.Forbidden:
                pass

            reward = await self.bot.db.fetchone("SELECT role_id FROM level_rewards WHERE guild_id = ? AND level = ?", (guild_id, new_level))
            if reward:
                try:
                    role = user.guild.get_role(reward['role_id'])
                    if role:
                        await user.add_roles(role, reason=f"Level {new_level} reward")
                        await channel.send(f"🌟 As a reward, you've received the **{role.name}** role!")
                except Exception as e:
                    self.bot.logger.error(f"Failed to grant level reward role in guild {guild_id}: {e}")

    @app_commands.command(name="rank", description="Check your or another user's current rank and level.")
    @app_commands.describe(user="The user whose rank to check. Defaults to you.")
    async def rank(self, interaction: discord.Interaction, user: Optional[discord.Member] = None):
        target = user or interaction.user
        if target.bot:
            return await interaction.response.send_message("Bots don't have ranks!", ephemeral=True)
        await interaction.response.defer()
        data = await self.bot.db.fetchone("SELECT xp, level FROM leveling WHERE guild_id = ? AND user_id = ?", (interaction.guild.id, target.id))

        level = data['level'] if data else 0
        xp = data['xp'] if data else 0
        xp_for_next_level = self.get_xp_for_level(level)

        leaderboard = await self.bot.db.fetchall("SELECT user_id FROM leveling WHERE guild_id = ? ORDER BY level DESC, xp DESC", (interaction.guild.id,))
        rank = 0
        for i, entry in enumerate(leaderboard):
            if entry['user_id'] == target.id:
                rank = i + 1
                break

        embed = discord.Embed(title=f"Rank for {target.display_name}", color=target.color)
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="Level", value=f"`{level}`", inline=True)
        embed.add_field(name="Rank", value=f"`#{rank}`" if rank > 0 else "`Unranked`", inline=True)
        embed.add_field(name="Progress", value=f"`{xp} / {xp_for_next_level} XP`", inline=False)
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="leaderboard-levels", description="Shows the server's leveling leaderboard.")
    async def leaderboard_levels(self, interaction: discord.Interaction):
        await interaction.response.defer()
        query = "SELECT user_id, level, xp FROM leveling WHERE guild_id = ? ORDER BY level DESC, xp DESC LIMIT 10"
        results = await self.bot.db.fetchall(query, (interaction.guild.id,))

        if not results:
            return await interaction.followup.send("There is no one on the leaderboard yet!")

        embed = discord.Embed(title=f"🏆 Level Leaderboard for {interaction.guild.name}", color=discord.Color.gold())
        description = []
        for i, row in enumerate(results):
            user = interaction.guild.get_member(row['user_id'])
            username = user.display_name if user else f"User ID: {row['user_id']}"
            description.append(f"**{i+1}.** {username} - **Level {row['level']}** ({row['xp']} XP)")
        embed.description = "\n".join(description)
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="level-reward-add", description="[Admin] Set a role to be given at a certain level.")
    @app_commands.describe(level="The level to grant the role at.", role="The role to grant.")
    @app_commands.checks.has_permissions(administrator=True)
    async def add_level_reward(self, interaction: discord.Interaction, level: app_commands.Range[int, 1, 200], role: discord.Role):
        if role.is_default() or role.is_bot_managed():
            return await interaction.response.send_message("You cannot use this role as a reward.", ephemeral=True)
        await self.bot.db.execute("REPLACE INTO level_rewards (guild_id, level, role_id) VALUES (?, ?, ?)", (interaction.guild.id, level, role.id))
        await interaction.response.send_message(f"✅ Role {role.mention} will now be awarded at **Level {level}**.", ephemeral=True)

    @app_commands.command(name="level-reward-remove", description="[Admin] Remove a role reward for a specific level.")
    @app_commands.describe(level="The level of the reward to remove.")
    @app_commands.checks.has_permissions(administrator=True)
    async def remove_level_reward(self, interaction: discord.Interaction, level: app_commands.Range[int, 1, 200]):
        await self.bot.db.execute("DELETE FROM level_rewards WHERE guild_id = ? AND level = ?", (interaction.guild.id, level))
        await interaction.response.send_message(f"🗑️ Any role reward for **Level {level}** has been removed.", ephemeral=True)

async def setup(bot: MaxyBot):
    await bot.add_cog(Leveling(bot))