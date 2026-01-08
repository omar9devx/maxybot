# 24+ Cogs in cogs/ !
# bot.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union, Literal

import aiofiles
import aiohttp
import discord
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv, set_key

# --------------------------------------------------------------------------- #
#                               CONSTANTS & PATHS                             #
# --------------------------------------------------------------------------- #

OWNER_IDS = {1279500219154956419}
DEV_GUILD_ID = 1400861301357678613
STATUS_CHANNEL_ID = 1410018649778950294
DEFAULT_PREFIX = "m!"

DATA_DIR = Path("data")
DATA_DIR.mkdir(parents=True, exist_ok=True)

ENV_PATH = Path(".env")

# --------------------------------------------------------------------------- #
#                                    LOGGING                                  #
# --------------------------------------------------------------------------- #

LOG_FORMAT = "%(asctime)s - %(levelname)s - [%(name)s] %(message)s"
LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"


def _setup_logging() -> logging.Logger:
    logger = logging.getLogger("MaxyBot")
    logger.setLevel(logging.INFO)

    # Avoid adding duplicate handlers if module reloaded
    if logger.handlers:
        return logger

    formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATEFMT)

    # Console handler
    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    # Daily rotating file (one per day, keep 7 days)
    log_dir = DATA_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    daily_log_path = log_dir / "maxybot.log"

    try:
        th = TimedRotatingFileHandler(
            daily_log_path,
            when="midnight",
            backupCount=7,
            encoding="utf-8",
            utc=True,
        )
        th.setFormatter(formatter)
        logger.addHandler(th)
    except Exception:
        # Fallback: size-based rotation
        fh = RotatingFileHandler(
            daily_log_path,
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        fh.setFormatter(formatter)
        logger.addHandler(fh)

    return logger


logger = _setup_logging()

# --------------------------------------------------------------------------- #
#                               ENV & DATABASE                                #
# --------------------------------------------------------------------------- #

load_dotenv()

# Database Manager fallback
try:
    from utils.database import DatabaseManager
except ImportError:
    class DatabaseManager:
        """Fallback dummy database manager (for development)."""

        def __init__(self, db_path: Path):
            self.db_path = db_path
            self.logger = logging.getLogger("DatabaseManager")
            self.logger.warning(f"Using dummy DatabaseManager for {db_path}.")

        async def close(self):
            self.logger.info("Dummy DB closed.")

        async def ping(self) -> bool:
            await asyncio.sleep(0.001)
            return True


# --------------------------------------------------------------------------- #
#                                 ENCRYPTION                                  #
# --------------------------------------------------------------------------- #

ENCRYPTION_KEY: Optional[bytes] = None


def setup_encryption_key() -> None:
    """
    Load or generate a 32-byte AES-GCM key and store it in .env as ENCRYPTION_KEY.

    - Uses URL-safe Base64 without padding in .env.
    - Regenerates key if invalid or wrong size.
    """
    global ENCRYPTION_KEY

    # Make sure .env exists so set_key won't fail on new environments
    if not ENV_PATH.exists():
        ENV_PATH.touch()

    key_str = os.getenv("ENCRYPTION_KEY")

    if key_str:
        try:
            padding = "=" * (-len(key_str) % 4)
            decoded_key = base64.urlsafe_b64decode(key_str + padding)
            if len(decoded_key) == 32:
                ENCRYPTION_KEY = decoded_key
                logger.info("Successfully loaded ENCRYPTION_KEY from .env file.")
                return
            else:
                logger.warning(
                    "ENCRYPTION_KEY in .env is not 32 bytes. A new key will be generated."
                )
        except (ValueError, TypeError):
            logger.warning(
                "ENCRYPTION_KEY in .env is invalid Base64. A new key will be generated."
            )

    logger.info("Generating a new ENCRYPTION_KEY and saving it to .env file...")
    new_key = os.urandom(32)
    key_str_to_save = base64.urlsafe_b64encode(new_key).decode("utf-8").rstrip("=")

    try:
        set_key(str(ENV_PATH), "ENCRYPTION_KEY", key_str_to_save)
        ENCRYPTION_KEY = new_key
        logger.info("Successfully generated and saved a new ENCRYPTION_KEY.")
    except Exception as e:
        logger.critical(f"FATAL: Could not write ENCRYPTION_KEY to .env file: {e}")
        sys.exit(1)


def encrypt_secret(secret: str) -> str:
    """Encrypt a string using AES-GCM with the global ENCRYPTION_KEY."""
    if not ENCRYPTION_KEY:
        raise ValueError("Encryption key is not set.")

    aesgcm = AESGCM(ENCRYPTION_KEY)
    nonce = os.urandom(12)  # 12 bytes is standard for AES-GCM nonce
    encrypted_data = aesgcm.encrypt(nonce, secret.encode("utf-8"), None)
    return base64.urlsafe_b64encode(nonce + encrypted_data).decode("utf-8").rstrip("=")


def decrypt_secret(enc_secret: str) -> str:
    """Decrypt a string using AES-GCM, with strong validation and error handling."""
    if not ENCRYPTION_KEY:
        raise ValueError("Encryption key is not set.")

    try:
        padding = "=" * (-len(enc_secret) % 4)
        data = base64.urlsafe_b64decode(enc_secret + padding)
        if len(data) < 28:  # 12 nonce + 16 tag at minimum
            raise ValueError("Encrypted data too short (>=28 bytes required).")

        nonce, ciphertext = data[:12], data[12:]
        aesgcm = AESGCM(ENCRYPTION_KEY)
        return aesgcm.decrypt(nonce, ciphertext, None).decode("utf-8")

    except InvalidTag:
        logger.error(
            "Decryption failed: Data was tampered with or key is wrong.", exc_info=False
        )
        raise ValueError("Invalid decryption key or corrupted data.")
    except (ValueError, TypeError) as e:
        logger.error(
            f"Decryption failed due to data format or length: {e}", exc_info=False
        )
        raise ValueError("Invalid data format for decryption.")
    except Exception as e:
        logger.exception(f"An unexpected error occurred during decryption: {e}")
        raise ValueError("An unexpected decryption error occurred.")


# Initialize encryption key at import time
setup_encryption_key()

# --------------------------------------------------------------------------- #
#                            DEFAULT GUILD CONFIG                             #
# --------------------------------------------------------------------------- #


def get_default_config() -> Dict[str, Any]:
    """
    Return a fresh default config for a guild.

    Always returns a NEW dict (no shared references between guilds).
    """
    return {
        "prefix": DEFAULT_PREFIX,
        "welcome": {
            "enabled": False,
            "channel_id": None,
            "message": "Welcome {user.mention} to {guild.name}!",
            "embed": {
                "enabled": True,
                "title": "New Member!",
                "description": "We're glad to have you.",
            },
        },
        "goodbye": {
            "enabled": False,
            "channel_id": None,
            "message": "Goodbye {user.name}!",
            "embed": {
                "enabled": True,
                "title": "Member Left",
                "description": "We'll miss them.",
            },
        },
        "logging": {
            "enabled": False,
            "channel_id": None,
            "events": {
                "message_delete": True,
                "message_edit": True,
                "member_join": True,
                "member_leave": True,
                "member_update": True,
                "role_update": True,
                "channel_update": True,
                "voice_update": True,
            },
        },
        "moderation": {
            "mute_role_id": None,
            "mod_log_channel_id": None,
            "allowed_roles": [],
        },
        "automod": {
            "enabled": True,
            "anti_link": False,
            "anti_invite": False,
            "anti_spam": False,
            "bad_words_enabled": False,
            "bad_words_list": [],
        },
        "leveling": {
            "enabled": True,
            "levelup_message": "🎉 Congrats {user.mention}, you reached **Level {level}**!",
            "xp_per_message_min": 15,
            "xp_per_message_max": 25,
            "xp_cooldown_seconds": 60,
        },
        "economy": {
            "enabled": True,
            "start_balance": 100,
            "currency_symbol": "🪙",
            "currency_name": "Maxy Coin",
        },
        "tickets": {
            "enabled": False,
            "category_id": None,
            "support_role_id": None,
            "transcript_channel_id": None,
            "panel_channel_id": None,
        },
        "autorole": {
            "enabled": False,
            "human_role_id": None,
            "bot_role_id": None,
        },
        "starboard": {"enabled": False, "channel_id": None, "star_count": 5},
        "autoresponder": {"enabled": True},
        "disabled_commands": [],
    }


# --------------------------------------------------------------------------- #
#                                    VIEWS                                    #
# --------------------------------------------------------------------------- #

class BaseConfirmView(discord.ui.View):
    """Base confirmation view that restricts interactions to a specific user."""

    def __init__(self, author_id: int, timeout: float = 30.0):
        super().__init__(timeout=timeout)
        self.value: Optional[bool] = None
        self.author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            try:
                await interaction.response.send_message(
                    "❌ This confirmation is not for you.",
                    ephemeral=True,
                )
            except discord.InteractionResponded:
                await interaction.followup.send(
                    "❌ This confirmation is not for you.",
                    ephemeral=True,
                )
            except Exception:
                pass
            return False
        return True

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, row=1)
    async def cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.value = False
        await interaction.response.defer()
        self.stop()


