# MaxyBot

A Simple, Open-source, and good Discord bot.

---

## 📝 Description

MaxyBot is a fully-featured Discord bot built with **discord.py**.  
It provides a modular cog-based structure with more than 24+ cogs, supporting:

- Moderation (mute, kick, ban, logging)
- Automoderation (anti-spam, anti-link, bad words)
- Economy system with coins and leveling
- Ticket management
- Welcome & Goodbye messages with embeds
- AutoResponder
- Starboard
- Cooldown management per command & per user
- Secure encryption for sensitive data using AES-GCM

The bot is designed to be **scalable, secure, and easily configurable** for multiple guilds.

---

## ⚙️ Features

- Cog-based modular design (24+ cogs in `cogs/`)
- Slash commands and prefix commands
- Per-guild configuration system
- Automatic configuration saving
- Graceful shutdown & signal handling
- Logging with daily rotating files
- Health check for DB & HTTP
- CooldownManager for precise command rate limiting
- AutoResponder caching
- Owner-only commands: shutdown, sync, clear commands

---

## 🛠 Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/omar9devx/maxybot.git
   cd maxybot
