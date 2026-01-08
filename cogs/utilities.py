# -*- coding: utf-8 -*-

# --- Imports ---
from __future__ import annotations
from typing import TYPE_CHECKING, Optional, List, Dict

import discord
from discord import app_commands
from discord.ext import commands, tasks

import re
import json
from datetime import datetime as dt, UTC, timedelta
import humanize

if TYPE_CHECKING:
    from ..bot import MaxyBot # تأكد من صحة مسار الاستيراد هذا

from .utils import cog_command_error # افتراض وجود هذه الدالة المساعدة

# --- SQL SCHEMA ---
# ضع هذا في قاعدة بيانات SQLite الخاصة بك
#
# CREATE TABLE IF NOT EXISTS afk (
#   guild_id INTEGER NOT NULL,
#   user_id INTEGER NOT NULL,
#   reason TEXT,
#   timestamp TEXT,
#   PRIMARY KEY (guild_id, user_id)
# );
#
# CREATE TABLE IF NOT EXISTS reminders (
#   reminder_id INTEGER PRIMARY KEY AUTOINCREMENT,
#   user_id INTEGER NOT NULL,
#   channel_id INTEGER NOT NULL,
#   remind_content TEXT,
#   remind_timestamp REAL
# );
#
# CREATE TABLE IF NOT EXISTS polls (
#   message_id INTEGER PRIMARY KEY,
#   guild_id INTEGER NOT NULL,
#   channel_id INTEGER NOT NULL,
#   author_id INTEGER NOT NULL,
#   end_timestamp REAL,
#   question TEXT,
#   options TEXT
# );
#
# --- Constants ---
POLL_EMOJIS = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣', '🔟']
SUCCESS_COLOR = discord.Color.green()
ERROR_COLOR = discord.Color.red()
INFO_COLOR = discord.Color.blurple()


# --- Helper Functions ---
def parse_duration(duration_str: str) -> Optional[timedelta]:
    """
    يُحلل سلسلة نصية للوقت (مثل '1d3h30m') ويحولها إلى كائن timedelta.
    Parses a duration string (e.g., '1d3h30m') into a timedelta object.
    """
    regex = r"(\d+)\s*(w|d|h|m|s)"
    matches = re.findall(regex, duration_str.lower())
    if not matches:
        return None
    
    delta_args = {"weeks": 0, "days": 0, "hours": 0, "minutes": 0, "seconds": 0}
    unit_map = {
        'w': 'weeks', 'd': 'days', 'h': 'hours', 'm': 'minutes', 's': 'seconds'
    }
    
    for value, unit in matches:
        delta_args[unit_map[unit]] += int(value)
        
    return timedelta(**delta_args)

