from __future__ import annotations
from typing import TYPE_CHECKING, Optional, List, Union
import io
import discord
from discord import app_commands
from discord.ext import commands, tasks
import datetime
from datetime import datetime as dt, UTC
import random
import aiohttp
import os
import re
import humanize
import psutil
import time
import asyncio
import json
import math
import difflib
import yt_dlp
from PIL import Image, ImageDraw, ImageFont, ImageOps

if TYPE_CHECKING:
    from ..bot import MaxyBot

from .utils import cog_command_error

# --- Blackjack Game Logic ---
class BlackjackGame:
    """A class to manage the logic of a blackjack game."""
    def __init__(self):
        self.deck = self._create_deck()
        self.player_hand = []
        self.dealer_hand = []

    def _create_deck(self) -> list:
        """Creates and shuffles a standard deck of cards."""
        ranks = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
        suits = ['♠️', '♥️', '♦️', '♣️']
        deck = [{'rank': rank, 'suit': suit} for rank in ranks for suit in suits]
        random.shuffle(deck)
        return deck

    def _calculate_value(self, hand: list) -> int:
        """Calculates the value of a hand."""
        value = 0
        aces = 0
        for card in hand:
            if card['rank'] in ['J', 'Q', 'K']:
                value += 10
            elif card['rank'] == 'A':
                aces += 1
                value += 11
            else:
                value += int(card['rank'])

        while value > 21 and aces:
            value -= 10
            aces -= 1
        return value

    def hand_to_string(self, hand: list, hide_dealer_card: bool = False) -> str:
        """Converts a hand to a string representation."""
        if hide_dealer_card:
            return f"[{self.card_to_string(hand[0])}] [?]"
        return " ".join([f"[{self.card_to_string(card)}]" for card in hand])

    def card_to_string(self, card: dict) -> str:
        """Converts a single card to a string."""
        return f"{card['rank']}{card['suit']}"

    def deal_initial(self):
        """Deals the initial two cards to player and dealer."""
        self.player_hand.append(self.deck.pop())
        self.dealer_hand.append(self.deck.pop())
        self.player_hand.append(self.deck.pop())
        self.dealer_hand.append(self.deck.pop())

    def hit(self, hand: list) -> dict:
        """Adds a card to the specified hand."""
        card = self.deck.pop()
        hand.append(card)
        return card

class BlackjackView(discord.ui.View):
    """A Discord UI View with 'Hit' and 'Stand' buttons for Blackjack."""
    def __init__(self, game: BlackjackGame, cog_instance, interaction: discord.Interaction, bet: int):
        super().__init__(timeout=120.0)
        self.game = game
        self.cog = cog_instance
        self.interaction = interaction
        self.bet = bet
        self.winner = None

    async def on_timeout(self):
        if self.winner is None: # If game is still running
            for item in self.children:
                item.disabled = True
            await self.interaction.edit_original_response(content="⏰ Game timed out. You lose your bet.", view=self)

    async def _update_embed(self, game_over: bool = False, result_message: str = ""):
        """Helper function to update the game embed."""
        player_score = self.game._calculate_value(self.game.player_hand)
        
        if game_over:
            dealer_score = self.game._calculate_value(self.game.dealer_hand)
            dealer_hand_str = self.game.hand_to_string(self.game.dealer_hand)
            color = discord.Color.red()
            if "win" in result_message.lower():
                color = discord.Color.green()
            elif "push" in result_message.lower():
                color = discord.Color.light_grey()
        else:
            dealer_score = self.game._calculate_value([self.game.dealer_hand[0]])
            dealer_hand_str = self.game.hand_to_string(self.game.dealer_hand, hide_dealer_card=True)
            color = discord.Color.blue()
        
        embed = discord.Embed(title=f"🃏 Blackjack | Bet: {self.bet:,}", description=result_message, color=color)
        embed.add_field(name=f"Your Hand ({player_score})", value=self.game.hand_to_string(self.game.player_hand), inline=False)
        embed.add_field(name=f"Dealer's Hand ({dealer_score if not game_over else self.game._calculate_value(self.game.dealer_hand)})", value=dealer_hand_str, inline=False)
        
        await self.interaction.edit_original_response(embed=embed, view=self if not game_over else None)

    async def _end_game(self, result: str, winnings: int):
        """Ends the game, disables buttons, and updates balance."""
        self.winner = result
        for item in self.children:
            item.disabled = True
        
        if winnings > 0:
            await self.cog.update_balance(self.interaction.guild.id, self.interaction.user.id, wallet_change=winnings)
            
        await self._update_embed(game_over=True, result_message=result)
        self.stop()

    @discord.ui.button(label="Hit", style=discord.ButtonStyle.green)
    async def hit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.game.hit(self.game.player_hand)
        player_score = self.game._calculate_value(self.game.player_hand)

        if player_score > 21:
            await self._end_game(f"💥 Bust! You lose {self.bet:,} coins.", 0)
        else:
            await self._update_embed()

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.red)
    async def stand_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        
        player_score = self.game._calculate_value(self.game.player_hand)
        dealer_score = self.game._calculate_value(self.game.dealer_hand)

        while dealer_score < 17:
            self.game.hit(self.game.dealer_hand)
            dealer_score = self.game._calculate_value(self.game.dealer_hand)

        if dealer_score > 21:
            await self._end_game(f"🎉 Dealer busts! You win {int(self.bet * 2):,} coins!", self.bet * 2)
        elif dealer_score > player_score:
            await self._end_game(f"😭 Dealer wins! You lose {self.bet:,} coins.", 0)
        elif player_score > dealer_score:
            await self._end_game(f"🎉 You win! You get {int(self.bet * 2):,} coins!", self.bet * 2)
        else:
            await self._end_game(f"😐 It's a push! Your bet of {self.bet:,} coins is returned.", self.bet)

