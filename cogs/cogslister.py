from __future__ import annotations
import discord
from discord import app_commands
from discord.ext import commands


class CommandLister(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # كوماند يظهر كل الكوماندات
    @app_commands.command(name="commands", description="عرض جميع الكوماندات مع الكوج التابع ليها")
    @app_commands.checks.has_permissions(administrator=True)
    async def list_commands(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="📜 Bot Commands",
            description="قائمة الكوماندات المتاحة مع الكوج الخاص بيها",
            color=discord.Color.blue()
        )

        commands_dict = {}
        for cmd in self.bot.tree.get_commands():
            cog_name = cmd.module.split(".")[-1] if cmd.module else "No Cog"
            if cog_name not in commands_dict:
                commands_dict[cog_name] = []
            commands_dict[cog_name].append(cmd.name)

        for cog, cmds in commands_dict.items():
            embed.add_field(
                name=f"⚙️ {cog}",
                value=", ".join(f"`/{c}`" for c in cmds),
                inline=False
            )

        await interaction.response.send_message(embed=embed)

    # error handler عشان لو حد مش ادمن
    @list_commands.error
    async def list_commands_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("🚫 لازم يكون عندك صلاحيات **Administrator** عشان تستخدم الكوماند ده.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(CommandLister(bot))
