# -*- coding: utf-8 -*-
import discord
from discord.ext import commands, tasks
import traceback
import logging
import psutil
import datetime
import asyncio
import platform  # لاستيراد معلومات النظام

# --- إعدادات أساسية ---
# ضع هنا آي دي حسابك لتصلك الأخطاء وتستخدم الأوامر الخاصة
OWNER_ID = 1279500219154956419
# ضع هنا آي دي القناة التي تريد إرسال تقارير الأخطاء إليها (اختياري)
LOG_CHANNEL_ID = 123456789012345678

# --- ثوابت لمراقبة الأداء ---
CPU_THRESHOLD = 85.0  # نسبة المعالج التي يتم التحذير عندها
RAM_THRESHOLD = 85.0  # نسبة الذاكرة التي يتم التحذير عندها

# --- إعداد مسجل الأخطاء (Logger) ---
logger = logging.getLogger('discord') # استخدام الـ logger الخاص بـ discord.py لتوحيد المصدر
logger.setLevel(logging.INFO)
handler = logging.FileHandler(filename='bot_errors.log', encoding='utf-8', mode='w')
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
logger.addHandler(handler)


class Fixes(commands.Cog):
    """
    Cog احترافي لمراقبة أداء البوت ومعالجة الأخطاء بشكل ذكي.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.process = psutil.Process()
        self.start_time = datetime.datetime.utcnow()
#        self.monitor_system.start()

    def cog_unload(self):
        """إيقاف المهمة عند إلغاء تحميل الـ Cog"""
#        self.monitor_system.cancel()


    # -------------------------------
    # 🔹 أمر لعرض حالة البوت
    # -------------------------------
    @commands.command(name="status", help="يعرض حالة البوت والموارد.", aliases=['stats'])
    @commands.is_owner()
    async def status_command(self, ctx: commands.Context):
        """أمر يعرض إحصائيات مفصلة عن البوت والنظام."""
        # حساب مدة تشغيل البوت
        uptime = datetime.datetime.utcnow() - self.start_time
        hours, remainder = divmod(int(uptime.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime_str = f"{hours} ساعة, {minutes} دقيقة, {seconds} ثانية"

        # معلومات النظام والبوت
        python_version = platform.python_version()
        discordpy_version = discord.__version__
        server_count = len(self.bot.guilds)
        member_count = sum(guild.member_count for guild in self.bot.guilds)

        # استهلاك الموارد
        cpu_usage = self.process.cpu_percent() / psutil.cpu_count()
        ram_usage_mb = self.process.memory_info().rss / (1024 * 1024)

        embed = discord.Embed(
            title="📊 حالة البوت",
            description="إحصائيات الأداء والموارد في الوقت الفعلي.",
            color=discord.Color.green(),
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_thumbnail(url=self.bot.user.avatar.url)

        embed.add_field(name="🚀 **مدة التشغيل**", value=uptime_str, inline=False)
        embed.add_field(name="💻 **النظام**", value=f"Python: {python_version}\nDiscord.py: {discordpy_version}", inline=True)
        embed.add_field(name="🌐 **الشبكة**", value=f"السيرفرات: {server_count}\nالأعضاء: {member_count}", inline=True)
        embed.add_field(name="⚙️ **استهلاك الموارد**", value=f"CPU: {cpu_usage:.2f}%\nRAM: {ram_usage_mb:.2f} MB", inline=True)
        embed.set_footer(text=f"تم طلبه بواسطة {ctx.author.name}", icon_url=ctx.author.avatar.url)

        await ctx.send(embed=embed)

    # -------------------------------
    # 🔹 معالج الأخطاء الذكي
    # -------------------------------
    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        """معالج ذكي للأخطاء، يفرق بين أخطاء المستخدم والأخطاء البرمجية."""

        # تجاهل الأخطاء التي لا تحتاج إلى معالجة خاصة
        if isinstance(error, (commands.CommandNotFound, commands.NotOwner)):
            return

        # أخطاء بسبب استخدام خاطئ من المستخدم
        elif isinstance(error, commands.MissingRequiredArgument):
            title = "🤔 نقص في المدخلات!"
            description = f"يبدو أنك نسيت تحديد `{error.param.name}`.\nالرجاء مراجعة كيفية استخدام الأمر والمحاولة مرة أخرى."
            await self.send_user_error(ctx, title, description)

        elif isinstance(error, commands.CheckFailure):
            title = "🔒 وصول مرفوض!"
            description = "ليس لديك الصلاحيات اللازمة لاستخدام هذا الأمر."
            await self.send_user_error(ctx, title, description)
            
        elif isinstance(error, commands.CommandOnCooldown):
            title = "⏳ تمهل قليلاً!"
            description = f"عليك الانتظار لمدة **{error.retry_after:.1f} ثانية** قبل استخدام هذا الأمر مرة أخرى."
            await self.send_user_error(ctx, title, description)

        # أخطاء برمجية غير متوقعة (للمبرمج فقط)
        else:
            # رسالة بسيطة للمستخدم
            await self.send_user_error(ctx, "❌ خطأ غير متوقع!", "حدث خطأ ما أثناء تنفيذ الأمر. تم إبلاغ المطورين.")

            # تسجيل الخطأ بالتفصيل في الملف
            error_traceback = "".join(traceback.format_exception(type(error), error, error.__traceback__))
            logger.error(f"خطأ غير متوقع في أمر '{ctx.command}':\n{error_traceback}")

            # إرسال تقرير خطأ مفصل لقناة السجلات أو للمالك
            embed = discord.Embed(
                title="🚨 تقرير خطأ برمجي",
                description=f"حدث خطأ غير متوقع أثناء تنفيذ أمر.",
                color=discord.Color.dark_red(),
                timestamp=datetime.datetime.utcnow()
            )
            embed.add_field(name="السيرفر", value=f"{ctx.guild.name} (`{ctx.guild.id}`)", inline=True)
            embed.add_field(name="القناة", value=f"#{ctx.channel.name} (`{ctx.channel.id}`)", inline=True)
            embed.add_field(name="المستخدم", value=f"{ctx.author.name} (`{ctx.author.id}`)", inline=True)
            embed.add_field(name="الأمر", value=f"`{ctx.message.content}`", inline=False)
            embed.add_field(name="نوع الخطأ", value=f"`{type(error).__name__}`", inline=False)
            embed.add_field(name="رسالة الخطأ", value=f"```\n{str(error)}\n```", inline=False)

            # إرسال جزء صغير من التتبع لتسهيل التصحيح
            short_traceback = "\n".join(traceback.format_exception(type(error), error, error.__traceback__, limit=5))
            embed.add_field(name="Traceback (مختصر)", value=f"```py\n{short_traceback}\n```", inline=False)

            await self.log_to_channel(embed=embed)


    # -------------------------------
    # 🔹 دوال مساعدة
    # -------------------------------
    async def send_user_error(self, ctx: commands.Context, title: str, description: str):
        """يرسل رسالة خطأ منسقة للمستخدم."""
        embed = discord.Embed(title=title, description=description, color=discord.Color.orange())
        try:
            await ctx.send(embed=embed)
        except discord.Forbidden:
            # في حال لم يتمكن البوت من إرسال Embed (بسبب نقص الصلاحيات)
            await ctx.send(f"**{title}**\n{description}")
        except Exception as e:
            logger.error(f"فشل في إرسال رسالة خطأ للمستخدم: {e}")

    async def log_to_channel(self, message: str = None, level: str = "error", embed: discord.Embed = None):
        """يرسل رسالة أو Embed إلى قناة السجلات أو إلى المالك."""
        target = self.bot.get_channel(LOG_CHANNEL_ID) or await self.bot.fetch_user(OWNER_ID)
        if not target:
            logger.warning("لم يتم العثور على قناة السجلات أو المالك.")
            return

        try:
            if embed:
                await target.send(embed=embed)
            elif message:
                if level == "warning":
                    embed = discord.Embed(title="⚠️ تحذير أداء", description=message, color=discord.Color.gold())
                else:
                    embed = discord.Embed(title="🚨 تقرير", description=message, color=discord.Color.dark_red())
                await target.send(embed=embed)
        except Exception as e:
            logger.error(f"فشل في إرسال السجل إلى قناة ديسكورد: {e}")


async def setup(bot: commands.Bot):
    """تحميل الـ Cog"""
    await bot.add_cog(Fixes(bot))