# FILE: cogs/high_admins.py

from __future__ import annotations
from typing import TYPE_CHECKING, Literal, Optional
import discord
from discord import app_commands
from discord.ext import commands
import io
import textwrap
import traceback
from contextlib import redirect_stdout
import json
import os
import psutil
import datetime
import sys
import asyncio

# This allows for type hinting the bot class without circular imports
if TYPE_CHECKING:
    from ..bot import MaxyBot

# =======================================================================================
# SECTION: Helper Functions & Views
# =======================================================================================

async def is_bot_owner_check(interaction: discord.Interaction) -> bool:
    """
    A robust check to see if the user is a bot owner.
    This uses the bot's internal is_owner() method.
    """
    if await interaction.client.is_owner(interaction.user):
        return True
    
    embed = discord.Embed(
        description="❌ | أنت لست مخولاً لاستخدام هذا الأمر. هذا الأمر مخصص لمالك البوت فقط.",
        color=discord.Color.red()
    )
    # Use the appropriate response method based on interaction state
    if interaction.response.is_done():
        await interaction.followup.send(embed=embed, ephemeral=True)
    else:
        await interaction.response.send_message(embed=embed, ephemeral=True)
    return False

def is_bot_owner():
    """Decorator for app_commands to check if the user is a bot owner."""
    return app_commands.check(is_bot_owner_check)