class ShutdownConfirmView(BaseConfirmView):
    """Confirmation view specifically for shutting down the bot."""

    @discord.ui.button(
        label="Confirm Shutdown", style=discord.ButtonStyle.danger, row=0
    )
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.value = True
        await interaction.response.defer()
        self.stop()


class SyncConfirmView(BaseConfirmView):
    """
    Confirmation view for syncing/clearing application commands.
    Dynamically defines the confirm button based on the requested action.
    """

    def __init__(self, author_id: int, *, is_clearing: bool = False):
        super().__init__(author_id)
        confirm_label = "Confirm Clear" if is_clearing else "Confirm Sync"
        confirm_style = (
            discord.ButtonStyle.danger if is_clearing else discord.ButtonStyle.primary
        )

        confirm_button = discord.ui.Button(
            label=confirm_label, style=confirm_style, row=0
        )
        confirm_button.callback = self._confirm_callback  # type: ignore
        self.add_item(confirm_button)

    async def _confirm_callback(self, interaction: discord.Interaction) -> None:
        self.value = True
        await interaction.response.defer()
        self.stop()


# --------------------------------------------------------------------------- #
#                               COOLDOWN MANAGER                              #
# --------------------------------------------------------------------------- #

class CooldownManager:
    """
    Token-bucket style cooldown per user per command.

    - Thread-safe using asyncio.Lock.
    - Configurable global cooldown plus per-command overrides.
    """

    def __init__(self, default_rate: int = 1, default_per: float = 5.0):
        self._data: Dict[int, Dict[str, List[float]]] = {}
        self.default_rate = default_rate
        self.default_per = default_per
        self.config: Dict[str, Dict[str, float]] = {
            "global": {"rate": float(default_rate), "per": default_per}
        }
        self._lock = asyncio.Lock()

    def set_command_cooldown(self, command_name: str, rate: int, per: float) -> None:
        """Set or update a specific command's cooldown configuration."""
        self.config[command_name.lower()] = {"rate": float(rate), "per": float(per)}

    def get_config(self, command_name: str) -> Tuple[int, float]:
        """Get (rate, per) config for a command (falling back to global)."""
        command_name = command_name.lower()
        cfg = self.config.get(command_name) or self.config["global"]
        rate = int(cfg.get("rate", self.default_rate))
        per = float(cfg.get("per", self.default_per))
        return rate, per

    async def acquire(self, user_id: int, command_name: str) -> float:
        """
        Try to consume a token.

        Returns:
            0.0 if allowed immediately,
            otherwise the remaining seconds until a token is available.
        """
        command_name = command_name.lower()
        rate, per = self.get_config(command_name)
        now = time.time()

        async with self._lock:
            user_rec = self._data.setdefault(user_id, {})
            timestamps = user_rec.setdefault(command_name, [])

            cutoff = now - per
            timestamps[:] = [t for t in timestamps if t > cutoff]

            if len(timestamps) < rate:
                timestamps.append(now)
                return 0.0

            retry_after = per - (now - timestamps[0])
            return max(0.0, retry_after)

    async def remaining(self, user_id: int, command_name: str) -> float:
        """
        Get the remaining cooldown in seconds (0.0 if command is free to use).
        """
        command_name = command_name.lower()
        _, per = self.get_config(command_name)
        now = time.time()

        async with self._lock:
            user_rec = self._data.get(user_id, {})
            timestamps = user_rec.get(command_name, [])
            if not timestamps:
                return 0.0

            cutoff = now - per
            timestamps[:] = [t for t in timestamps if t > cutoff]
            if len(timestamps) < self.config.get(command_name, self.config["global"]).get(
                "rate", self.default_rate
            ):
                return 0.0

            return per - (now - timestamps[0])