# --- Main Cog Class ---
class Utilities(commands.Cog, name="Utilities"):
    """
    كوج يحتوي على أوامر مفيدة متنوعة للاستخدام اليومي في السيرفر.
    A cog with various useful commands for everyday server use.
    """
    
    def __init__(self, bot: MaxyBot):
        self.bot = bot
        self.check_reminders.start()
        self.check_polls.start()

    def cog_unload(self):
        """إيقاف المهام الخلفية عند إلغاء تحميل الكوج."""
        self.check_reminders.cancel()
        self.check_polls.cancel()

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """معالج أخطاء مخصص لأوامر هذا الكوج."""
        await cog_command_error(interaction, error)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """
        يتعامل مع إزالة حالة AFK والإشارة إلى المستخدمين في حالة AFK.
        Handles AFK status removal and mentions.
        """
        if message.author.bot or not message.guild:
            return

        # 1. التعامل مع عودة المستخدم من AFK
        # التأكد مما إذا كان كاتب الرسالة موجودًا في قاعدة بيانات AFK
        is_afk = await self.bot.db.fetchone(
            "SELECT 1 FROM afk WHERE guild_id = ? AND user_id = ?",
            (message.guild.id, message.author.id)
        )
        if is_afk:
            await self.bot.db.execute(
                "DELETE FROM afk WHERE guild_id = ? AND user_id = ?",
                (message.guild.id, message.author.id)
            )
            await message.channel.send(f"أهلاً بعودتك {message.author.mention}! لقد أزلت حالة الـ AFK عنك.", delete_after=10)
            try:
                # محاولة إزالة [AFK] من اللقب
                if message.author.display_name.startswith("[AFK]"):
                    new_nick = message.author.display_name.replace("[AFK] ", "", 1)
                    await message.author.edit(nick=new_nick)
            except discord.Forbidden:
                pass # لا يمكن تغيير اللقب، ولكن تمت إزالة حالة AFK
            return # التوقف لتجنب الرد على رسالة "أهلاً بعودتك"

        # 2. التعامل مع الإشارة إلى مستخدمين في حالة AFK
        if not message.mentions:
            return

        mentioned_afk_users = []
        for user in message.mentions:
            afk_data = await self.bot.db.fetchone(
                "SELECT reason, timestamp FROM afk WHERE guild_id = ? AND user_id = ?",
                (message.guild.id, user.id)
            )
            if afk_data:
                timestamp = dt.fromisoformat(afk_data['timestamp'])
                afk_time = humanize.naturaltime(dt.now(UTC) - timestamp)
                mentioned_afk_users.append(f"**{user.display_name}** غائب حاليًا: `{afk_data['reason']}` ({afk_time})")
        
        if mentioned_afk_users:
            await message.channel.send("\n".join(mentioned_afk_users), allowed_mentions=discord.AllowedMentions.none())

    # --- AFK Commands ---
    @app_commands.command(name="afk", description="يضبط حالتك إلى AFK (بعيد عن لوحة المفاتيح).")
    @app_commands.describe(reason="سبب غيابك.")
    async def afk(self, interaction: discord.Interaction, reason: str = "لا يوجد سبب"):
        """يضبط حالة المستخدم إلى AFK، والتي تُعرض عند الإشارة إليه."""
        await self.bot.db.execute(
            "REPLACE INTO afk (guild_id, user_id, reason, timestamp) VALUES (?, ?, ?, ?)",
            (interaction.guild.id, interaction.user.id, reason, dt.now(UTC).isoformat())
        )
        await interaction.response.send_message(f"تم ضبط حالتك إلى AFK. السبب: `{reason}`", ephemeral=True)
        try:
            current_nick = interaction.user.display_name
            if not current_nick.startswith("[AFK]"):
                await interaction.user.edit(nick=f"[AFK] {current_nick}")
        except discord.Forbidden:
            await interaction.followup.send("لم أتمكن من تغيير لقبك، لكن تم تفعيل حالة AFK.", ephemeral=True)

    # --- Poll Commands ---
    @app_commands.command(name="poll", description="ينشئ استطلاعًا مع خيارات، ويمكن تحديد مدة له.")
    @app_commands.describe(
        question="سؤال الاستطلاع.",
        options="ما يصل إلى 10 خيارات، مفصولة بـ '|'.",
        duration="مدة الاستطلاع (مثال: '10m', '1h30m', '2d')."
    )
    async def poll(self, interaction: discord.Interaction, question: str, options: str, duration: Optional[str] = None):
        """ينشئ استطلاعًا تفاعليًا يمكن أن ينتهي تلقائيًا ويعرض النتائج."""
        option_list = [opt.strip() for opt in options.split('|')]
        if not (2 <= len(option_list) <= 10):
            return await interaction.response.send_message("يجب تقديم ما بين 2 و 10 خيارات، مفصولة بـ '|'.", ephemeral=True)
        
        description_lines = [f"{POLL_EMOJIS[i]} {option}" for i, option in enumerate(option_list)]
        
        embed = discord.Embed(
            title=f"📊 استطلاع: {question}",
            description="\n".join(description_lines),
            color=INFO_COLOR,
            timestamp=dt.now(UTC)
        )
        embed.set_footer(text=f"بدأه {interaction.user.display_name}", icon_url=interaction.user.display_avatar)

        end_time = None
        if duration:
            delta = parse_duration(duration)
            if not delta or delta.total_seconds() <= 0:
                return await interaction.response.send_message("تنسيق المدة غير صالح. استخدم 'w', 'd', 'h', 'm', 's'.", ephemeral=True)
            end_time = dt.now(UTC) + delta
            embed.add_field(name="⏰ ينتهي", value=f"{discord.utils.format_dt(end_time, 'R')}", inline=False)

        await interaction.response.send_message(embed=embed)
        message = await interaction.original_response()

        for i in range(len(option_list)):
            await message.add_reaction(POLL_EMOJIS[i])

        if end_time:
            await self.bot.db.execute(
                "INSERT INTO polls (message_id, guild_id, channel_id, author_id, end_timestamp, question, options) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (message.id, interaction.guild.id, interaction.channel.id, interaction.user.id, end_time.timestamp(), question, json.dumps(option_list))
            )

    @tasks.loop(seconds=60)
    async def check_polls(self):
        """تتحقق بشكل دوري من الاستطلاعات المنتهية وتعلن نتائجها."""
        ended_polls = await self.bot.db.fetchall("SELECT * FROM polls WHERE end_timestamp <= ?", (dt.now(UTC).timestamp(),))
        
        for poll_data in ended_polls:
            try:
                channel = await self.bot.fetch_channel(poll_data['channel_id'])
                message = await channel.fetch_message(poll_data['message_id'])
            except (discord.NotFound, discord.Forbidden):
                await self.bot.db.execute("DELETE FROM polls WHERE message_id = ?", (poll_data['message_id'],))
                continue

            options = json.loads(poll_data['options'])
            results = {}
            total_votes = 0

            # جلب الأصوات من الرسالة
            for reaction in message.reactions:
                emoji_str = str(reaction.emoji)
                if emoji_str in POLL_EMOJIS:
                    count = reaction.count - 1 # إزالة تصويت البوت
                    if count > 0:
                        idx = POLL_EMOJIS.index(emoji_str)
                        if idx < len(options):
                            results[options[idx]] = count
                            total_votes += count

            # إنشاء رسالة النتائج
            result_description = []
            sorted_results = sorted(results.items(), key=lambda item: item[1], reverse=True)
            
            for option, votes in sorted_results:
                percentage = (votes / total_votes * 100) if total_votes > 0 else 0
                bar = '█' * int(percentage / 10) + '░' * (10 - int(percentage / 10))
                result_description.append(f"**{option}**\n`{bar}` ({votes} أصوات, {percentage:.1f}%)")

            # تحديد الفائز
            winner_text = "لم يتم الإدلاء بأي أصوات."
            if sorted_results:
                top_votes = sorted_results[0][1]
                winners = [opt for opt, votes in sorted_results if votes == top_votes]
                if len(winners) > 1:
                    winner_text = f"🏆 **تعادل بين:** {', '.join(winners)}"
                else:
                    winner_text = f"🏆 **الفائز:** {winners[0]}"

            embed = discord.Embed(
                title=f"🏁 انتهى الاستطلاع: {poll_data['question']}",
                description="\n\n".join(result_description),
                color=SUCCESS_COLOR
            )
            embed.add_field(name="النتيجة النهائية", value=winner_text, inline=False)
            
            await message.edit(embed=embed)
            await message.clear_reactions()
            await self.bot.db.execute("DELETE FROM polls WHERE message_id = ?", (poll_data['message_id'],))

    # --- Reminder Commands ---
    @app_commands.command(name="remindme", description="يضبط تذكيرًا للمستقبل.")
    @app_commands.describe(
        duration="متى يتم التذكير (مثال: '10m', '1h30m', '2d').",
        reminder="ما الذي يجب تذكيرك به."
    )
    async def remindme(self, interaction: discord.Interaction, duration: str, reminder: str):
        """يضبط تذكيرًا سيرسله البوت بعد المدة المحددة."""
        delta = parse_duration(duration)
        if not delta or delta.total_seconds() <= 1:
            return await interaction.response.send_message("تنسيق المدة غير صالح أو قصير جدًا. استخدم 'w', 'd', 'h', 'm', 's'.", ephemeral=True)
        
        remind_time = dt.now(UTC) + delta
        
        await self.bot.db.execute(
            "INSERT INTO reminders (user_id, channel_id, remind_content, remind_timestamp) VALUES (?, ?, ?, ?)",
            (interaction.user.id, interaction.channel.id, reminder, remind_time.timestamp())
        )
        
        await interaction.response.send_message(
            f"✅ حسنًا! سأذكرك بـ `{reminder}` في {discord.utils.format_dt(remind_time, 'F')} ({discord.utils.format_dt(remind_time, 'R')}).",
            ephemeral=True
        )

    @tasks.loop(seconds=15)
    async def check_reminders(self):
        """تتحقق بشكل دوري من التذكيرات المستحقة وترسلها."""
        reminders = await self.bot.db.fetchall("SELECT * FROM reminders WHERE remind_timestamp <= ?", (dt.now(UTC).timestamp(),))
        
        for r in reminders:
            try:
                user = await self.bot.fetch_user(r['user_id'])
                channel = await self.bot.fetch_channel(r['channel_id'])
                
                embed = discord.Embed(
                    title="⏰ تذكير!",
                    description=f"مرحبًا {user.mention}، لقد طلبت مني أن أذكرك بالتالي:",
                    color=INFO_COLOR,
                    timestamp=dt.fromtimestamp(r['remind_timestamp'], tz=UTC)
                )
                embed.add_field(name="المحتوى", value=f"> {r['remind_content']}", inline=False)
                
                await channel.send(embed=embed)
            except (discord.NotFound, discord.Forbidden) as e:
                self.bot.logger.warning(f"لا يمكن إرسال التذكير {r['reminder_id']}: {e}")
            finally:
                await self.bot.db.execute("DELETE FROM reminders WHERE reminder_id = ?", (r['reminder_id'],))
    
    # --- Before Loop Waits ---
    @check_reminders.before_loop
    @check_polls.before_loop
    async def before_tasks(self):
        """ينتظر حتى يكون البوت جاهزًا قبل بدء المهام."""
        await self.bot.wait_until_ready()

async def setup(bot: MaxyBot):
    """يضيف كوج Utilities إلى البوت."""
    if not hasattr(bot, 'db'):
        raise RuntimeError("كائن قاعدة البيانات `bot.db` غير موجود. هذا الكوج يتطلب اتصالاً بقاعدة البيانات.")
    await bot.add_cog(Utilities(bot))