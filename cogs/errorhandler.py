# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import traceback
from datetime import datetime
from typing import TYPE_CHECKING
import discord
from discord import app_commands
from discord.ext import commands

if TYPE_CHECKING:
    from ..bot import MaxyBot


class ErrorHandlerCog(commands.Cog):
    """Cog مركزي لتسجيل جميع أخطاء Slash Commands بالتفصيل مع نصائح."""

    def __init__(self, bot: MaxyBot):
        self.bot = bot
        self.logger = bot.logger

        # إنشاء مجلد logs لو مش موجود
        os.makedirs("logs", exist_ok=True)
        self.log_file_txt = "logs/errors.txt"
        self.log_file_log = "logs/errors.log"

    async def log_to_files(self, message: str):
        """تسجيل الأخطاء في ملفات نصية"""
        with open(self.log_file_txt, "a", encoding="utf-8") as f_txt:
            f_txt.write(message + "\n\n")
        with open(self.log_file_log, "a", encoding="utf-8") as f_log:
            f_log.write(message + "\n\n")

    def generate_advice(self, error: app_commands.AppCommandError) -> str:
        """إرجاع نصائح حسب نوع الخطأ"""
        if isinstance(error, app_commands.CommandOnCooldown):
            return "✅ طبيعي. المستخدم يجب أن ينتظر فترة التهدئة قبل إعادة المحاولة."
        elif isinstance(error, app_commands.MissingPermissions):
            return "⚠️ أبلغ المستخدم بالصلاحيات المطلوبة أو عدّل صلاحيات الكوماند."
        elif isinstance(error, app_commands.BotMissingPermissions):
            return f"⚠️ تأكد أن البوت لديه الصلاحيات: {', '.join(error.missing_permissions)}"
        else:
            return "❌ تحقق من الكوماند نفسه وحل المشكلة في الكود."

    @commands.Cog.listener()
    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """التعامل مع كل أخطاء Slash Commands"""

        # معلومات أساسية
        user = interaction.user
        guild = interaction.guild
        command_name = interaction.command.name if interaction.command else "unknown_command"
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

        # full traceback
        exc_info = (type(error), error, error.__traceback__)
        full_traceback = "".join(traceback.format_exception(*exc_info))

        # نصيحة حسب الخطأ
        advice = self.generate_advice(error)

        # بناء رسالة اللوج التفصيلية
        log_message = (
            f"========== ERROR REPORT ==========\n"
            f"Time: {now}\n"
            f"Command: /{command_name}\n"
            f"User: {user} | ID: {user.id}\n"
            f"Guild: {guild} | ID: {guild.id if guild else 'DM'}\n"
            f"Interaction Data: {interaction.data}\n"
            f"Error Type: {type(error).__name__}\n"
            f"Traceback:\n{full_traceback}\n"
            f"Advice: {advice}\n"
            f"================================"
        )

        # تسجيل في ملفات و logger
        await self.log_to_files(log_message)
        self.logger.error(log_message)

        # إرسال رسالة للمستخدم
        try:
            if isinstance(error, app_commands.CommandOnCooldown):
                await interaction.response.send_message(
                    f"⏳ هذا الأمر عليه فترة تهدئة. من فضلك حاول مرة أخرى خلال {error.retry_after:.2f} ثانية.",
                    ephemeral=True
                )
            elif isinstance(error, app_commands.MissingPermissions):
                await interaction.response.send_message(
                    "❌ ليس لديك الصلاحيات المطلوبة لاستخدام هذا الأمر.",
                    ephemeral=True
                )
            elif isinstance(error, app_commands.BotMissingPermissions):
                await interaction.response.send_message(
                    "🚫 ليس لدي الصلاحيات اللازمة لتنفيذ هذا الإجراء.",
                    ephemeral=True
                )
            else:
                if interaction.response.is_done():
                    await interaction.followup.send(
                        "⚙️ حدث خطأ غير متوقع. تم إبلاغ المطورين.", ephemeral=True
                    )
                else:
                    await interaction.response.send_message(
                        "⚙️ حدث خطأ غير متوقع. تم إبلاغ المطورين.", ephemeral=True
                    )
        except discord.errors.InteractionResponded:
            pass


async def setup(bot: MaxyBot):
    """تحميل الكوج"""
    await bot.add_cog(ErrorHandlerCog(bot))
