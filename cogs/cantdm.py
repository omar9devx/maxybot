# -*- coding: utf-8 -*-
import discord
from discord.ext import commands

class CantDM(commands.Cog):
    """
    Cog لمنع استخدام أي كوماند في DM.
    """
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_command(self, ctx):
        if isinstance(ctx.channel, discord.DMChannel):
            await ctx.send("❌ Commands only work in servers! الرجاء استخدام البوت داخل السيرفرات.")
            # وقف تنفيذ الكوماند
            ctx.command.reset_cooldown(ctx)
            return  # بدل raise، ده هيوقف الكوماند بدون أخطاء

async def setup(bot):
    await bot.add_cog(CantDM(bot))
