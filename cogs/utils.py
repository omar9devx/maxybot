# -*- coding: utf-8 -*-
import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import datetime
import logging
import functools
import time
from typing import Callable, Any, Type, Coroutine, Optional, Union

# -----------------------
# إعداد الـ Logging
# -----------------------
logger = logging.getLogger("bot")
logger.setLevel(logging.INFO)

# Console
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter("%(asctime)s:%(levelname)s:%(name)s: %(message)s"))
logger.addHandler(console_handler)

# File log
file_handler = logging.FileHandler("bot_errors.log", encoding="utf-8")
file_handler.setFormatter(logging.Formatter("%(asctime)s:%(levelname)s:%(name)s: %(message)s"))
logger.addHandler(file_handler)

# -----------------------
# معالج الأخطاء العام للـ Cogs
# -----------------------
async def cog_command_error(ctx_or_interaction, error):
    """
    Universal error handler (prefix + slash).
    """

    # لو الكوماند Prefix (ctx)
    if isinstance(ctx_or_interaction, commands.Context):
        ctx = ctx_or_interaction

        if isinstance(error, commands.CommandNotFound):
            return  # تجاهل أو ابعت رسالة
        elif isinstance(error, commands.MissingRequiredArgument):
            msg = f"⚠️ نسيت تحدد `{error.param.name}`!"
        elif isinstance(error, commands.MissingPermissions):
            msg = "🚫 ماعندكش صلاحيات تستخدم الأمر ده."
        elif isinstance(error, commands.BotMissingPermissions):
            msg = "⚠️ البوت ماعندوش صلاحيات كفاية."
        elif isinstance(error, commands.BadArgument):
            msg = "⚠️ المدخلات مش صحيحة."
        elif isinstance(error, commands.CommandOnCooldown):
            msg = f"⏳ استنى `{error.retry_after:.1f}` ثانية قبل ما تستخدم الأمر تاني."
        else:
            original = getattr(error, "original", error)
            msg = f"❌ حصل خطأ غير متوقع: `{original}`"
            logger.error(f"Error in command {ctx.command}: {original}", exc_info=True)

        try:
            await ctx.send(msg, delete_after=10)
        except Exception as e:
            logger.warning(f"Couldn't send error message in {ctx.channel}: {e}")

        logger.warning(
            f"Command Error | Guild: {getattr(ctx.guild, 'name', 'DM')} | "
            f"User: {ctx.author} ({ctx.author.id}) | "
            f"Command: {ctx.command} | Error: {type(error).__name__}: {error}"
        )

    # لو الكوماند Slash (interaction)
    elif isinstance(ctx_or_interaction, discord.Interaction):
        interaction = ctx_or_interaction

        if isinstance(error, app_commands.MissingPermissions):
            msg = "🚫 ماعندكش صلاحيات تستخدم الأمر ده."
        elif isinstance(error, app_commands.CommandOnCooldown):
            msg = f"⏳ استنى `{error.retry_after:.1f}` ثانية قبل ما تستخدم الأمر تاني."
        else:
            original = getattr(error, "original", error)
            msg = f"❌ حصل خطأ غير متوقع: `{original}`"
            logger.error(f"Error in slash command {interaction.command}: {original}", exc_info=True)

        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(msg, ephemeral=True)
            else:
                await interaction.followup.send(msg, ephemeral=True)
        except Exception as e:
            logger.warning(f"Couldn't send error message in slash command: {e}")

        logger.warning(
            f"Slash Command Error | Guild: {getattr(interaction.guild, 'name', 'DM')} | "
            f"User: {interaction.user} ({interaction.user.id}) | "
            f"Command: {interaction.command} | Error: {type(error).__name__}: {error}"
        )

# -----------------------
# Utils Cog - مكتبة الأدوات
# -----------------------
class Utils(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # Decorator لإعادة المحاولة (Retry)
    def retry(self, retries: int = 3, delay: float = 1.5,
              allowed_exceptions: tuple[Type[Exception], ...] = (Exception,)):
        def decorator(func: Callable[..., Coroutine[Any, Any, Any]]) -> Callable[..., Coroutine[Any, Any, Any]]:
            @functools.wraps(func)
            async def wrapper(*args, **kwargs):
                for attempt in range(1, retries + 1):
                    try:
                        return await func(*args, **kwargs)
                    except allowed_exceptions as e:
                        if attempt == retries:
                            logger.error(f"Function '{func.__name__}' failed after {retries} retries. Error: {e}")
                            raise
                        logger.warning(f"Retry {attempt}/{retries} for '{func.__name__}'. Error: {e}")
                        await asyncio.sleep(delay)
            return wrapper
        return decorator

    # Decorator لقياس وقت التنفيذ
    def timeit(self, func: Callable[..., Coroutine[Any, Any, Any]]) -> Callable[..., Coroutine[Any, Any, Any]]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            start = time.perf_counter()
            result = await func(*args, **kwargs)
            end = time.perf_counter()
            logger.info(f"Function '{func.__name__}' took {end - start:.4f}s")
            return result
        return wrapper

    # دوال آمنة للتعامل مع Discord API
    async def safe_send(self, destination, content=None, embed=None, delete_after=None):
        try:
            return await destination.send(content=content, embed=embed, delete_after=delete_after)
        except discord.Forbidden:
            logger.warning(f"No permission to send message to {destination}")
        except discord.HTTPException as e:
            logger.error(f"HTTP error while sending: {e}")
        return None

    async def safe_edit(self, message, content=None, embed=None):
        try:
            return await message.edit(content=content, embed=embed)
        except Exception as e:
            logger.warning(f"Failed to edit message {message.id}: {e}")
        return None

    async def safe_delete(self, message):
        try:
            await message.delete()
            return True
        except Exception as e:
            logger.warning(f"Failed to delete message {message.id}: {e}")
        return False

    async def bulk_delete_safe(self, channel: discord.TextChannel, limit: int):
        try:
            deleted = await channel.purge(limit=limit)
            return len(deleted)
        except Exception as e:
            logger.warning(f"Bulk delete failed in {channel.id}: {e}")
        return 0

    # Utilities
    def format_user(self, member: Union[discord.Member, discord.User]) -> str:
        return f"{member.name}#{member.discriminator} ({member.id})"

    def format_guild(self, guild: discord.Guild) -> str:
        return f"{guild.name} | Members: {guild.member_count} | ID: {guild.id}"

    def random_color(self) -> discord.Color:
        return discord.Color.random()

    def format_timestamp(self, dt_object: Optional[datetime.datetime] = None, style: str = "F") -> str:
        if dt_object is None:
            dt_object = datetime.datetime.now(datetime.timezone.utc)
        return f"<t:{int(dt_object.timestamp())}:{style}>"

# -----------------------
# Setup
# -----------------------
async def setup(bot: commands.Bot):
    await bot.add_cog(Utils(bot))
    logger.info("Utils cog loaded successfully ✅")