# --------------------------------------------------------------------------- #
#                                 MAIN BOT CLASS                              #
# --------------------------------------------------------------------------- #

class MaxyBot(commands.Bot):
    CommandPrefix = Union[List[str], Tuple[str, ...], str]

    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        intents.presences = False

        self.root_path = Path.cwd()
        self.data_path = self.root_path / "data"
        self.config_path = self.data_path / "config.json"
        self.data_path.mkdir(exist_ok=True)

        # Resources
        self.db = DatabaseManager(self.data_path / "maxy.db")
        self.http_session: Optional[aiohttp.ClientSession] = None
        self.cooldowns = CooldownManager(default_rate=1, default_per=5.0)

        super().__init__(
            command_prefix=self.get_prefix_wrapper,
            intents=intents,
            case_insensitive=True,
            owner_ids=OWNER_IDS,
            help_command=None,
        )

        self.start_time = datetime.now(timezone.utc)

        # Configuration caches
        # config_cache: guild_id (int) -> effective config dict
        self.config_cache: Dict[int, Dict[str, Any]] = {}
        # config_cache_from_file: guild_id (str) -> settings_dict (raw from file)
        self.config_cache_from_file: Dict[str, Any] = {}
        self._config_lock = asyncio.Lock()

        self.logger = logger

        # Cache for AutoResponder cog (optional)
        self.autoresponder_cog: Optional[commands.Cog] = None

        # Register global before_invoke hook for prefix commands cooldown
        @self.before_invoke
        async def _global_before_invoke(ctx: commands.Context) -> None:  # type: ignore[no-redef]
            # Skip for application (slash) invocations – those are handled by app_commands system.
            if getattr(ctx, "interaction", None):
                return
            cmd = ctx.command
            cmd_name = cmd.qualified_name.lower() if cmd else "unknown"
            remaining = await self.cooldowns.acquire(ctx.author.id, cmd_name)
            if remaining > 0:
                rate, per = self.cooldowns.get_config(cmd_name)
                cooldown = commands.Cooldown(rate, per)
                # This will be caught by on_command_error
                raise commands.CommandOnCooldown(cooldown, remaining)

    # ------------------------------- PROPERTIES ------------------------------ #

    @property
    def config_data(self) -> Dict[str, Any]:
        """Provides raw config data from file/memory (read-only snapshot)."""
        return self.config_cache_from_file

    # ------------------------------- SETUP HOOK ------------------------------ #

    async def setup_hook(self) -> None:
        """
        Called by discord.py after login but before on_ready.

        Ideal place to start background tasks, load cogs, and set up long-lived
        resources.
        """
        self.logger.info("Running setup_hook...")

        # Single shared aiohttp session
        self.http_session = aiohttp.ClientSession()

        await self.load_config()

        # Owner cog early
        try:
            await self.add_cog(OwnerCog(self))
        except Exception:
            self.logger.exception("Failed to load OwnerCog")

        await self._load_all_cogs()

        # Cache AutoResponder reference (if present)
        self.autoresponder_cog = self.get_cog("AutoResponder")

        # Global cooldown for ALL slash commands using CooldownManager
        async def _app_cmd_cooldown(interaction: discord.Interaction) -> bool:
            # Ignore bots / webhooks
            if not interaction.user or interaction.user.bot:
                return True

            cmd = interaction.command
            cmd_name = cmd.qualified_name.lower() if cmd else "unknown"

            remaining = await self.cooldowns.acquire(interaction.user.id, cmd_name)
            if remaining > 0:
                rate, per = self.cooldowns.get_config(cmd_name)
                cooldown = app_commands.Cooldown(rate, per)

                self.logger.info(
                    f"Cooldown blocked slash command '{cmd_name}' from "
                    f"{interaction.user} ({remaining:.1f}s left)"
                )

                # This will be handled by on_tree_error
                raise app_commands.CommandOnCooldown(cooldown, remaining)
            return True

        # Attach the global check to the app command tree
        self.tree.interaction_check = _app_cmd_cooldown

        # Start background tasks
        self.health_check.start()
        self.auto_save_config.start()

        self.logger.info(
            "setup_hook completed successfully. Use the 'sync' command to manage slash commands."
        )

    # ------------------------------- COG LOADING ----------------------------- #

    async def _load_all_cogs(self) -> None:
        """Discover and load cogs from the 'cogs' directory."""
        self.logger.info("--- Loading Cogs ---")
        cog_dir = self.root_path / "cogs"

        loaded_cogs: List[str] = []
        failed_cogs: List[str] = []

        if not cog_dir.exists():
            self.logger.warning(
                f"Cog directory '{cog_dir.relative_to(self.root_path)}' does not exist. Skipping cog loading."
            )
            return

        for item in sorted(cog_dir.iterdir()):
            if item.is_file() and item.suffix == ".py" and not item.name.startswith("_"):
                cog_name = f"cogs.{item.stem}"
                try:
                    await self.load_extension(cog_name)
                    loaded_cogs.append(cog_name)
                except Exception:
                    failed_cogs.append(cog_name)
                    self.logger.exception(f"Failed to load Cog: {cog_name}")

        self.logger.info(f"✅ Loaded {len(loaded_cogs)} cogs.")
        if failed_cogs:
            self.logger.warning(
                f"❌ Failed to load {len(failed_cogs)} cogs: {failed_cogs}"
            )
        self.logger.info("--------------------")

    # ----------------------------- CLEAN SHUTDOWN ---------------------------- #

    async def close(self) -> None:
        """Safely close all resources and shut down the bot."""
        self.logger.info("Closing bot resources...")

        # 1) Cancel background loops
        for loop_task in (self.health_check, self.auto_save_config):
            try:
                loop_task.cancel()
            except Exception:
                pass

        # 2) Wait for loops to actually cancel
        try:
            await asyncio.gather(
                *(t for t in (self.health_check, self.auto_save_config) if t is not None),
                return_exceptions=True,
            )
        except Exception:
            pass

        # 3) Save configuration one last time
        await self.save_config()

        # 4) Close HTTP session
        if self.http_session and not self.http_session.closed:
            try:
                await self.http_session.close()
            except Exception as e:
                self.logger.warning(f"HTTP session close error: {e}")

        # 5) Close database connection
        try:
            await self.db.close()
        except Exception as e:
            self.logger.error(f"Error closing database connection: {e}")

        # 6) Close Discord connection
        await super().close()
        self.logger.info("Bot has been shut down.")

    # ----------------------------- CONFIG HANDLING --------------------------- #

    async def load_config(self) -> None:
        """Load guild config from JSON file into memory, protected by a lock."""
        async with self._config_lock:
            try:
                if not self.config_path.exists():
                    raise FileNotFoundError

                async with aiofiles.open(
                    self.config_path, "r", encoding="utf-8"
                ) as f:
                    content = await f.read()
                    data = json.loads(content)
                    self.config_cache_from_file = data.get("guild_settings", {})
                    self.logger.info("Configuration loaded successfully from config.json.")
            except FileNotFoundError:
                self.logger.warning(
                    "config.json not found. Starting with an empty config and defaults."
                )
                self.config_cache_from_file = {}
            except json.JSONDecodeError:
                self.logger.error(
                    "config.json is invalid JSON. Starting with an empty config and defaults."
                )
                self.config_cache_from_file = {}
            except Exception as e:
                self.logger.exception(
                    f"An unexpected error occurred during config load: {e}"
                )
                self.config_cache_from_file = {}

    async def save_config(self) -> None:
        """Save raw configuration to disk, protected by a lock (atomic write)."""
        async with self._config_lock:
            try:
                full_config = {"guild_settings": self.config_cache_from_file}
                temp_path = self.config_path.with_suffix(
                    f"{self.config_path.suffix}.tmp"
                )

                async with aiofiles.open(temp_path, "w", encoding="utf-8") as f:
                    await f.write(
                        json.dumps(
                            full_config,
                            indent=4,
                            ensure_ascii=False,
                        )
                    )

                os.replace(temp_path, self.config_path)
                self.config_cache.clear()
                self.logger.info("Configuration saved successfully to config.json.")
            except Exception as e:
                self.logger.exception(f"Failed to save config.json: {e}")

    def get_guild_config(self, guild_id: int) -> Dict[str, Any]:
        """
        Get the effective configuration for a guild (defaults + overrides).

        Uses an in-memory cache for performance.
        """
        # Fast path: cached
        if guild_id in self.config_cache:
            return self.config_cache[guild_id]

        guild_id_str = str(guild_id)
        final_config = get_default_config()
        saved_settings = self.config_cache_from_file.get(guild_id_str, {})

        def _recursive_update(d: Dict[str, Any], u: Dict[str, Any]) -> Dict[str, Any]:
            """Recursively update dictionary d with values from u."""
            for k, v in u.items():
                if isinstance(v, dict) and isinstance(d.get(k), dict):
                    d[k] = _recursive_update(d[k], v)
                else:
                    d[k] = v
            return d

        final_config = _recursive_update(final_config, saved_settings)
        self.config_cache[guild_id] = final_config
        return final_config

    def set_guild_config(self, guild_id: int, key_path: List[str], value: Any) -> None:
        """
        Update a configuration value by key path.

        Example:
            set_guild_config(123, ["welcome", "enabled"], True)
        """
        guild_id_str = str(guild_id)

        if guild_id_str not in self.config_cache_from_file:
            self.config_cache_from_file[guild_id_str] = {}

        current_level: Dict[str, Any] = self.config_cache_from_file[guild_id_str]
        for key in key_path[:-1]:
            nested = current_level.setdefault(key, {})
            if not isinstance(nested, dict):
                raise ValueError(
                    f"Cannot set key path: '{key}' is not a dictionary in the config structure."
                )
            current_level = nested  # type: ignore[assignment]

        current_level[key_path[-1]] = value

        # Invalidate effective config cache for this guild
        if guild_id in self.config_cache:
            del self.config_cache[guild_id]

        self.logger.info(
            f"Config for guild {guild_id} updated: {'->'.join(key_path)} = {value}. Will auto-save."
        )

    # ------------------------------- PREFIX LOGIC ---------------------------- #

    async def get_prefix_wrapper(
        self, bot: commands.Bot, message: discord.Message
    ) -> CommandPrefix:
        """Dynamically retrieve prefix, falling back to mention and default."""
        if message.guild:
            conf = self.get_guild_config(message.guild.id)
            prefix = conf.get("prefix", DEFAULT_PREFIX)
        else:
            prefix = DEFAULT_PREFIX

        if isinstance(prefix, str):
            prefix_list: List[str] = [prefix]
        else:
            prefix_list = list(prefix)

        return commands.when_mentioned_or(*prefix_list)(bot, message)

    # ------------------------------- LIFECYCLE ------------------------------- #

    async def on_ready(self) -> None:
        """Called when the bot is fully ready and connected."""
        if not hasattr(self, "_run_once_on_ready"):
            self._run_once_on_ready = True

            self.logger.info("=" * 40)
            self.logger.info(f"Bot Logged In as: {self.user} | {self.user.id}")
            self.logger.info(f"Discord.py Version: {discord.__version__}")
            self.logger.info(f"Serving {len(self.guilds)} guilds.")
            self.logger.info("MaxyBot is online and operational.")
            self.logger.info("=" * 40)

            await self.send_status_message(
                title="✅ System Status: Online",
                description="Maxy Bot is now online and fully operational.",
                color=discord.Color.green(),
            )

            activity = discord.Game(name=f"/help | {DEFAULT_PREFIX}help")
            await self.change_presence(activity=activity, status=discord.Status.idle)
        else:
            self.logger.info("Bot reconnected.")

    # --------------------------- MESSAGE HANDLING ---------------------------- #

    async def on_message(self, message: discord.Message) -> None:
        """
        Handle incoming messages.

        - Runs AutoResponder (if available).
        - Processes prefix commands.
        """
        if message.author.bot:
            return

        if message.guild is None:
            # You can allow DM commands here if you want:
            # await self.process_commands(message)
            return

        # 1) AutoResponder (optional)
        if self.autoresponder_cog:
            handler = getattr(self.autoresponder_cog, "handle_responses", None)
            if callable(handler):
                try:
                    handled = await handler(message)
                    if handled:
                        return
                except Exception:
                    self.logger.exception("Error in AutoResponder.handle_responses")

        # 2) Prefix commands
        await self.process_commands(message)

    # ------------------------------- ERROR HANDLERS -------------------------- #

    async def on_command_error(
        self, ctx: commands.Context, error: commands.CommandError
    ) -> None:
        """Handle errors raised by prefix commands."""
        # Unwrap CommandOnCooldown if wrapped inside CommandInvokeError
        if isinstance(error, commands.CommandInvokeError) and isinstance(
            error.original, commands.CommandOnCooldown
        ):
            error = error.original  # type: ignore[assignment]

        if isinstance(error, commands.CommandNotFound):
            # silently ignore unknown commands
            return

        send_msg: Optional[str] = None

        if isinstance(error, commands.MissingPermissions):
            send_msg = (
                "❌ You don't have the required permissions: "
                f"`{', '.join(error.missing_permissions)}`."
            )
        elif isinstance(error, commands.BotMissingPermissions):
            send_msg = (
                "🚫 I don't have the necessary permissions: "
                f"`{', '.join(error.missing_permissions)}`."
            )
        elif isinstance(error, commands.CommandOnCooldown):
            send_msg = (
                "⏳ This command is on cooldown. "
                f"Please try again in **{error.retry_after:.1f}** seconds."
            )
        elif isinstance(error, commands.MissingRequiredArgument):
            usage = (
                f"{ctx.prefix}{ctx.command.qualified_name} {ctx.command.signature}"
                if ctx.command
                else "N/A"
            )
            send_msg = (
                f"Missing a required argument: `{error.param.name}`. "
                f"Usage: `{usage}`"
            )
        elif isinstance(error, commands.BadArgument):
            send_msg = f"Invalid argument: {error}"
        else:
            self.logger.exception(
                f"Unhandled prefix command error in "
                f"'{ctx.command.qualified_name if ctx.command else 'Unknown'}': {error}"
            )
            send_msg = "An unexpected error occurred. The developers have been notified."

        if send_msg:
            try:
                # ⚠️ Note: ephemeral is only valid with interactions / hybrid commands (ctx.interaction)
                if getattr(ctx, "interaction", None):
                    await ctx.send(send_msg, ephemeral=True)  # type: ignore[arg-type]
                else:
                    await ctx.send(send_msg)
            except discord.Forbidden:
                self.logger.warning(
                    "Failed to send error message due to missing permissions "
                    f"(guild={getattr(ctx.guild, 'id', 'N/A')}, "
                    f"channel={getattr(ctx.channel, 'id', 'N/A')})."
                )
            except Exception:
                pass

    async def on_tree_error(
        self,
        interaction: discord.Interaction,
        error: discord.app_commands.AppCommandError,
    ) -> None:
        """Handle errors raised by application (slash) commands."""
        original_error = getattr(error, "original", error)

        try:
            if interaction.response.is_done():
                send_func = interaction.followup.send
            else:
                send_func = interaction.response.send_message
        except Exception:
            self.logger.error(
                f"Failed to prepare interaction response for error: {error}",
                exc_info=True,
            )
            return

        send_msg: Optional[str] = None

        try:
            if isinstance(original_error, app_commands.CommandOnCooldown):
                send_msg = (
                    "⏳ This command is on cooldown. "
                    f"Try again in **{original_error.retry_after:.1f}s**."
                )
            elif isinstance(original_error, app_commands.MissingPermissions):
                send_msg = (
                    "❌ You lack the permissions: "
                    f"`{', '.join(original_error.missing_permissions)}`."
                )
            elif isinstance(original_error, app_commands.BotMissingPermissions):
                send_msg = (
                    "🚫 I don't have the required permissions: "
                    f"`{', '.join(original_error.missing_permissions)}`."
                )
            else:
                self.logger.exception(
                    f"Unhandled slash command error for "
                    f"'{interaction.command.name if interaction.command else 'Unknown'}': "
                    f"{original_error}"
                )
                send_msg = "An unexpected error occurred. This has been reported."

            if send_msg:
                await send_func(send_msg, ephemeral=True)
        except Exception:
            pass

    # ------------------------------- UTILITIES ------------------------------- #

    async def send_status_message(
        self, title: str, description: str, color: discord.Color
    ) -> None:
        """Send a status embed to the configured status channel."""
        if not self.is_ready() or not self.user:
            return

        try:
            channel = (
                self.get_channel(STATUS_CHANNEL_ID)
                or await self.fetch_channel(STATUS_CHANNEL_ID)
            )
            if isinstance(channel, discord.TextChannel):
                embed = discord.Embed(
                    title=title,
                    description=description,
                    color=color,
                    timestamp=datetime.now(timezone.utc),
                )
                embed.set_footer(text=f"Bot ID: {self.user.id}")
                await channel.send(embed=embed)
            else:
                self.logger.warning(
                    f"Status channel {STATUS_CHANNEL_ID} is not a text channel."
                )
        except (discord.NotFound, discord.Forbidden) as e:
            self.logger.warning(
                f"Could not send status message to channel {STATUS_CHANNEL_ID}: {e}"
            )
        except Exception as e:
            self.logger.exception(
                f"An unexpected error occurred while sending status message: {e}"
            )

    # ----------------------------- BACKGROUND TASKS -------------------------- #

    @tasks.loop(minutes=5.0)
    async def auto_save_config(self) -> None:
        """Periodically save configuration to disk."""
        try:
            await self.save_config()
            self.logger.info("Configuration auto-saved successfully.")
        except Exception as e:
            self.logger.error(f"Failed to auto-save configuration: {e}")

    @auto_save_config.before_loop
    async def before_auto_save(self) -> None:
        """Wait until the bot is ready before starting the auto-save loop."""
        await self.wait_until_ready()

    @tasks.loop(minutes=1.0)
    async def health_check(self) -> None:
        """
        Periodic health check:
        - Database ping
        - HTTP ping
        - Latency logging
        """
        if not self.is_ready():
            return

        # 1) DB health
        try:
            await self.db.ping()
        except Exception as e:
            self.logger.warning(f"DB health check failed: {e}")

        # 2) HTTP health (Discord API gateway)
        if self.http_session:
            try:
                async with self.http_session.get(
                    "https://discord.com/api/v10/gateway", timeout=5
                ) as r:
                    if r.status not in (200, 401):
                        self.logger.warning(
                            f"HTTP health check returned non-200/401 status: {r.status}"
                        )
            except asyncio.TimeoutError:
                self.logger.warning("HTTP health check timed out.")
            except Exception as e:
                self.logger.warning(f"HTTP health check failed: {e}")

        # 3) Latency info
        try:
            if self.latency is not None:
                self.logger.debug(f"Heartbeat latency: {self.latency * 1000:.1f} ms")
        except Exception:
            pass


