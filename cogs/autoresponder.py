# -*- coding: utf-8 -*-
# cogs/autoresponder.py

from __future__ import annotations
import typing
import discord
from discord import app_commands
from discord.ext import commands
import re
import random
from datetime import datetime
from discord import Embed, Color

# استيراد كلاس البوت الرئيسي للـ Type Hinting
if typing.TYPE_CHECKING:
    from ..bot import MaxyBot

# استيراد معالج الأخطاء (إذا كان موجوداً في ملف آخر)
from .utils import cog_command_error

# كلاس مخصص لتخزين بيانات الردود لتسهيل التعامل معها
class AutoResponse:
    def __init__(self, record: dict):
        self.response_id: int = record['response_id']
        self.guild_id: int = record['guild_id']
        self.creator_id: int = record['creator_id']
        self.trigger: str = record['trigger']
        self.response: str = record['response']
        self.match_type: str = record['match_type']
        self.response_type: str = record['response_type']
        self.case_sensitive: bool = bool(record['case_sensitive'])
        self.created_at: datetime = record['created_at']

class AutoResponder(commands.Cog, name="AutoResponder"):
    """
    نظام ردود تلقائية متطور مع أنواع متعددة للمطابقة والاستجابة.
    """
    def __init__(self, bot: MaxyBot):
        self.bot = bot
        # ذاكرة تخزين مؤقت (cache) لتجنب استدعاء قاعدة البيانات مع كل رسالة
        self.response_cache: typing.Dict[int, typing.List[AutoResponse]] = {}

    async def cog_load(self):
        # يمكنك ملء الـ cache عند تحميل الـ cog
        await self.load_all_responses()
        botname = "[MaxyBot] "
        print(f"{botname}: Cog AutoResponder loaded and cache populated.")

    async def load_all_responses(self):
        """تحميل جميع الردود من قاعدة البيانات إلى الذاكرة المؤقتة."""
        self.response_cache.clear()
        all_records = await self.bot.db.fetchall("SELECT * FROM auto_responses")
        for record in all_records:
            response = AutoResponse(record)
            if response.guild_id not in self.response_cache:
                self.response_cache[response.guild_id] = []
            self.response_cache[response.guild_id].append(response)

    # معالجة الأخطاء الخاصة بالـ Cog
    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        await cog_command_error(interaction, error)

    # التحقق من صلاحيات المستخدم لتنفيذ الأوامر
    async def cog_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.guild_permissions.manage_messages

    async def _parse_placeholders(self, text: str, message: discord.Message) -> str:
        """معالجة المتغيرات النصية (Placeholders) في الردود."""
        replacements = {
            r'{user}': message.author.mention,
            r'{user.mention}': message.author.mention,
            r'{user.name}': message.author.name,
            r'{user.id}': str(message.author.id),
            r'{user.avatar}': message.author.display_avatar.url,
            r'{guild.name}': message.guild.name,
            r'{guild.id}': str(message.guild.id),
            r'{guild.icon}': message.guild.icon.url if message.guild.icon else "No Icon",
            r'{channel.name}': message.channel.name,
            r'{channel.mention}': message.channel.mention,
            r'{channel.id}': str(message.channel.id),
        }
        for placeholder, value in replacements.items():
            text = text.replace(placeholder, value)

        # متغيرات متقدمة
        if '{random.user}' in text:
            random_user = random.choice(message.guild.members)
            text = text.replace('{random.user}', random_user.mention)
        
        # متغير رقم عشوائي (e.g., {random.number(1,100)})
        for match in re.finditer(r'{random\.number\((\d+),(\d+)\)}', text):
            min_val, max_val = map(int, match.groups())
            random_num = random.randint(min_val, max_val)
            text = text.replace(match.group(0), str(random_num))

        return text

    @commands.Cog.listener("on_message")
    async def handle_responses(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        content = message.content.strip()
        if not content:  # تجاهل الرسائل الفاضية أو اللي فيها مسافات فقط
            return

        conf = self.bot.get_guild_config(message.guild.id)
        if not conf.get('autoresponder', {}).get('enabled', False):
            return

        guild_responses = self.response_cache.get(message.guild.id, [])
        if not guild_responses:
            return

        for resp in guild_responses:
            trigger = resp.trigger
            text_to_check = content if resp.case_sensitive else content.lower()
            trigger_to_check = trigger if resp.case_sensitive else trigger.lower()

            is_match = False
            try:
                if resp.match_type == 'exact' and text_to_check == trigger_to_check:
                    is_match = True
                elif resp.match_type == 'contains' and trigger_to_check in text_to_check:
                    is_match = True
                elif resp.match_type == 'starts_with' and text_to_check.startswith(trigger_to_check):
                    is_match = True
                elif resp.match_type == 'ends_with' and text_to_check.endswith(trigger_to_check):
                    is_match = True
                elif resp.match_type == 'regex':
                    flags = 0 if resp.case_sensitive else re.IGNORECASE
                    if re.search(trigger, content, flags):
                        is_match = True
            except re.error:
                continue

            if is_match:
                final_response = await self._parse_placeholders(resp.response, message)
                try:
                    if resp.response_type == 'message':
                        await message.channel.send(final_response)
                    elif resp.response_type == 'reply':
                        await message.reply(final_response, mention_author=True)
                    elif resp.response_type == 'react':
                        try:
                            await message.add_reaction(final_response)
                        except discord.HTTPException:
                            pass
                except (discord.HTTPException, discord.Forbidden):
                    pass
                return

    # ======================================================
    #                 مجموعة أوامر الردود التلقائية
    # ======================================================
    autoresponse = app_commands.Group(name="autoresponse", description="إدارة الردود التلقائية في السيرفر")

    @autoresponse.command(name="add", description="➕ إضافة رد تلقائي جديد")
    @app_commands.describe(
        trigger="الكلمة أو الجملة التي ستفعل الرد",
        response="الرد الذي سيرسله البوت (نص أو إيموجي للـ react)",
        response_type="اختر نوع الرد: رسالة عادية، رد على الرسالة، أو تفاعل.",
        match_type="اختر كيف سيتم مطابقة الرسالة مع الكلمة المفتاحية.",
        case_sensitive="هل يجب أن تكون حالة الأحرف متطابقة؟ (افتراضي: لا)"
    )
    @app_commands.choices(
        response_type=[
            app_commands.Choice(name="✉️ Message (رسالة)", value="message"),
            app_commands.Choice(name="↩️ Reply (رد)", value="reply"),
            app_commands.Choice(name="👍 React (تفاعل)", value="react"),
        ],
        match_type=[
            app_commands.Choice(name="كامل الرسالة (Exact)", value="exact"),
            app_commands.Choice(name="تحتوي على (Contains)", value="contains"),
            app_commands.Choice(name="تبدأ بـ (Starts With)", value="starts_with"),
            app_commands.Choice(name="تنتهي بـ (Ends With)", value="ends_with"),
            app_commands.Choice(name="تعبير نمطي (Regex)", value="regex"),
        ]
    )
    async def add_response(self, interaction: discord.Interaction, 
                           trigger: str, 
                           response: str, 
                           response_type: app_commands.Choice[str], 
                           match_type: app_commands.Choice[str],
                           case_sensitive: bool = False):
        
        trigger_lower = trigger.lower()
        exists = await self.bot.db.fetchone("SELECT 1 FROM auto_responses WHERE guild_id = ? AND lower(trigger) = ?", (interaction.guild.id, trigger_lower))
        if exists:
            return await interaction.response.send_message(f"❌ يوجد رد تلقائي بالفعل للمعرف `{trigger}`.", ephemeral=True)

        await self.bot.db.execute(
            """
            INSERT INTO auto_responses 
            (guild_id, creator_id, trigger, response, match_type, response_type, case_sensitive, created_at) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (interaction.guild.id, interaction.user.id, trigger, response, match_type.value, response_type.value, int(case_sensitive), datetime.utcnow())
        )
        
        # تحديث الذاكرة المؤقتة
        await self.load_all_responses()

        embed = discord.Embed(
            title="✅ تم إضافة رد تلقائي جديد",
            color=discord.Color.green()
        )
        embed.add_field(name="المُحفّز (Trigger)", value=f"`{trigger}`", inline=False)
        embed.add_field(name="الاستجابة (Response)", value=f"```\n{response}\n```", inline=False)
        embed.add_field(name="نوع الرد", value=response_type.name, inline=True)
        embed.add_field(name="نوع المطابقة", value=match_type.name, inline=True)
        embed.add_field(name="حساسية الأحرف", value="نعم" if case_sensitive else "لا", inline=True)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @autoresponse.command(name="remove", description="🗑️ إزالة رد تلقائي")
    @app_commands.describe(trigger="المعرف (trigger) للرد الذي تريد حذفه")
    async def remove_response(self, interaction: discord.Interaction, trigger: str):
        # ميزة الإكمال التلقائي
        row = await self.bot.db.fetchone("SELECT response_id FROM auto_responses WHERE guild_id = ? AND lower(trigger) = ?", (interaction.guild.id, trigger.lower()))
        if not row:
            return await interaction.response.send_message(f"❌ لم يتم العثور على رد تلقائي للمعرف `{trigger}`.", ephemeral=True)

        await self.bot.db.execute("DELETE FROM auto_responses WHERE response_id = ?", (row['response_id'],))
        
        # تحديث الذاكرة المؤقتة
        await self.load_all_responses()
        
        await interaction.response.send_message(f"🗑️ تم حذف الرد التلقائي الخاص بـ `{trigger}` بنجاح.", ephemeral=True)
    
    # دالة الإكمال التلقائي لأسماء الردود
    @remove_response.autocomplete('trigger')
    async def remove_response_autocomplete(self, interaction: discord.Interaction, current: str) -> typing.List[app_commands.Choice[str]]:
        guild_responses = self.response_cache.get(interaction.guild.id, [])
        triggers = [resp.trigger for resp in guild_responses]
        
        return [
            app_commands.Choice(name=trigger, value=trigger)
            for trigger in triggers if current.lower() in trigger.lower()
        ][:25] # الحد الأقصى للاختيارات هو 25

    @autoresponse.command(name="list", description="📋 عرض كل الردود التلقائية في السيرفر")
    async def list_responses(self, interaction: discord.Interaction):
        guild_responses = self.response_cache.get(interaction.guild.id, [])
        if not guild_responses:
            return await interaction.response.send_message("ℹ️ لا توجد ردود تلقائية في هذا السيرفر.", ephemeral=True)

        embed = discord.Embed(
            title=f"الردود التلقائية لسيرفر {interaction.guild.name}",
            color=discord.Color.blue()
        )
        
        description = []
        for resp in guild_responses:
            description.append(f"**- `{resp.trigger}`** (النوع: {resp.response_type})")

        embed.description = "\n".join(description)
        await interaction.response.send_message(embed=embed, ephemeral=True)

# دالة الـ setup لتحميل الـ Cog
async def setup(bot: MaxyBot):
    await bot.add_cog(AutoResponder(bot))