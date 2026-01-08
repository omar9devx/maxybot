# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..bot import MaxyBot  # عشان type hints بس، مش تنفيذ فعلي

from .utils import cog_command_error  # لو cog_command_error موجود في utils/__init__.py أو utils/utils.py
import discord
from discord import app_commands
from discord.ext import commands

class RolesManage(commands.Cog):
    """Cog كامل لإدارة الرتب متوافق مع MaxyBot وUtils Cog"""

    def __init__(self, bot):
        self.bot: commands.Bot = bot
        self.utils: Utils = bot.get_cog("Utils")  # نجيب Cog الأدوات

    # ---------------- Main Group ----------------
    role_group = app_commands.Group(name="role", description="إدارة الرتب في السيرفر")

    # ---------------- Basic Commands ----------------
    @role_group.command(name="create", description="إنشاء رتبة جديدة")
    @app_commands.default_permissions(manage_roles=True)
    async def create(self, interaction: discord.Interaction, name: str, colour: str = "#2f3136"):
        try:
            role = await interaction.guild.create_role(
                name=name,
                colour=discord.Colour(int(colour.replace("#",""),16))
            )
            await self.utils.safe_send(interaction.channel, f"✅ تم إنشاء الرتبة: {role.name}")
        except Exception as e:
            await self.utils.safe_send(interaction.channel, f"❌ حدث خطأ: {e}")

    @role_group.command(name="delete", description="حذف رتبة")
    @app_commands.default_permissions(manage_roles=True)
    async def delete(self, interaction: discord.Interaction, role: discord.Role):
        try:
            await role.delete()
            await self.utils.safe_send(interaction.channel, f"✅ تم حذف الرتبة: {role.name}")
        except Exception as e:
            await self.utils.safe_send(interaction.channel, f"❌ حدث خطأ: {e}")

    @role_group.command(name="add", description="إضافة رتبة لعضو")
    @app_commands.default_permissions(manage_roles=True)
    async def add(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role):
        try:
            await member.add_roles(role)
            await self.utils.safe_send(interaction.channel, f"✅ تم إضافة رتبة {role.name} للعضو {member.display_name}")
        except Exception as e:
            await self.utils.safe_send(interaction.channel, f"❌ حدث خطأ: {e}")

    @role_group.command(name="remove", description="إزالة رتبة من عضو")
    @app_commands.default_permissions(manage_roles=True)
    async def remove(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role):
        try:
            await member.remove_roles(role)
            await self.utils.safe_send(interaction.channel, f"✅ تم إزالة رتبة {role.name} من العضو {member.display_name}")
        except Exception as e:
            await self.utils.safe_send(interaction.channel, f"❌ حدث خطأ: {e}")

    @role_group.command(name="info", description="عرض معلومات عن رتبة")
    async def info(self, interaction: discord.Interaction, role: discord.Role):
        embed = discord.Embed(title=f"معلومات الرتبة: {role.name}", colour=role.colour)
        embed.add_field(name="ID", value=role.id)
        embed.add_field(name="Position", value=role.position)
        embed.add_field(name="الأعضاء", value=len(role.members))
        embed.set_footer(text=f"تم الإنشاء بتاريخ: {role.created_at.strftime('%Y-%m-%d')}")
        await self.utils.safe_send(interaction.channel, embed=embed)

    @role_group.command(name="list", description="عرض كل الرتب في السيرفر")
    async def list_roles(self, interaction: discord.Interaction):
        roles = [role.name for role in interaction.guild.roles if role != interaction.guild.default_role]
        message = "📜 رتب السيرفر:\n" + "\n".join(roles) if roles else "لا توجد رتب."
        await self.utils.safe_send(interaction.channel, message)

    # ---------------- Advanced Commands ----------------
    @role_group.command(name="rename", description="تغيير اسم رتبة")
    @app_commands.default_permissions(manage_roles=True)
    async def rename(self, interaction: discord.Interaction, role: discord.Role, new_name: str):
        try:
            await role.edit(name=new_name)
            await self.utils.safe_send(interaction.channel, f"✅ تم تغيير اسم الرتبة إلى: {new_name}")
        except Exception as e:
            await self.utils.safe_send(interaction.channel, f"❌ حدث خطأ: {e}")

    @role_group.command(name="color", description="تغيير لون الرتبة")
    @app_commands.default_permissions(manage_roles=True)
    async def color(self, interaction: discord.Interaction, role: discord.Role, colour: str):
        try:
            await role.edit(colour=discord.Colour(int(colour.replace("#",""),16)))
            await self.utils.safe_send(interaction.channel, f"✅ تم تغيير لون الرتبة {role.name}")
        except Exception as e:
            await self.utils.safe_send(interaction.channel, f"❌ حدث خطأ: {e}")

    @role_group.command(name="top", description="رفع الرتبة لأعلى")
    @app_commands.default_permissions(manage_roles=True)
    async def top(self, interaction: discord.Interaction, role: discord.Role):
        try:
            await role.edit(position=len(interaction.guild.roles)-1)
            await self.utils.safe_send(interaction.channel, f"✅ تم رفع الرتبة {role.name} لأعلى الرتب")
        except Exception as e:
            await self.utils.safe_send(interaction.channel, f"❌ حدث خطأ: {e}")

    @role_group.command(name="bottom", description="نقل الرتبة لأسفل")
    @app_commands.default_permissions(manage_roles=True)
    async def bottom(self, interaction: discord.Interaction, role: discord.Role):
        try:
            await role.edit(position=1)
            await self.utils.safe_send(interaction.channel, f"✅ تم نقل الرتبة {role.name} لأسفل الرتب")
        except Exception as e:
            await self.utils.safe_send(interaction.channel, f"❌ حدث خطأ: {e}")

    @role_group.command(name="giveall", description="إعطاء رتبة لكل الأعضاء")
    @app_commands.default_permissions(manage_roles=True)
    async def giveall(self, interaction: discord.Interaction, role: discord.Role):
        try:
            for member in interaction.guild.members:
                if role not in member.roles:
                    await member.add_roles(role)
            await self.utils.safe_send(interaction.channel, f"✅ تم إعطاء رتبة {role.name} لكل الأعضاء")
        except Exception as e:
            await self.utils.safe_send(interaction.channel, f"❌ حدث خطأ: {e}")

    @role_group.command(name="removeall", description="إزالة رتبة من كل الأعضاء")
    @app_commands.default_permissions(manage_roles=True)
    async def removeall(self, interaction: discord.Interaction, role: discord.Role):
        try:
            for member in interaction.guild.members:
                if role in member.roles:
                    await member.remove_roles(role)
            await self.utils.safe_send(interaction.channel, f"✅ تم إزالة رتبة {role.name} من كل الأعضاء")
        except Exception as e:
            await self.utils.safe_send(interaction.channel, f"❌ حدث خطأ: {e}")

    @role_group.command(name="random", description="إعطاء رتبة عشوائية لعضو")
    @app_commands.default_permissions(manage_roles=True)
    async def random_role(self, interaction: discord.Interaction, member: discord.Member):
        try:
            roles = [r for r in interaction.guild.roles if r != interaction.guild.default_role]
            if roles:
                role = random.choice(roles)
                await member.add_roles(role)
                await self.utils.safe_send(interaction.channel, f"🎲 تم إعطاء رتبة عشوائية {role.name} للعضو {member.display_name}")
            else:
                await self.utils.safe_send(interaction.channel, "لا توجد رتب لأختيارها")
        except Exception as e:
            await self.utils.safe_send(interaction.channel, f"❌ حدث خطأ: {e}")

    @role_group.command(name="mute", description="Mute رتبة")
    @app_commands.default_permissions(manage_roles=True)
    async def mute(self, interaction: discord.Interaction, role: discord.Role):
        try:
            await role.edit(permissions=discord.Permissions(send_messages=False))
            await self.utils.safe_send(interaction.channel, f"🔇 تم Mute للرتبة {role.name}")
        except Exception as e:
            await self.utils.safe_send(interaction.channel, f"❌ حدث خطأ: {e}")

    @role_group.command(name="unmute", description="Unmute رتبة")
    @app_commands.default_permissions(manage_roles=True)
    async def unmute(self, interaction: discord.Interaction, role: discord.Role):
        try:
            await role.edit(permissions=discord.Permissions(send_messages=True))
            await self.utils.safe_send(interaction.channel, f"🔊 تم إزالة Mute للرتبة {role.name}")
        except Exception as e:
            await self.utils.safe_send(interaction.channel, f"❌ حدث خطأ: {e}")

    @role_group.command(name="protect", description="حماية الرتبة")
    @app_commands.default_permissions(manage_roles=True)
    async def protect(self, interaction: discord.Interaction, role: discord.Role):
        try:
            await role.edit(permissions=discord.Permissions(administrator=False))
            await self.utils.safe_send(interaction.channel, f"🛡️ تم حماية الرتبة {role.name}")
        except Exception as e:
            await self.utils.safe_send(interaction.channel, f"❌ حدث خطأ: {e}")

    @role_group.command(name="unprotect", description="إلغاء حماية الرتبة")
    @app_commands.default_permissions(manage_roles=True)
    async def unprotect(self, interaction: discord.Interaction, role: discord.Role):
        try:
            await role.edit(permissions=discord.Permissions(administrator=True))
            await self.utils.safe_send(interaction.channel, f"✅ تم إزالة الحماية عن الرتبة {role.name}")
        except Exception as e:
            await self.utils.safe_send(interaction.channel, f"❌ حدث خطأ: {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(RolesManage(bot))