# --------------------------------------------------------------------------- #
#                                  OWNER COG                                  #
# --------------------------------------------------------------------------- #

class OwnerCog(commands.Cog, name="Owner"):
    """Owner-only commands (shutdown, sync, etc.)."""

    def __init__(self, bot: MaxyBot):
        self.bot = bot

    @commands.command(name="shutdown", hidden=True)
    @commands.is_owner()
    async def shutdown(self, ctx: commands.Context) -> None:
        """Safely shut down the bot."""
        view = ShutdownConfirmView(ctx.author.id)
        msg = await ctx.send(
            "❓ Are you absolutely sure you want to shut down the bot?",
            view=view,
        )

        await view.wait()

        if view.value is True:
            await msg.edit(content="⏳ Shutting down...", view=None)
            self.bot.logger.info(
                f"Shutdown command issued by {ctx.author} ({ctx.author.id}). "
                f"Beginning shutdown."
            )
            await self.bot.close()
        elif view.value is False:
            await msg.edit(content="✅ Shutdown cancelled.", view=None)
        else:
            await msg.edit(
                content="⚠️ Shutdown confirmation timed out. Operation aborted.",
                view=None,
            )

    @commands.command(name="sync", hidden=True)
    @commands.is_owner()
    async def sync(
        self,
        ctx: commands.Context,
        scope: Optional[Literal["current_guild", "clear", "global"]] = None,
    ) -> None:
        """
        Sync application commands.

        Scopes:
            - current_guild: sync only the current guild (fast).
            - clear: clear all global commands (dangerous).
            - global: full global sync (slow).
        """
        if scope == "current_guild":
            if not ctx.guild:
                await ctx.send("❌ This command can only be used in a server.")
                return

            try:
                synced = await self.bot.tree.sync(guild=ctx.guild)
                await ctx.send(
                    f"✅ Synced **{len(synced)}** commands to **{ctx.guild.name}**."
                )
                self.bot.logger.info(
                    f"Commands synced to guild {ctx.guild.id} by {ctx.author}."
                )
            except Exception as e:
                self.bot.logger.exception(f"Failed to sync to guild {ctx.guild.id}")
                await ctx.send(f"❌ An error occurred during sync: `{e}`")
            return

        if scope is None:
            scope = "global"  # Default to global sync

        is_clearing = scope == "clear"
        action_description = (
            "clear all **GLOBAL** commands"
            if is_clearing
            else "sync all **GLOBAL** commands"
        )

        confirm_message = (
            f"**🛑 WARNING:** Are you absolutely sure you want to {action_description}?\n"
            "This is a major action and may take up to an hour to update everywhere on Discord."
        )

        view = SyncConfirmView(ctx.author.id, is_clearing=is_clearing)
        msg = await ctx.send(confirm_message, view=view)
        await view.wait()

        if view.value is True:
            await msg.edit(
                content=f"⏳ {action_description.capitalize()} in progress...",
                view=None,
            )

            # For clear/global we always sync on the global scope (guild=None)
            guild_to_sync = None

            try:
                await self.bot.tree.sync(guild=guild_to_sync)
                final_action = "Cleared" if is_clearing else "Synced"
                await msg.edit(content=f"✅ Successfully **{final_action}** global commands.")
                self.bot.logger.info(
                    f"Global commands {final_action.lower()} by {ctx.author}."
                )
            except Exception as e:
                self.bot.logger.exception(f"Failed to {action_description} globally")
                await msg.edit(
                    content=f"❌ An error occurred during global sync/clear: `{e}`"
                )
        elif view.value is False:
            await msg.edit(content="✅ Sync/Clear cancelled.", view=None)
        else:
            await msg.edit(
                content="⚠️ Sync/Clear confirmation timed out. Operation aborted.",
                view=None,
            )