class ConfirmationView(discord.ui.View):
    """A view that provides Confirm/Cancel buttons for dangerous actions."""
    def __init__(self, author_id: int, action: str = "Confirm"):
        super().__init__(timeout=60.0)
        self.value: Optional[bool] = None
        self.author_id = author_id
        # Set the confirm button's label dynamically
        self.children[0].label = action

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Ensures that only the original command invoker can use the buttons."""
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This confirmation is not for you.", ephemeral=True)
            return False
        return True
        
    async def disable_all_items(self):
        """Disables all buttons in the view."""
        for item in self.children:
            item.disabled = True

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = True
        self.stop()
        await self.disable_all_items()
        await interaction.response.edit_message(view=self) # Update message to show disabled buttons

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = False
        self.stop()
        await self.disable_all_items()
        await interaction.response.edit_message(view=self) # Update message to show disabled buttons

# =======================================================================================
# SECTION: Main Cog Class
# =======================================================================================

class HighAdmins(commands.Cog, name="Bot Owner (cant use this commands!)"):
    """
    Commands for high-level bot administration. Restricted to bot owners only.
    """
    def __init__(self, bot: MaxyBot):
        self.bot = bot
        self._last_result = None

    # --- Command Groups Definition ---
    cogs_group = app_commands.Group(name="own-cogs", description="إدارة وحدات البوت (Cogs)")
    guilds_group = app_commands.Group(name="own-guilds", description="إدارة السيرفرات التي يتواجد بها البوت")
    profile_group = app_commands.Group(name="own-profile", description="[خطير] التحكم في ملف تعريف البوت الشخصي")
    files_group = app_commands.Group(name="own-files", description="[خطير جداً] التحكم في ملفات البوت على السيرفر")
    blacklist_group = app_commands.Group(name="own-blacklist", description="[خطير] إدارة القائمة السوداء للمستخدمين والسيرفرات")

    # =======================================================================================
    # SECTION: Core Bot Control Commands
    # =======================================================================================

    async def _graceful_unload_cogs(self, interaction: discord.Interaction) -> bool:
        """Helper function to unload all cogs gracefully for shutdown/restart."""
        loaded_cogs = list(self.bot.extensions.keys())
        total_cogs = len(loaded_cogs)
        
        for i, cog_name in enumerate(loaded_cogs):
            try:
                await self.bot.unload_extension(cog_name)
                self.bot.logger.info(f"Successfully unloaded cog: {cog_name}")
                cog_display_name = cog_name.split('.')[-1]
                await interaction.edit_original_response(content=f"🔄 Unloading module {i+1}/{total_cogs} (`{cog_display_name}`)...")
                await asyncio.sleep(0.2)
            except Exception as e:
                self.bot.logger.error(f"Failed to unload cog {cog_name}: {e}")
                await interaction.edit_original_response(content=f"⚠️ Error unloading `{cog_name}`. Proceeding anyway.")
                await asyncio.sleep(1)
        return True

    @is_bot_owner()
    @app_commands.command(name="own-shutdown", description="[OWNER] إيقاف تشغيل البوت بشكل آمن وتدريجي.")
    async def shutdown(self, interaction: discord.Interaction):
        view = ConfirmationView(interaction.user.id, action="Confirm Shutdown")
        await interaction.response.send_message("Are you sure you want to shut down the bot?", view=view, ephemeral=True)
        
        await view.wait()
        if view.value is True:
            await interaction.edit_original_response(content="🔄 Shutting down... Preparing to unload modules.", view=None)
            self.bot.logger.info(f"Shutdown command issued by {interaction.user}. Beginning gradual shutdown.")
            await self._graceful_unload_cogs(interaction)
            await interaction.edit_original_response(content="✅ All modules unloaded. Closing connection...")
            self.bot.logger.info("All cogs unloaded. Closing bot connection now.")
            await asyncio.sleep(1)
            await self.bot.close()
        elif view.value is False:
            await interaction.edit_original_response(content="✅ Shutdown cancelled.", view=None)
        else: # Timeout
            await interaction.edit_original_response(content="⚠️ Shutdown confirmation timed out. Action cancelled.", view=None)

    @is_bot_owner()
    @app_commands.command(name="own-restart", description="[OWNER] إعادة تشغيل البوت (يتطلب مدير عمليات).")
    async def restart(self, interaction: discord.Interaction):
        view = ConfirmationView(interaction.user.id, action="Confirm Restart")
        embed = discord.Embed(title="⚠️ Restart Confirmation", description="Are you sure you want to restart the bot?\n\n**Note:** This requires a process manager (like PM2, systemd, or Docker) to automatically restart the script after it exits.", color=discord.Color.orange())
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        
        await view.wait()
        if view.value is True:
            await interaction.edit_original_response(content="🔄 Restarting... Unloading modules before exit.", view=None, embed=None)
            self.bot.logger.info(f"Restart command issued by {interaction.user}.")
            # Create a flag file to indicate a restart
            with open("restart.flag", "w") as f: f.write(f"{interaction.channel.id}")
            await self._graceful_unload_cogs(interaction)
            await interaction.edit_original_response(content="✅ See you in a moment!")
            await self.bot.close()
        elif view.value is False:
            await interaction.edit_original_response(content="✅ Restart cancelled.", view=None, embed=None)
        else: # Timeout
            await interaction.edit_original_response(content="⚠️ Restart confirmation timed out.", view=None, embed=None)

    @is_bot_owner()
    @app_commands.command(name="own-maintenance", description="[OWNER] تفعيل أو تعطيل وضع الصيانة.")
    @app_commands.describe(status="الحالة الجديدة لوضع الصيانة")
    async def maintenance(self, interaction: discord.Interaction, status: Literal['on', 'off']):
        self.bot.maintenance_mode = (status == 'on')
        self.bot.logger.warning(f"Maintenance mode set to {status.upper()} by {interaction.user}.")
        
        if self.bot.maintenance_mode:
            title = "🔧 Maintenance Mode Enabled"
            desc = "The bot is now **ON**. While active, most non-owner commands will be blocked."
            color = discord.Color.orange()
        else:
            title = "✅ Maintenance Mode Disabled"
            desc = "The bot is now **OFF**. All commands are operational."
            color = discord.Color.green()
            
        embed = discord.Embed(title=title, description=desc, color=color)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # =======================================================================================
    # SECTION: Bot Information and Dev Commands
    # =======================================================================================

    @is_bot_owner()
    @app_commands.command(name="own-botstatus", description="يعرض معلومات تفصيلية عن حالة البوت وأداءه.")
    async def botstatus(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        process = psutil.Process(os.getpid())
        uptime_delta = datetime.datetime.now(datetime.timezone.utc) - self.bot.start_time
        mem_usage = process.memory_info().rss / 1024**2
        cpu_usage = process.cpu_percent() / psutil.cpu_count()
        
        embed = discord.Embed(title="📊 Bot Status", color=discord.Color.blue(), timestamp=datetime.datetime.now(datetime.timezone.utc))
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        
        # Core Info
        embed.add_field(name="🕒 Uptime", value=str(uptime_delta).split('.')[0], inline=True)
        embed.add_field(name="⏳ Latency", value=f"{self.bot.latency * 1000:.2f} ms", inline=True)
        embed.add_field(name="🆔 Process ID", value=str(process.pid), inline=True)

        # Usage Info
        embed.add_field(name="🖥️ CPU Usage", value=f"{cpu_usage:.2f}%", inline=True)
        embed.add_field(name="💾 Memory Usage", value=f"{mem_usage:.2f} MB", inline=True)
        embed.add_field(name="🧵 Threads", value=str(process.num_threads()), inline=True)
        
        # Discord Info
        embed.add_field(name="🌐 Servers", value=str(len(self.bot.guilds)), inline=True)
        embed.add_field(name="👥 Users", value=f"{len(self.bot.users):,}", inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=True) # Spacer

        # Software Info
        embed.add_field(name="🐍 Python", value=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}", inline=True)
        embed.add_field(name="📦 discord.py", value=discord.__version__, inline=True)
        
        await interaction.followup.send(embed=embed)

    @is_bot_owner()
    @app_commands.command(name="own-eval", description="[خطير جداً] تنفيذ كود بايثون.")
    @app_commands.describe(code="الكود المراد تنفيذه")
    async def _eval(self, interaction: discord.Interaction, *, code: str):
        await interaction.response.defer(ephemeral=True)
        code = code.strip('` ')
        if code.startswith('py'): code = code[2:]
        
        env = {
            'bot': self.bot, 
            'interaction': interaction, 
            '_': self._last_result, 
            'discord': discord, 
            'asyncio': asyncio,
            'os': os,
            'sys': sys,
            'psutil': psutil
        }
        env.update(globals())
        
        stdout = io.StringIO()
        to_compile = f'async def func():\n{textwrap.indent(code, "  ")}'
        
        try:
            exec(to_compile, env)
        except Exception as e:
            return await interaction.followup.send(f'```py\n{e.__class__.__name__}: {e}\n```')
        
        func = env['func']
        try:
            with redirect_stdout(stdout):
                ret = await func()
        except Exception:
            value = stdout.getvalue()
            await interaction.followup.send(f'```py\n{value}{traceback.format_exc()}\n```')
        else:
            value = stdout.getvalue()
            if ret is None:
                output = f"```py\n{value}\n```" if value else "✅ | تم تنفيذ الكود بنجاح."
            else:
                self._last_result = ret
                output = f'```py\n{value}{ret}\n```'
            
            if len(output) > 2000:
                await interaction.followup.send("The result was too long, so it was sent as a file.", file=discord.File(io.BytesIO(output.encode('utf-8')), "eval_result.txt"))
            else:
                await interaction.followup.send(output)

    @is_bot_owner()
    @app_commands.command(name="own-sql", description="[خطير جداً] تنفيذ استعلام SQL مباشر على قاعدة البيانات.")
    @app_commands.describe(query="استعلام SQL المراد تنفيذه")
    async def sql_query(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer(ephemeral=True, thinking=True)
        if not hasattr(self.bot, 'db'):
            return await interaction.followup.send("❌ | Database connection not found.")
        
        try:
            if query.strip().lower().startswith("select"):
                results = await self.bot.db.fetchall(query)
                if not results:
                    return await interaction.followup.send("🗃️ | Query returned no results.")
                
                json_str = json.dumps([dict(row) for row in results], indent=2, ensure_ascii=False)
                output = f"```json\n{json_str}\n```"
                
                if len(output) > 2000:
                    await interaction.followup.send("Result too long, sent as file.", file=discord.File(io.BytesIO(output.encode('utf-8')), "sql_result.json"))
                else:
                    await interaction.followup.send(output)
            else:
                cursor = await self.bot.db.execute(query)
                await self.bot.db.commit()
                await interaction.followup.send(f"✅ | Query executed. **{cursor.rowcount}** rows affected.")
        except Exception as e:
            await interaction.followup.send(f"🔥 | An SQL error occurred:\n```\n{e}\n```")

    # =======================================================================================
    # SECTION: Bot Interaction Commands
    # =======================================================================================

    @is_bot_owner()
    @app_commands.command(name="own-sudo", description="[خطير] إرسال رسالة كـ البوت في أي قناة.")
    @app_commands.describe(channel_id="ID القناة", message="الرسالة")
    async def sudo(self, interaction: discord.Interaction, channel_id: str, message: str):
        try:
            channel = self.bot.get_channel(int(channel_id))
            if not isinstance(channel, (discord.TextChannel, discord.Thread)):
                return await interaction.response.send_message("❌ | لم أجد قناة نصية بهذا الـ ID.", ephemeral=True)
            
            await channel.send(message)
            await interaction.response.send_message(f"✅ | تم إرسال رسالتك إلى {channel.mention}.", ephemeral=True)
        except (ValueError, TypeError):
            await interaction.response.send_message("❌ | ID القناة غير صالح.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message(f"🔥 | ليس لدي صلاحيات لإرسال رسائل في {channel.mention}.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"🔥 | حدث خطأ غير متوقع: {e}", ephemeral=True)

    @is_bot_owner()
    @app_commands.command(name="own-dm", description="[خطير] إرسال رسالة خاصة لمستخدم معين.")
    @app_commands.describe(user_id="ID المستخدم", message="الرسالة")
    async def direct_message(self, interaction: discord.Interaction, user_id: str, message: str):
        try:
            user = await self.bot.fetch_user(int(user_id))
            await user.send(message)
            await interaction.response.send_message(f"✅ | تم إرسال رسالتك الخاصة إلى **{user}**.", ephemeral=True)
        except (ValueError, TypeError):
            await interaction.response.send_message("❌ | ID المستخدم غير صالح.", ephemeral=True)
        except discord.NotFound:
            await interaction.response.send_message("❌ | لم أجد مستخدم بهذا الـ ID.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message(f"🔥 | لا يمكنني إرسال رسالة خاصة لهذا المستخدم (قد يكون أغلق الرسائل الخاصة).", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"🔥 | حدث خطأ غير متوقع: {e}", ephemeral=True)

    @is_bot_owner()
    @app_commands.command(name="own-set-activity", description="[OWNER] تغيير حالة ونشاط البوت.")
    @app_commands.describe(activity_type="نوع النشاط", text="النص الذي سيظهر", stream_url="رابط البث (لـ Streaming فقط)")
    @app_commands.choices(activity_type=[
        app_commands.Choice(name="Playing", value="playing"),
        app_commands.Choice(name="Watching", value="watching"),
        app_commands.Choice(name="Listening to", value="listening"),
        app_commands.Choice(name="Streaming", value="streaming"),
        app_commands.Choice(name="Clear Activity", value="clear"),
    ])
    async def set_activity(self, interaction: discord.Interaction, activity_type: str, text: str = None, stream_url: str = None):
        activity = None
        if activity_type == 'clear':
            pass
        elif not text:
            return await interaction.response.send_message("❌ | يرجى تحديد نص للحالة.", ephemeral=True)
        elif activity_type == "playing":
            activity = discord.Game(name=text)
        elif activity_type == "watching":
            activity = discord.Activity(type=discord.ActivityType.watching, name=text)
        elif activity_type == "listening":
            activity = discord.Activity(type=discord.ActivityType.listening, name=text)
        elif activity_type == "streaming":
            if not stream_url:
                return await interaction.response.send_message("❌ | يرجى تحديد رابط للبث.", ephemeral=True)
            activity = discord.Streaming(name=text, url=stream_url)
        
        try:
            await self.bot.change_presence(activity=activity)
            msg = f"✅ | تم إزالة حالة البوت." if not activity else f"✅ | تم تغيير حالة البوت إلى: `{activity_type.capitalize()} {text}`"
            await interaction.response.send_message(msg, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"🔥 | حدث خطأ: {e}", ephemeral=True)

    # =======================================================================================
    # SECTION: Cogs Management Commands
    # =======================================================================================

    @is_bot_owner()
    @cogs_group.command(name="load", description="تحميل وحدة (Cog) جديدة.")
    @app_commands.describe(extension="اسم الوحدة المراد تحميلها")
    async def load_cog(self, interaction: discord.Interaction, extension: str):
        try:
            await self.bot.load_extension(f"cogs.{extension}")
            await interaction.response.send_message(f"✅ | تم تحميل `{extension}`.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"🔥 | خطأ في تحميل `{extension}`:\n```py\n{e}\n```", ephemeral=True)

    @is_bot_owner()
    @cogs_group.command(name="unload", description="إلغاء تحميل وحدة (Cog).")
    @app_commands.describe(extension="اسم الوحدة المراد إلغاء تحميلها")
    async def unload_cog(self, interaction: discord.Interaction, extension: str):
        try:
            await self.bot.unload_extension(f"cogs.{extension}")
            await interaction.response.send_message(f"✅ | تم إلغاء تحميل `{extension}`.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"🔥 | خطأ في إلغاء تحميل `{extension}`:\n```py\n{e}\n```", ephemeral=True)
    
    @is_bot_owner()
    @cogs_group.command(name="reload", description="إعادة تحميل وحدة (Cog).")
    @app_commands.describe(extension="اسم الوحدة المراد إعادة تحميلها")
    async def reload_slash_cog(self, interaction: discord.Interaction, extension: str):
        try:
            await self.bot.reload_extension(f"cogs.{extension}")
            await interaction.response.send_message(f"🔄 | تم إعادة تحميل `{extension}`.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"🔥 | خطأ في إعادة تحميل `{extension}`:\n```py\n{e}\n```", ephemeral=True)
            
    @is_bot_owner()
    @cogs_group.command(name="list", description="عرض كل الوحدات المتاحة وحالتها.")
    async def list_cogs(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        cogs_dir = "cogs"
        if not os.path.isdir(cogs_dir):
            return await interaction.followup.send("❌ | لم أتمكن من العثور على مجلد `cogs`.")
        
        loaded_cogs = {cog.replace("cogs.", "") for cog in self.bot.extensions.keys()}
        all_cogs = {f.replace('.py', '') for f in os.listdir(cogs_dir) if f.endswith('.py') and not f.startswith('_')}
        
        embed = discord.Embed(title="📚 حالة الوحدات (Cogs)", color=discord.Color.dark_purple())
        
        loaded_list = "\n".join(f"✅ `{cog}`" for cog in sorted(all_cogs) if cog in loaded_cogs) or "لا توجد"
        unloaded_list = "\n".join(f"❌ `{cog}`" for cog in sorted(all_cogs) if cog not in loaded_cogs) or "لا توجد"

        embed.add_field(name="-- Loaded --", value=loaded_list, inline=False)
        embed.add_field(name="-- Unloaded --", value=unloaded_list, inline=False)
        
        await interaction.followup.send(embed=embed)

    # Prefix command for reloading (useful if slash commands break)
    @commands.command(name="cog-reload")
    @commands.is_owner()
    async def reload_prefix_cog(self, ctx: commands.Context, cog_name: str):
        """
        Reloads a cog. Does NOT sync commands.
        Usage: m!cog-reload high_admins
        """
        msg = await ctx.send(f"🔄 Reloading cog `{cog_name}`...")
        try:
            await self.bot.reload_extension(f"cogs.{cog_name}")
            await msg.edit(content=f"✅ Cog `{cog_name}` reloaded successfully!\n**Note:** Command syncing is now manual.")
        except commands.ExtensionNotLoaded:
            await msg.edit(content=f"❌ Cog `{cog_name}` is not loaded.")
        except commands.ExtensionNotFound:
            await msg.edit(content=f"❌ Cog `{cog_name}` not found.")
        except Exception as e:
            await msg.edit(content=f"❌ Failed to reload cog `{cog_name}`: `{e}`")

    # =======================================================================================
    # SECTION: Guilds Management Commands
    # =======================================================================================

    @is_bot_owner()
    @guilds_group.command(name="list", description="عرض قائمة بكل السيرفرات التي يتواجد بها البوت.")
    async def guild_list(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        guilds = sorted(self.bot.guilds, key=lambda g: g.member_count, reverse=True)
        guild_list_str = "\n".join([f"- {g.name} (ID: {g.id}) | Members: {g.member_count}" for g in guilds])
        
        if len(guild_list_str) > 1900:
            await interaction.followup.send("القائمة طويلة جدًا، تم إرسالها كملف.", file=discord.File(io.BytesIO(guild_list_str.encode('utf-8')), "guilds.txt"))
        elif not guild_list_str:
            await interaction.followup.send("لا يتواجد البوت في أي سيرفرات.")
        else:
            await interaction.followup.send(f"**📜 قائمة السيرفرات ({len(guilds)}):**\n```\n{guild_list_str}\n```")

    @is_bot_owner()
    @guilds_group.command(name="leave", description="[خطير] إجبار البوت على مغادرة سيرفر معين.")
    @app_commands.describe(guild_id="ID السيرفر")
    async def guild_leave(self, interaction: discord.Interaction, guild_id: str):
        try:
            guild = self.bot.get_guild(int(guild_id))
            if not guild:
                return await interaction.response.send_message("❌ | لم أجد سيرفر بهذا الـ ID.", ephemeral=True)
            
            view = ConfirmationView(interaction.user.id, action=f"Leave {guild.name}")
            await interaction.response.send_message(f"هل أنت متأكد أنك تريد إجبار البوت على مغادرة **{guild.name}**؟", view=view, ephemeral=True)
            
            await view.wait()
            if view.value:
                await guild.leave()
                await interaction.edit_original_response(content=f"✅ | غادرت السيرفر **{guild.name}** بنجاح.", view=None)
            else:
                await interaction.edit_original_response(content="✅ | تم إلغاء عملية المغادرة.", view=None)
        except (ValueError, TypeError):
            await interaction.response.send_message("❌ | ID السيرفر غير صالح.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("🔥 | ليس لدي صلاحيات لمغادرة هذا السيرفر.", ephemeral=True)

    # =======================================================================================
    # SECTION: Profile Management Commands
    # =======================================================================================

    @is_bot_owner()
    @profile_group.command(name="set_username", description="[خطير جداً] تغيير اسم مستخدم البوت.")
    @app_commands.describe(name="الاسم الجديد للبوت")
    async def set_username(self, interaction: discord.Interaction, name: str):
        try:
            await self.bot.user.edit(username=name)
            await interaction.response.send_message(f"✅ | تم تغيير اسم البوت إلى **{name}**.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.response.send_message(f"🔥 | فشل تغيير الاسم: {e}", ephemeral=True)

    @is_bot_owner()
    @profile_group.command(name="set_avatar", description="[خطير جداً] تغيير صورة بروفايل البوت.")
    @app_commands.describe(image="الصورة الجديدة للبوت")
    async def set_avatar(self, interaction: discord.Interaction, image: discord.Attachment):
        if not image.content_type.startswith('image/'):
            return await interaction.response.send_message("❌ | الملف المرفق ليس صورة.", ephemeral=True)
        
        try:
            await self.bot.user.edit(avatar=await image.read())
            await interaction.response.send_message("✅ | تم تغيير صورة البوت بنجاح.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.response.send_message(f"🔥 | فشل تغيير الصورة: {e}", ephemeral=True)

    # =======================================================================================
    # SECTION: File Management Commands
    # =======================================================================================

    @is_bot_owner()
    @files_group.command(name="list", description="[خطير جداً] عرض الملفات والمجلدات في مسار معين.")
    @app_commands.describe(path="المسار لعرض محتوياته (e.g., cogs/)")
    async def list_files(self, interaction: discord.Interaction, path: str = "."):
        if ".." in path:
            return await interaction.response.send_message("❌ | الوصول إلى المسارات العليا غير مسموح به.", ephemeral=True)
        if not os.path.isdir(path):
            return await interaction.response.send_message(f"❌ | المسار `{path}` غير موجود.", ephemeral=True)
        
        try:
            items = os.listdir(path)
            dirs = [f"└─ 📂 {d}" for d in items if os.path.isdir(os.path.join(path, d))]
            files = [f"└─ 📄 {f}" for f in items if os.path.isfile(os.path.join(path, f))]
            message = f"📁 **Contents: `{os.path.abspath(path)}`**\n\n" + "\n".join(sorted(dirs)) + "\n" + "\n".join(sorted(files))
            
            if len(message) > 2000:
                await interaction.response.send_message("List too long, sent as file.", file=discord.File(io.BytesIO(message.encode('utf-8')), "file_list.txt"), ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"🔥 | حدث خطأ: {e}", ephemeral=True)
    
    @is_bot_owner()
    @files_group.command(name="logs", description="[خطير] عرض آخر أسطر من ملف سجلات البوت.")
    @app_commands.describe(lines="عدد الأسطر (الافتراضي: 20)")
    async def show_logs(self, interaction: discord.Interaction, lines: app_commands.Range[int, 1, 100] = 20):
        log_file_path = "bot.log" # Change this if your log file has a different name
        if not os.path.isfile(log_file_path):
            return await interaction.response.send_message(f"❌ | The log file (`{log_file_path}`) was not found.", ephemeral=True)
        
        try:
            with open(log_file_path, 'r', encoding='utf-8') as f:
                content = "".join(f.readlines()[-lines:])
            
            if not content:
                return await interaction.response.send_message("📄 | The log file is empty.", ephemeral=True)
            
            output = f"```log\n{content}\n```"
            if len(output) > 2000:
                await interaction.response.send_message(f"Showing last `{lines}` lines from `{log_file_path}`.", file=discord.File(io.BytesIO(content.encode('utf-8')), "latest_logs.log"), ephemeral=True)
            else:
                await interaction.response.send_message(output, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"🔥 | Error reading log file: {e}", ephemeral=True)

    @is_bot_owner()
    @files_group.command(name="show", description="[خطير جداً] عرض محتويات ملف نصي.")
    @app_commands.describe(filepath="مسار الملف المراد عرضه")
    async def show_file(self, interaction: discord.Interaction, filepath: str):
        if ".." in filepath:
            return await interaction.response.send_message("❌ | الوصول إلى المسارات العليا غير مسموح به.", ephemeral=True)
        if not os.path.isfile(filepath):
            return await interaction.response.send_message(f"❌ | الملف `{filepath}` غير موجود.", ephemeral=True)
        
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            if not content:
                return await interaction.response.send_message("📄 | الملف فارغ.", ephemeral=True)
            
            file_extension = filepath.split('.')[-1]
            output = f"```{file_extension}\n{content}\n```"
            
            if len(output) > 2000:
                file_bytes = io.BytesIO(content.encode('utf-8'))
                await interaction.response.send_message("File too long, sent as attachment.", file=discord.File(file_bytes, filename=os.path.basename(filepath)), ephemeral=True)
            else:
                await interaction.response.send_message(output, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"🔥 | حدث خطأ: {e}", ephemeral=True)

    @is_bot_owner()
    @files_group.command(name="download", description="[خطير جداً] تنزيل ملف من السيرفر.")
    @app_commands.describe(filepath="مسار الملف المراد تنزيله")
    async def download_file(self, interaction: discord.Interaction, filepath: str):
        if ".." in filepath:
            return await interaction.response.send_message("❌ | الوصول إلى المسارات العليا غير مسموح به.", ephemeral=True)
        if not os.path.isfile(filepath):
            return await interaction.response.send_message(f"❌ | الملف `{filepath}` غير موجود.", ephemeral=True)
        
        try:
            await interaction.response.send_message(file=discord.File(filepath), ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"🔥 | حدث خطأ: {e}", ephemeral=True)
            
    @is_bot_owner()
    @files_group.command(name="upload", description="[خطير جداً] رفع ملف إلى السيرفر.")
    @app_commands.describe(file="الملف المراد رفعه", path="المسار لحفظ الملف فيه (اختياري)")
    async def upload_file(self, interaction: discord.Interaction, file: discord.Attachment, path: str = "."):
        if ".." in path:
            return await interaction.response.send_message("❌ | الوصول إلى المسارات العليا غير مسموح به.", ephemeral=True)
        if not os.path.isdir(path):
            return await interaction.response.send_message(f"❌ | المسار `{path}` غير موجود.", ephemeral=True)
            
        destination = os.path.join(path, file.filename)
        if os.path.exists(destination):
            return await interaction.response.send_message(f"⚠️ | يوجد ملف بنفس الاسم (`{file.filename}`) هنا.", ephemeral=True)
        
        try:
            await interaction.response.defer(ephemeral=True, thinking=True)
            await file.save(destination)
            await interaction.followup.send(f"✅ | تم رفع الملف بنجاح إلى: `{destination}`")
        except Exception as e:
            await interaction.followup.send(f"🔥 | حدث خطأ: {e}")

    # =======================================================================================
    # SECTION: Blacklist Commands
    # =======================================================================================

    @is_bot_owner()
    @blacklist_group.command(name="add", description="إضافة مستخدم أو سيرفر إلى القائمة السوداء.")
    @app_commands.describe(target_id="ID المستخدم أو السيرفر", reason="سبب الحظر")
    async def blacklist_add(self, interaction: discord.Interaction, target_id: str, reason: str):
        await interaction.response.defer(ephemeral=True)
        if not hasattr(self.bot, 'db'):
            return await interaction.followup.send("❌ | Database not configured.")
        
        try:
            target_id_int = int(target_id)
        except ValueError:
            return await interaction.followup.send("❌ | Invalid ID format.")
        
        # Assumes a table named 'blacklist' with columns: 'id' (BIGINT, PK), 'reason' (TEXT), 'timestamp' (TIMESTAMPTZ)
        await self.bot.db.execute(
            "INSERT INTO blacklist (id, reason, timestamp) VALUES ($1, $2, $3) ON CONFLICT (id) DO UPDATE SET reason = $2, timestamp = $3", 
            target_id_int, reason, datetime.datetime.now(datetime.timezone.utc)
        )
        await self.bot.db.commit()
        self.bot.blacklist.add(target_id_int) # Update in-memory cache
        
        embed = discord.Embed(title="🚫 Blacklist Updated", description=f"Successfully blacklisted `{target_id_int}`.", color=discord.Color.dark_red())
        embed.add_field(name="Reason", value=reason)
        await interaction.followup.send(embed=embed)

    @is_bot_owner()
    @blacklist_group.command(name="remove", description="إزالة مستخدم أو سيرفر من القائمة السوداء.")
    @app_commands.describe(target_id="ID المستخدم أو السيرفر")
    async def blacklist_remove(self, interaction: discord.Interaction, target_id: str):
        await interaction.response.defer(ephemeral=True)
        if not hasattr(self.bot, 'db'):
            return await interaction.followup.send("❌ | Database not configured.")
        
        try:
            target_id_int = int(target_id)
        except ValueError:
            return await interaction.followup.send("❌ | Invalid ID format.")
        
        result = await self.bot.db.execute("DELETE FROM blacklist WHERE id = $1", target_id_int)
        await self.bot.db.commit()
        
        if result.rowcount > 0:
            if target_id_int in self.bot.blacklist:
                self.bot.blacklist.remove(target_id_int) # Update in-memory cache
            await interaction.followup.send(f"✅ | Successfully removed `{target_id_int}` from the blacklist.")
        else:
            await interaction.followup.send(f"⚠️ | ID `{target_id_int}` not found in the blacklist.")

# =======================================================================================
# SECTION: Cog Setup
# =======================================================================================
async def setup(bot: MaxyBot):
    # Initialize attributes on the bot object if they don't exist.
    if not hasattr(bot, 'maintenance_mode'):
        bot.maintenance_mode = False
    if not hasattr(bot, 'blacklist'):
        bot.blacklist = set() # Should be loaded from DB on startup.
        
    await bot.add_cog(HighAdmins(bot))