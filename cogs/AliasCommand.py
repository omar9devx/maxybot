# Filename: cogs/AliasCommand.py
import discord
from discord import app_commands
from discord.ext import commands
import aiosqlite
from pathlib import Path

DB_PATH = Path("data/aliases.db")  # قاعدة البيانات لتخزين aliases

class AliasCommand(commands.Cog):
    """Cog to create command aliases with admin restriction and persistent storage"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.bot.loop.create_task(self.setup_db())

    async def setup_db(self):
        DB_PATH.parent.mkdir(exist_ok=True)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS aliases (
                    guild_id TEXT NOT NULL,
                    alias TEXT NOT NULL,
                    command_name TEXT NOT NULL,
                    PRIMARY KEY (guild_id, alias)
                )
            """)
            await db.commit()

    async def check_admin(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ You need Administrator permissions to use this command!", ephemeral=True
            )
            return False
        return True

    # ------------------ Slash Commands لإدارة aliases ------------------
    @app_commands.command(name="alias", description="Create an alias for a command")
    @app_commands.describe(command="The command to alias (use /command_name)", alias="The alias name")
    async def alias(self, interaction: discord.Interaction, command: str, alias: str):
        if not await self.check_admin(interaction):
            return
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT OR REPLACE INTO aliases (guild_id, alias, command_name) VALUES (?, ?, ?)",
                (str(interaction.guild.id), alias.lower(), command.lstrip("/"))
            )
            await db.commit()
        await interaction.response.send_message(
            f"✅ Alias `{alias}` created for command `{command}`!", ephemeral=True
        )

    @app_commands.command(name="removealias", description="Remove an alias")
    @app_commands.describe(alias="The alias to remove")
    async def removealias(self, interaction: discord.Interaction, alias: str):
        if not await self.check_admin(interaction):
            return
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "DELETE FROM aliases WHERE guild_id = ? AND alias = ?",
                (str(interaction.guild.id), alias.lower())
            )
            await db.commit()
            if cursor.rowcount == 0:
                await interaction.response.send_message(f"❌ Alias `{alias}` not found!", ephemeral=True)
            else:
                await interaction.response.send_message(f"✅ Alias `{alias}` removed!", ephemeral=True)

    @app_commands.command(name="showaliases", description="Show all aliases for this server")
    async def showaliases(self, interaction: discord.Interaction):
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT alias, command_name FROM aliases WHERE guild_id = ?",
                (str(interaction.guild.id),)
            )
            rows = await cursor.fetchall()
        if not rows:
            await interaction.response.send_message("No aliases found for this server.", ephemeral=True)
            return
        msg = "\n".join([f"`{row[0]}` → `{row[1]}`" for row in rows])
        await interaction.response.send_message(f"**Aliases:**\n{msg}", ephemeral=True)

    # ------------------ Listener لتشغيل aliases عند كتابة الرسائل ------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        first_word = message.content.split()[0].lower()
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT command_name FROM aliases WHERE guild_id = ? AND alias = ?",
                (str(message.guild.id), first_word)
            )
            row = await cursor.fetchone()

        if row:
            command_name = row[0]

            # البحث عن slash command
            cmd = self.bot.tree.get_command(command_name)
            if not cmd:
                await message.channel.send(f"❌ Command `{command_name}` not found!")
                return

            # إعداد fake interaction لتشغيل الأمر
            class FakeInteraction:
                def __init__(self, message):
                    self.message = message
                    self.user = message.author
                    self.channel = message.channel
                    self.guild = message.guild

                async def response_send_message(self, content, ephemeral=False):
                    await self.channel.send(content)

                async def response(self):
                    return self

                async def send_message(self, content, ephemeral=False):
                    await self.channel.send(content)

            # تشغيل الأمر
            ctx = await self.bot.get_context(message)
            await ctx.send(f"⚡ Executing alias `{first_word}` → `{command_name}`")
            await self.bot.get_command(command_name).callback(ctx)  # يشغل الأمر

async def setup(bot: commands.Bot):
    await bot.add_cog(AliasCommand(bot))