# --------------------------------------------------------------------------- #
#                              MAIN EXECUTION BLOCK                            #
# --------------------------------------------------------------------------- #

def main() -> None:
    """Initialize and run the bot."""
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        logger.critical(
            "FATAL: DISCORD_BOT_TOKEN environment variable not found. "
            "Please set it in your environment or .env file."
        )
        sys.exit(1)

    bot = MaxyBot()

    # Graceful shutdown signal handlers (Linux/Docker)
    def handle_signal(sig, frame) -> None:
        logger.info(f"Received signal {sig}. Initiating graceful shutdown.")
        try:
            # Use call_soon_threadsafe to be safe from signal handler context
            bot.loop.call_soon_threadsafe(asyncio.create_task, bot.close())
        except Exception as e:
            logger.error(f"Error scheduling graceful shutdown: {e}")

    if os.name == "posix":
        try:
            signal.signal(signal.SIGINT, handle_signal)
            signal.signal(signal.SIGTERM, handle_signal)
        except ValueError:
            logger.warning(
                "Could not set up signal handlers. Running without graceful signal handling."
            )

    try:
        bot.run(token, log_handler=None)  # Disable discord.py's default logging
    except discord.errors.LoginFailure:
        logger.critical("FATAL: Invalid DISCORD_BOT_TOKEN was provided.")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Bot manually stopped via KeyboardInterrupt.")
    except Exception as e:
        logger.critical(
            f"FATAL: An unhandled exception occurred during bot run: {e}",
            exc_info=True,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()