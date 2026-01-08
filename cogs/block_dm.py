import discord
from discord.ext import commands
from discord import app_commands

class BlockDM(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # منع أوامر البريفكس في DM
    @commands.Cog.listener()
    async def on_command(self, ctx: commands.Context):
        if ctx.guild is None:  # يعني في DM
            await ctx.send("❌ مينفعش تستخدم الأوامر في الخاص (DM).", delete_after=5)
            raise commands.CheckFailure("Command used in DM.")

    # منع أوامر السلاش في DM
    @commands.Cog.listener()
    async def on_app_command_completion(self, interaction: discord.Interaction, command: app_commands.Command):
        if interaction.guild is None:  # يعني في DM
            try:
                await interaction.response.send_message(
                    "❌ مينفعش تستخدم الأوامر في الخاص (DM).",
                    ephemeral=True
                )
            except discord.InteractionResponded:
                await interaction.followup.send(
                    "❌ مينفعش تستخدم الأوامر في الخاص (DM).",
                    ephemeral=True
                )
            raise app_commands.CheckFailure("Slash command used in DM.")

async def setup(bot):
    await bot.add_cog(BlockDM(bot))
