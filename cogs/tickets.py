# -*- coding: utf-8 -*-
import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import os
import aiofiles
from datetime import datetime

TRANSCRIPTS_DIR = "transcripts"

if not os.path.exists(TRANSCRIPTS_DIR):
    os.makedirs(TRANSCRIPTS_DIR)

class Tickets(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # -----------------------------
    # Views
    # -----------------------------
    class TicketPanelView(discord.ui.View):
        def __init__(self, staff_roles_ids: list[int], category_id: int, panel_title: str, ticket_type: str):
            super().__init__(timeout=None)
            self.add_item(
                discord.ui.Button(
                    label=f"{panel_title} - {ticket_type}",
                    style=discord.ButtonStyle.primary,
                    emoji="🎟️",
                    custom_id=f"ticket_create_{ticket_type}_{category_id}_{'_'.join(map(str, staff_roles_ids))}"
                )
            )

    class TicketActionView(discord.ui.View):
        def __init__(self, claimed_by: str = None):
            super().__init__(timeout=None)
            self.claimed_by = claimed_by
            self.btn_claim = discord.ui.Button(label="Claim", style=discord.ButtonStyle.success, emoji="🙋", custom_id="persistent_ticket_claim")
            self.btn_transcript = discord.ui.Button(label="Transcript", style=discord.ButtonStyle.secondary, emoji="📜", custom_id="persistent_ticket_transcript")
            self.btn_close = discord.ui.Button(label="Close", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="persistent_ticket_close")
            self.btn_mention = discord.ui.Button(label="@Admins", style=discord.ButtonStyle.secondary, emoji="👑", custom_id="persistent_ticket_mention_admins")

            if claimed_by:
                self.btn_claim.disabled = True

            self.add_item(self.btn_claim)
            self.add_item(self.btn_transcript)
            self.add_item(self.btn_close)
            self.add_item(self.btn_mention)

    # -----------------------------
    # Listeners
    # -----------------------------
    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if not interaction.data or not (custom_id := interaction.data.get("custom_id")):
            return

        if custom_id.startswith("ticket_create_"):
            await self.create_ticket(interaction, custom_id)
        elif custom_id == "persistent_ticket_claim":
            await self.claim_ticket(interaction)
        elif custom_id == "persistent_ticket_transcript":
            await self.transcript_ticket(interaction)
        elif custom_id == "persistent_ticket_close":
            await self.close_ticket(interaction)
        elif custom_id == "persistent_ticket_mention_admins":
            await self.mention_admins(interaction)
        elif custom_id.startswith("persistent_ticket_reopen"):
            await self.reopen_ticket(interaction)

    # -----------------------------
    # Ticket Actions
    # -----------------------------
    async def create_ticket(self, interaction: discord.Interaction, custom_id: str):
        await interaction.response.defer(ephemeral=True, thinking=True)
        _, ticket_type, cat_id_str, *staff_ids = custom_id.split('_')
        guild = interaction.guild
        
        # منع التذاكر المكررة
        existing_ticket = discord.utils.find(
            lambda c: c.topic and f"ticket_user_{interaction.user.id}" in c.topic,
            guild.text_channels
        )
        if existing_ticket:
            return await interaction.followup.send(f"❌ You already have a ticket open: {existing_ticket.mention}", ephemeral=True)

        staff_roles = [guild.get_role(int(rid)) for rid in staff_ids if guild.get_role(int(rid))]
        category = guild.get_channel(int(cat_id_str))
        if not staff_roles or not isinstance(category, discord.CategoryChannel):
            return await interaction.followup.send("❌ Ticket system misconfigured.", ephemeral=True)

        overwrites = {guild.default_role: discord.PermissionOverwrite(view_channel=False)}
        overwrites[interaction.user] = discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True, embed_links=True)
        for role in staff_roles:
            overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
        overwrites[guild.me] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

        channel = await guild.create_text_channel(
            name=f"ticket-{interaction.user.name}",
            category=category,
            overwrites=overwrites,
            topic=f"Ticket for {interaction.user.name} | User ID: ticket_user_{interaction.user.id} | Type: {ticket_type}"
        )

        await interaction.followup.send(f"✅ Ticket created! {channel.mention}", ephemeral=True)

        staff_mentions = " ".join(role.mention for role in staff_roles)
        embed = discord.Embed(
            title=f"{ticket_type} Ticket",
            description=f"Welcome {interaction.user.mention}! {staff_mentions}\nPlease describe your issue.",
            color=discord.Color.blurple()
        )
        await channel.send(embed=embed, view=self.TicketActionView())

    async def claim_ticket(self, interaction: discord.Interaction):
        if "ticket-" not in interaction.channel.name: 
            return
        view = self.TicketActionView(claimed_by=str(interaction.user))
        await interaction.message.edit(view=view)
        await interaction.response.send_message(f"🙋 Ticket claimed by {interaction.user.mention}.", ephemeral=False)

    async def transcript_ticket(self, interaction: discord.Interaction):
        if "ticket-" not in interaction.channel.name: 
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        transcript_filename = f"{TRANSCRIPTS_DIR}/{interaction.channel.id}.html"
        async with aiofiles.open(transcript_filename, 'w', encoding='utf-8') as f:
            await f.write(f"<html><body><h1>Transcript for #{interaction.channel.name}</h1>")
            async for msg in interaction.channel.history(limit=None, oldest_first=True):
                await f.write(f"<p><b>{msg.author.name}</b> ({msg.created_at.strftime('%Y-%m-%d %H:%M:%S')}): {msg.clean_content}</p>")
            await f.write("</body></html>")

        # إرسال نسخة للـDM
        try:
            await interaction.user.send(file=discord.File(transcript_filename))
            await interaction.followup.send(f"✅ Transcript sent to your DMs.", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send(f"⚠️ Could not DM the transcript. Check your privacy settings.", ephemeral=True)
        finally:
            os.remove(transcript_filename)

    async def close_ticket(self, interaction: discord.Interaction):
        if "ticket-" not in interaction.channel.name: 
            return
        await interaction.response.send_message("🔒 Closing this ticket in 5 seconds...")
        await asyncio.sleep(5)
        # إنشاء زر لإعادة الفتح
        view = discord.ui.View()
        reopen_btn = discord.ui.Button(label="Reopen Ticket", style=discord.ButtonStyle.primary, custom_id=f"persistent_ticket_reopen_{interaction.channel.id}")
        view.add_item(reopen_btn)
        msg = await interaction.channel.send("Ticket closed.", view=view)
        await interaction.channel.edit(name=f"closed-{interaction.channel.name}")
        await interaction.channel.set_permissions(interaction.guild.default_role, view_channel=False)

    async def reopen_ticket(self, interaction: discord.Interaction):
        await interaction.response.send_message("♻️ Ticket reopened!", ephemeral=True)
        channel = interaction.channel
        await channel.edit(name=channel.name.replace("closed-", "ticket-"))
        await channel.set_permissions(interaction.guild.default_role, view_channel=False)
        await channel.set_permissions(interaction.user, view_channel=True, send_messages=True)
        await interaction.message.delete()

    async def mention_admins(self, interaction: discord.Interaction):
        if "ticket-" not in interaction.channel.name: 
            return
        guild = interaction.guild
        admins = [member.mention for member in guild.members if member.guild_permissions.administrator]
        if not admins:
            await interaction.response.send_message("No admins found.", ephemeral=True)
        else:
            mentions = " ".join(admins)
            await interaction.response.send_message(f"👑 Attention Admins: {mentions}", allowed_mentions=discord.AllowedMentions(users=True))

    # -----------------------------
    # Slash Command
    # -----------------------------
    @app_commands.command(name="ticket-setup", description="🛠️ Creates the ticket system panel.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ticketsetup(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        staff_roles: str,  # IDs separated by commas
        category: discord.CategoryChannel,
        panel_title: str,
        panel_description: str,
        ticket_type: str = "Support"
    ):
        staff_roles_ids = [int(rid.strip()) for rid in staff_roles.split(",")]
        embed = discord.Embed(title=panel_title, description=panel_description, color=discord.Color.dark_blue())
        view = self.TicketPanelView(staff_roles_ids, category.id, panel_title, ticket_type)
        await channel.send(embed=embed, view=view)
        await interaction.response.send_message(f"✅ Ticket panel created in {channel.mention}.", ephemeral=True)

# -----------------------------
# Cog Setup
# -----------------------------
async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))