# --- Economy Cog ---
class Economy(commands.Cog, name="Economy"):
    def __init__(self, bot: MaxyBot):
        self.bot = bot
        self.http_session = bot.http_session
        self.shop_items = {}
        self.font_path = str(self.bot.root_path / "assets" / "fonts" / "font.ttf")
        self.bg_path = self.bot.root_path / "assets" / "images" / "profile_backgrounds"
        self.work_responses = [
            "You worked as a programmer and debugged some code, earning **{symbol} {amount}**.",
            "You flipped burgers at the local diner and got **{symbol} {amount}**.",
            "You helped an old lady cross the street and she gave you **{symbol} {amount}**.",
            "You mined some rare minerals and sold them for **{symbol} {amount}**.",
            "You wrote a hit song and the royalties paid you **{symbol} {amount}**.",
            "You streamed video games for a few hours and your fans donated **{symbol} {amount}**."
        ]
        try:
            with open(self.bot.root_path / "assets/json/shop_items.json", 'r', encoding='utf-8') as f:
                self.shop_items = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.bot.logger.error("Could not load shop_items.json. Shop functionality will be limited.")

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """Handles errors for commands in this cog."""
        if isinstance(error, app_commands.CommandOnCooldown):
            retry_after = humanize.naturaldelta(datetime.timedelta(seconds=error.retry_after))
            await interaction.response.send_message(f"⏳ This command is on cooldown. Please try again in **{retry_after}**.", ephemeral=True)
        else:
            await cog_command_error(interaction, error)

    # --- Database Helper Methods ---
    async def get_balance(self, guild_id: int, user_id: int) -> dict:
        """Fetches a user's balance, creating an entry if it doesn't exist."""
        data = await self.bot.db.fetchone("SELECT wallet, bank FROM economy WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
        if not data:
            conf = self.bot.get_guild_config(guild_id)
            start_balance = conf['economy'].get('start_balance', 100)
            await self.bot.db.execute("INSERT INTO economy (guild_id, user_id, wallet) VALUES (?, ?, ?)", (guild_id, user_id, start_balance))
            return {'wallet': start_balance, 'bank': 0}
        return {'wallet': data['wallet'], 'bank': data['bank']}

    async def update_balance(self, guild_id: int, user_id: int, wallet_change: int = 0, bank_change: int = 0):
        """Updates a user's balance in the database."""
        await self.bot.db.execute(f"INSERT OR IGNORE INTO economy (guild_id, user_id) VALUES (?, ?)", (guild_id, user_id))
        await self.bot.db.execute(f"UPDATE economy SET wallet = wallet + ?, bank = bank + ? WHERE guild_id = ? AND user_id = ?", (wallet_change, bank_change, guild_id, user_id))

    async def has_item(self, guild_id: int, user_id: int, item_id: str) -> bool:
        """Checks if a user has a specific item in their inventory."""
        item = await self.bot.db.fetchone("SELECT 1 FROM user_inventory WHERE user_id = ? AND guild_id = ? AND item_id = ?", (user_id, guild_id, item_id))
        return item is not None
        
    # --- Image Generation ---
    def generate_profile_image(self, user_data: dict):
        """Generates the profile card image using Pillow."""
        username = user_data['username']
        level = user_data['level']
        rank = user_data['rank']
        wallet = user_data['wallet']
        xp = user_data['xp']
        xp_needed = user_data['xp_needed']
        currency_name = user_data['currency_name']
        bg_file = user_data['bg_file']

        bg_image = Image.open(self.bg_path / bg_file).convert("RGBA")
        avatar_image = Image.open(io.BytesIO(user_data['avatar_bytes'])).convert("RGBA").resize((184, 184))

        mask = Image.new('L', avatar_image.size, 0)
        draw_mask = ImageDraw.Draw(mask)
        draw_mask.ellipse((0, 0) + avatar_image.size, fill=255)

        img = Image.new("RGBA", (934, 282), (0,0,0,0))
        img.paste(bg_image, (0,0))
        img.paste(avatar_image, (63, 50), mask)

        draw = ImageDraw.Draw(img)
        font_big = ImageFont.truetype(self.font_path, 48)
        font_medium = ImageFont.truetype(self.font_path, 35)
        font_small = ImageFont.truetype(self.font_path, 25)

        draw.text((280, 55), username, (255, 255, 255), font=font_big, stroke_width=1, stroke_fill=(0,0,0))
        draw.text((285, 130), f"Level: {level}", (255, 255, 255), font=font_medium, stroke_width=1, stroke_fill=(0,0,0))
        draw.text((490, 130), f"Rank: #{rank}", (255, 255, 255), font=font_medium, stroke_width=1, stroke_fill=(0,0,0))
        draw.text((285, 180), f"{wallet:,} {currency_name}", (255, 255, 255), font=font_medium, stroke_width=1, stroke_fill=(0,0,0))

        xp_percent = (xp / xp_needed) if xp_needed > 0 else 0
        xp_bar_width = int(590 * xp_percent)
        draw.rectangle((290, 230, 880, 245), fill=(70, 70, 70))
        if xp_bar_width > 0:
            draw.rectangle((290, 230, 290 + xp_bar_width, 245), fill=(59, 171, 255))

        xp_text = f"{xp:,} / {xp_needed:,} XP"
        text_bbox = draw.textbbox((0, 0), xp_text, font=font_small)
        text_width = text_bbox[2] - text_bbox[0]
        draw.text((880 - text_width, 195), xp_text, (255, 255, 255), font=font_small, stroke_width=1, stroke_fill=(0,0,0))

        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer

    # --- Core Economy Commands ---
    @app_commands.command(name="profile", description="Displays your server profile.")
    @app_commands.describe(user="The user to view the profile of.")
    async def profile(self, interaction: discord.Interaction, user: Optional[discord.Member] = None):
        target = user or interaction.user
        if target.bot:
            return await interaction.response.send_message("Bots don't have profiles!", ephemeral=True)
        await interaction.response.defer()

        leveling_cog = self.bot.get_cog("Leveling")
        conf = self.bot.get_guild_config(interaction.guild.id)

        level_data = await self.bot.db.fetchone("SELECT level, xp FROM leveling WHERE guild_id = ? AND user_id = ?", (interaction.guild.id, target.id))
        eco_data = await self.get_balance(interaction.guild.id, target.id)
        leaderboard = await self.bot.db.fetchall("SELECT user_id FROM leveling WHERE guild_id = ? ORDER BY level DESC, xp DESC", (interaction.guild.id,))

        rank = "N/A"
        for i, entry in enumerate(leaderboard):
            if entry['user_id'] == target.id:
                rank = i + 1
                break

        level = level_data['level'] if level_data else 0
        xp = level_data['xp'] if level_data else 0
        xp_needed = leveling_cog.get_xp_for_level(level) if leveling_cog else 100

        active_bg_data = await self.bot.db.fetchone("SELECT item_id FROM user_inventory WHERE guild_id = ? AND user_id = ? AND item_type = 'profile_background' AND is_active = 1", (interaction.guild.id, target.id))
        bg_id = active_bg_data['item_id'] if active_bg_data else 'default_bg'
        bg_item = next((item for item in self.shop_items.get("profile_backgrounds", []) if item['id'] == bg_id), None)
        bg_file = bg_item['path'] if bg_item else 'default.png'

        avatar_bytes = await target.display_avatar.with_format("png").read()

        user_data = {
            "username": target.display_name, "level": level, "rank": rank, "xp": xp, "xp_needed": xp_needed,
            "wallet": eco_data['wallet'], "currency_name": conf['economy']['currency_name'],
            "bg_file": bg_file, "avatar_bytes": avatar_bytes
        }

        loop = asyncio.get_event_loop()
        final_buffer = await loop.run_in_executor(None, self.generate_profile_image, user_data)

        file = discord.File(fp=final_buffer, filename=f"profile_{target.id}.png")
        await interaction.followup.send(file=file)

    @app_commands.command(name="balance", description="Check your or another user's balance.")
    @app_commands.describe(user="The user to check the balance of.")
    async def balance(self, interaction: discord.Interaction, user: Optional[discord.Member] = None):
        target = user or interaction.user
        if target.bot:
            return await interaction.response.send_message("Bots don't have money!", ephemeral=True)

        conf = self.bot.get_guild_config(interaction.guild.id)
        currency_symbol = conf['economy']['currency_symbol']
        bal = await self.get_balance(interaction.guild.id, target.id)

        embed = discord.Embed(title=f"{target.display_name}'s Balance", color=target.color)
        embed.add_field(name="Wallet", value=f"{currency_symbol} {bal['wallet']:,}", inline=True)
        embed.add_field(name="Bank", value=f"{currency_symbol} {bal['bank']:,}", inline=True)
        embed.add_field(name="Total", value=f"{currency_symbol} {bal['wallet'] + bal['bank']:,}", inline=True)
        await interaction.response.send_message(embed=embed)
        
    @app_commands.command(name="pay", description="Transfer coins to another user.")
    @app_commands.describe(user="The user you want to pay.", amount="The amount of coins to pay.")
    async def pay(self, interaction: discord.Interaction, user: discord.Member, amount: app_commands.Range[int, 1, None]):
        if user.id == interaction.user.id:
            return await interaction.response.send_message("You can't pay yourself!", ephemeral=True)
        if user.bot:
            return await interaction.response.send_message("You can't pay bots!", ephemeral=True)
            
        bal = await self.get_balance(interaction.guild.id, interaction.user.id)
        if bal['wallet'] < amount:
            return await interaction.response.send_message("You don't have enough money in your wallet for this transaction.", ephemeral=True)

        await self.update_balance(interaction.guild.id, interaction.user.id, wallet_change=-amount)
        await self.update_balance(interaction.guild.id, user.id, wallet_change=amount)

        conf = self.bot.get_guild_config(interaction.guild.id)
        currency_symbol = conf['economy']['currency_symbol']
        await interaction.response.send_message(f"💸 You have successfully sent **{currency_symbol} {amount:,}** to {user.mention}!")


    @app_commands.command(name="deposit", description="Deposit coins into your bank account.")
    @app_commands.describe(amount="The amount to deposit or 'all'.")
    async def deposit(self, interaction: discord.Interaction, amount: str):
        bal = await self.get_balance(interaction.guild.id, interaction.user.id)
        wallet_bal = bal['wallet']
        if amount.lower() == 'all':
            dep_amount = wallet_bal
        else:
            try:
                dep_amount = int(amount)
            except ValueError:
                return await interaction.response.send_message("Please enter a valid number or 'all'.", ephemeral=True)

        if dep_amount <= 0:
            return await interaction.response.send_message("You must deposit a positive amount.", ephemeral=True)
        if dep_amount > wallet_bal:
            return await interaction.response.send_message("You don't have that much money in your wallet.", ephemeral=True)

        await self.update_balance(interaction.guild.id, interaction.user.id, wallet_change=-dep_amount, bank_change=dep_amount)
        conf = self.bot.get_guild_config(interaction.guild.id)
        currency_symbol = conf['economy']['currency_symbol']
        await interaction.response.send_message(f"🏦 You have deposited **{currency_symbol} {dep_amount:,}** into your bank.")

    @app_commands.command(name="withdraw", description="Withdraw coins from your bank account.")
    @app_commands.describe(amount="The amount to withdraw or 'all'.")
    async def withdraw(self, interaction: discord.Interaction, amount: str):
        bal = await self.get_balance(interaction.guild.id, interaction.user.id)
        bank_bal = bal['bank']
        if amount.lower() == 'all':
            wit_amount = bank_bal
        else:
            try:
                wit_amount = int(amount)
            except ValueError:
                return await interaction.response.send_message("Please enter a valid number or 'all'.", ephemeral=True)

        if wit_amount <= 0:
            return await interaction.response.send_message("You must withdraw a positive amount.", ephemeral=True)
        if wit_amount > bank_bal:
            return await interaction.response.send_message("You don't have that much money in your bank.", ephemeral=True)

        await self.update_balance(interaction.guild.id, interaction.user.id, wallet_change=wit_amount, bank_change=-wit_amount)
        conf = self.bot.get_guild_config(interaction.guild.id)
        currency_symbol = conf['economy']['currency_symbol']
        await interaction.response.send_message(f"💸 You have withdrawn **{currency_symbol} {wit_amount:,}** from your bank.")

    @app_commands.command(name="leaderboard-eco", description="Shows the server's economy leaderboard.")
    async def leaderboard_eco(self, interaction: discord.Interaction):
        await interaction.response.defer()
        query = "SELECT user_id, wallet, bank FROM economy WHERE guild_id = ? ORDER BY (wallet + bank) DESC LIMIT 10"
        results = await self.bot.db.fetchall(query, (interaction.guild.id,))
        if not results:
            return await interaction.followup.send("There is no one on the leaderboard yet!")

        conf = self.bot.get_guild_config(interaction.guild.id)
        currency_symbol = conf['economy']['currency_symbol']
        embed = discord.Embed(title=f"🏆 Economy Leaderboard for {interaction.guild.name}", color=discord.Color.gold())
        description = []
        for i, row in enumerate(results):
            user = interaction.guild.get_member(row['user_id'])
            username = user.display_name if user else f"User ID: {row['user_id']}"
            total = row['wallet'] + row['bank']
            description.append(f"**{i+1}.** {username} - **{currency_symbol} {total:,}**")
        embed.description = "\n".join(description)
        await interaction.followup.send(embed=embed)
        
    # --- Earning Commands ---
    @app_commands.command(name="daily", description="Claim your daily coins.")
    @app_commands.checks.cooldown(1, 86400, key=lambda i: (i.guild_id, i.user.id))
    async def daily(self, interaction: discord.Interaction):
        amount = random.randint(500, 1500) # Increased daily amount
        await self.update_balance(interaction.guild.id, interaction.user.id, wallet_change=amount)
        conf = self.bot.get_guild_config(interaction.guild.id)
        currency_symbol = conf['economy']['currency_symbol']
        await interaction.response.send_message(f"🎉 You claimed your daily bonus of **{currency_symbol} {amount:,}**!")

    @app_commands.command(name="work", description="Work to earn some coins.")
    @app_commands.checks.cooldown(1, 3600, key=lambda i: (i.guild_id, i.user.id))
    async def work(self, interaction: discord.Interaction):
        amount = random.randint(100, 400) # Increased work amount
        await self.update_balance(interaction.guild.id, interaction.user.id, wallet_change=amount)
        conf = self.bot.get_guild_config(interaction.guild.id)
        currency_symbol = conf['economy']['currency_symbol']
        response_template = random.choice(self.work_responses)
        await interaction.response.send_message(response_template.format(symbol=currency_symbol, amount=f"{amount:,}"))
        
    # --- Shop & Inventory Commands ---
    @app_commands.command(name="shop", description="View items available for purchase.")
    async def shop(self, interaction: discord.Interaction):
        conf = self.bot.get_guild_config(interaction.guild.id)
        currency_symbol = conf['economy']['currency_symbol']
        
        embed = discord.Embed(title="🛒 The Server Shop", description="Use `/buy <item_id>` to purchase an item.", color=discord.Color.blurple())

        # Profile Backgrounds
        if self.shop_items.get("profile_backgrounds"):
            bg_list = []
            for item in self.shop_items["profile_backgrounds"]:
                if item['price'] > 0:
                     bg_list.append(f"**{item['name']}** - `{item['id']}` | Price: **{item['price']:,} {currency_symbol}**\n*{item['description']}*")
            if bg_list:
                embed.add_field(name="🖼️ Profile Backgrounds", value="\n".join(bg_list), inline=False)
        
        # Roles
        if self.shop_items.get("roles"):
            role_list = []
            for item in self.shop_items["roles"]:
                 role_list.append(f"**{item['name']}** - `{item['id']}` | Price: **{item['price']:,} {currency_symbol}**\n*{item['description']}*")
            if role_list:
                 embed.add_field(name="✨ Purchasable Roles", value="\n".join(role_list), inline=False)

        # Special Items
        if self.shop_items.get("special_items"):
            special_list = []
            for item in self.shop_items["special_items"]:
                 special_list.append(f"**{item['name']}** - `{item['id']}` | Price: **{item['price']:,} {currency_symbol}**\n*{item['description']}*")
            if special_list:
                 embed.add_field(name="🛠️ Special Items", value="\n".join(special_list), inline=False)
                 
        if not embed.fields:
             return await interaction.response.send_message("The shop is currently empty.", ephemeral=True)

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="buy", description="Buy an item from the shop.")
    @app_commands.describe(item_id="The ID of the item to buy.")
    async def buy(self, interaction: discord.Interaction, item_id: str):
        item_id = item_id.lower()
        target_item = None
        item_category = None

        for category, items in self.shop_items.items():
            for i in items:
                if i['id'].lower() == item_id:
                    target_item = i
                    item_category = category
                    break
            if target_item:
                break
        
        if not target_item:
            return await interaction.response.send_message("That item does not exist in the shop.", ephemeral=True)

        bal = await self.get_balance(interaction.guild.id, interaction.user.id)
        if bal['wallet'] < target_item['price']:
            return await interaction.response.send_message("You don't have enough money in your wallet to buy this.", ephemeral=True)

        owned = await self.bot.db.fetchone("SELECT 1 FROM user_inventory WHERE user_id = ? AND guild_id = ? AND item_id = ?", (interaction.user.id, interaction.guild.id, item_id))
        if owned:
            return await interaction.response.send_message("You already own this item!", ephemeral=True)
            
        # Handle role purchase
        if item_category == 'roles':
            role_id = target_item.get('role_id')
            role = interaction.guild.get_role(role_id)
            if not role:
                 return await interaction.response.send_message("Error: The role for this item could not be found. Please contact a server admin.", ephemeral=True)
            if role in interaction.user.roles:
                 return await interaction.response.send_message("You already have this role!", ephemeral=True)

            await self.update_balance(interaction.guild.id, interaction.user.id, wallet_change=-target_item['price'])
            await interaction.user.add_roles(role, reason=f"Purchased from shop by {interaction.user}")
            # Add to inventory to prevent re-buying
            await self.bot.db.execute("INSERT INTO user_inventory (user_id, guild_id, item_id, item_type, quantity) VALUES (?, ?, ?, ?, ?)", (interaction.user.id, interaction.guild.id, item_id, 'role', 1))
            await interaction.response.send_message(f"👑 You have successfully purchased the **{target_item['name']}** role!")
        else: # Handle backgrounds and special items
            item_type = 'profile_background' if item_category == 'profile_backgrounds' else 'special_item'
            await self.update_balance(interaction.guild.id, interaction.user.id, wallet_change=-target_item['price'])
            await self.bot.db.execute("INSERT INTO user_inventory (user_id, guild_id, item_id, item_type, quantity) VALUES (?, ?, ?, ?, ?)", (interaction.user.id, interaction.guild.id, item_id, item_type, 1))
            await interaction.response.send_message(f"🛍️ You have successfully purchased **{target_item['name']}**!")

    @app_commands.command(name="inventory", description="View your purchased items.")
    async def inventory(self, interaction: discord.Interaction):
        items = await self.bot.db.fetchall("SELECT item_id, item_type, is_active FROM user_inventory WHERE user_id = ? AND guild_id = ?", (interaction.user.id, interaction.guild.id))
        if not items:
            return await interaction.response.send_message("Your inventory is empty. Visit the `/shop` to buy something!", ephemeral=True)

        embed = discord.Embed(title=f"🎒 {interaction.user.display_name}'s Inventory", color=interaction.user.color)
        
        bg_list = []
        role_list = []
        special_list = []

        all_shop_items = {i['id']: i for cat in self.shop_items.values() for i in cat}

        for db_item in items:
            shop_item = all_shop_items.get(db_item['item_id'])
            if not shop_item: continue
            
            item_name = shop_item['name']
            item_id = shop_item['id']

            if db_item['item_type'] == 'profile_background':
                active_str = " - **(Active)**" if db_item['is_active'] else ""
                bg_list.append(f"• **{item_name}** (`{item_id}`){active_str}")
            elif db_item['item_type'] == 'role':
                role_list.append(f"• **{item_name}** (`{item_id}`)")
            elif db_item['item_type'] == 'special_item':
                special_list.append(f"• **{item_name}** (`{item_id}`)")
        
        if bg_list:
            embed.add_field(name="🖼️ Backgrounds", value="\n".join(bg_list) + "\n\n*Use `/set-background <id>` to equip.*", inline=False)
        if role_list:
            embed.add_field(name="✨ Roles", value="\n".join(role_list), inline=False)
        if special_list:
            embed.add_field(name="🛠️ Special Items", value="\n".join(special_list), inline=False)

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="set-background", description="Set your active profile background.")
    @app_commands.describe(item_id="The ID of the background from your inventory.")
    async def set_background(self, interaction: discord.Interaction, item_id: str):
        item_id = item_id.lower()
        owned = await self.bot.db.fetchone("SELECT 1 FROM user_inventory WHERE user_id = ? AND guild_id = ? AND item_id = ? AND item_type = 'profile_background'", (interaction.user.id, interaction.guild.id, item_id))
        if not owned:
            return await interaction.response.send_message("You do not own this background. Check your `/inventory`.", ephemeral=True)

        # Deactivate all other backgrounds first
        await self.bot.db.execute("UPDATE user_inventory SET is_active = 0 WHERE user_id = ? AND guild_id = ? AND item_type = 'profile_background'", (interaction.user.id, interaction.guild.id))
        # Activate the chosen one
        await self.bot.db.execute("UPDATE user_inventory SET is_active = 1 WHERE user_id = ? AND guild_id = ? AND item_id = ?", (interaction.user.id, interaction.guild.id, item_id))

        item = next((i for i in self.shop_items.get("profile_backgrounds", []) if i['id'] == item_id), None)
        item_name = item['name'] if item else item_id
        await interaction.response.send_message(f"🖼️ Your profile background has been set to **{item_name}**!")
        
    # --- Gambling Commands ---
    @app_commands.command(name="slots", description="Play the slot machine.")
    @app_commands.checks.cooldown(1, 5, key=lambda i: (i.guild_id, i.user.id))
    @app_commands.describe(bet="The amount you want to bet.")
    async def slots(self, interaction: discord.Interaction, bet: app_commands.Range[int, 1, 10000]):
        bal = await self.get_balance(interaction.guild.id, interaction.user.id)
        if bet > bal['wallet']:
            return await interaction.response.send_message("You don't have enough money in your wallet to place that bet.", ephemeral=True)

        await self.update_balance(interaction.guild.id, interaction.user.id, wallet_change=-bet)

        emojis = ["🍒", "🍇", "🍊", "🍋", "🔔", "💎", "🍀"]
        reels = [random.choice(emojis) for _ in range(3)]
        result_str = " | ".join(reels)

        winnings = 0
        if reels[0] == reels[1] == reels[2]:
            winnings = bet * 10
        elif reels[0] == reels[1] or reels[1] == reels[2]:
            winnings = bet * 3

        embed = discord.Embed(title="🎰 Slot Machine 🎰", color=discord.Color.gold())
        embed.add_field(name="Result", value=f"**[ {result_str} ]**", inline=False)

        if winnings > 0:
            await self.update_balance(interaction.guild.id, interaction.user.id, wallet_change=winnings)
            embed.description = f"🎉 Congratulations! You won **{winnings:,}** coins!"
            embed.color = discord.Color.green()
        else:
            embed.description = "Better luck next time!"
            embed.color = discord.Color.red()

        new_bal = await self.get_balance(interaction.guild.id, interaction.user.id)
        embed.set_footer(text=f"Your new balance: {new_bal['wallet']:,}")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="flip", description="Bet on a coin flip.")
    @app_commands.checks.cooldown(1, 5, key=lambda i: (i.guild_id, i.user.id))
    @app_commands.describe(bet="The amount to bet.", choice="Your choice: heads or tails.")
    @app_commands.choices(choice=[
        app_commands.Choice(name="Heads", value="heads"),
        app_commands.Choice(name="Tails", value="tails")
    ])
    async def flip(self, interaction: discord.Interaction, bet: app_commands.Range[int, 1, 25000], choice: app_commands.Choice[str]):
        bal = await self.get_balance(interaction.guild.id, interaction.user.id)
        if bet > bal['wallet']:
            return await interaction.response.send_message("You don't have enough money in your wallet for that bet.", ephemeral=True)

        result = random.choice(["heads", "tails"])
        
        if result == choice.value:
            winnings = bet * 2
            await self.update_balance(interaction.guild.id, interaction.user.id, wallet_change=bet) # Win bet back + winnings
            await interaction.response.send_message(f"🪙 The coin landed on **{result.title()}**. You won **{bet:,}** coins!")
        else:
            await self.update_balance(interaction.guild.id, interaction.user.id, wallet_change=-bet)
            await interaction.response.send_message(f"🪙 The coin landed on **{result.title()}**. You lost **{bet:,}** coins.")

    @app_commands.command(name="blackjack", description="Play a game of blackjack.")
    @app_commands.checks.cooldown(1, 15, key=lambda i: (i.guild_id, i.user.id))
    @app_commands.describe(bet="The amount you want to bet.")
    async def blackjack(self, interaction: discord.Interaction, bet: app_commands.Range[int, 10, 50000]):
        bal = await self.get_balance(interaction.guild.id, interaction.user.id)
        if bet > bal['wallet']:
            return await interaction.response.send_message("You don't have enough money in your wallet for that bet.", ephemeral=True)
            
        await self.update_balance(interaction.guild.id, interaction.user.id, wallet_change=-bet)
        
        game = BlackjackGame()
        game.deal_initial()
        
        player_score = game._calculate_value(game.player_hand)

        view = BlackjackView(game, self, interaction, bet)

        embed = discord.Embed(title=f"🃏 Blackjack | Bet: {bet:,}", color=discord.Color.blue())
        embed.add_field(name=f"Your Hand ({player_score})", value=game.hand_to_string(game.player_hand), inline=False)
        embed.add_field(name=f"Dealer's Hand ({game._calculate_value([game.dealer_hand[0]])})", value=game.hand_to_string(game.dealer_hand, hide_dealer_card=True), inline=False)

        if player_score == 21: # Natural Blackjack
            winnings = int(bet * 2.5)
            await self.update_balance(interaction.guild.id, interaction.user.id, wallet_change=winnings)
            embed.description = f"BLACKJACK! You won **{winnings:,}** coins!"
            embed.color=discord.Color.gold()
            return await interaction.response.send_message(embed=embed)
            
        await interaction.response.send_message(embed=embed, view=view)


    @app_commands.command(name="rob", description="Attempt to rob another user.")
    @app_commands.checks.cooldown(1, 3600, key=lambda i: (i.guild_id, i.user.id))
    @app_commands.describe(user="The user you want to rob.")
    async def rob(self, interaction: discord.Interaction, user: discord.Member):
        if user.id == interaction.user.id:
            return await interaction.response.send_message("You can't rob yourself!", ephemeral=True)
        if user.bot:
            return await interaction.response.send_message("You can't rob bots, they have nothing to steal!", ephemeral=True)

        robber_bal = await self.get_balance(interaction.guild.id, interaction.user.id)
        if robber_bal['wallet'] < 250:
            return await interaction.response.send_message("You need at least 250 coins in your wallet to attempt a robbery.", ephemeral=True)

        target_bal = await self.get_balance(interaction.guild.id, user.id)
        if target_bal['wallet'] < 100:
            return await interaction.response.send_message(f"{user.display_name} is too poor to rob.", ephemeral=True)
        
        # Check for Robber's Mask
        success_chance = 3 # 1 in 3 chance
        has_mask = await self.has_item(interaction.guild.id, interaction.user.id, 'robbers_mask')
        if has_mask:
            success_chance = 2 # 1 in 2 chance (50%)
            await self.bot.db.execute("DELETE FROM user_inventory WHERE user_id = ? AND guild_id = ? AND item_id = ?", (interaction.user.id, interaction.guild.id, 'robbers_mask'))
            
        if random.randint(1, success_chance) == 1:
            amount_stolen = random.randint(1, int(target_bal['wallet'] * 0.4)) # Can steal up to 40%
            await self.update_balance(interaction.guild.id, interaction.user.id, wallet_change=amount_stolen)
            await self.update_balance(interaction.guild.id, user.id, wallet_change=-amount_stolen)
            msg = f"💰 Success! You robbed **{amount_stolen:,}** coins from {user.mention}!"
            if has_mask:
                msg += "\n*Your Robber's Mask broke in the process.*"
            await interaction.response.send_message(msg)
        else:
            fine = random.randint(50, 250)
            fine = min(fine, robber_bal['wallet']) # Can't pay more than you have
            await self.update_balance(interaction.guild.id, interaction.user.id, wallet_change=-fine)
            msg = f"👮‍♂️ You were caught! You paid a fine of **{fine:,}** coins."
            if has_mask:
                msg += "\n*Your Robber's Mask broke in the process.*"
            await interaction.response.send_message(msg)


async def setup(bot: MaxyBot):
    await bot.add_cog(Economy(bot))