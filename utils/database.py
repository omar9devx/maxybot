# Filename: utils/db_manager.py

import aiosqlite
import logging
import asyncio
from pathlib import Path
from typing import Any, Iterable, Optional, List, Union

# Set up a logger for database-related messages
logger = logging.getLogger(__name__)


class DatabaseManager:
    """
    An asynchronous and robust database manager for SQLite using aiosqlite.

    This class handles connection, initialization, and common database operations,
    with added concurrency control to prevent 'database is locked' errors.
    """

    def __init__(self, db_path: Union[str, Path]):
        """
        Initializes the DatabaseManager.

        Args:
            db_path: The file path to the SQLite database.
        """
        self._db_path = Path(db_path)
        self._db: Optional[aiosqlite.Connection] = None
        self._lock = asyncio.Lock()  # Lock for serializing write operations

    async def _get_db(self) -> aiosqlite.Connection:
        """
        Lazily connects to the database if not already connected.

        This method ensures there's an active connection before any operation.
        It also configures the connection to return rows as dictionary-like objects
        and enables Write-Ahead Logging (WAL) for improved concurrency.

        Returns:
            An active aiosqlite.Connection object.
        """
        # Use a lock to prevent race conditions during the initial connection setup.
        async with self._lock:
            if self._db is None or not getattr(self._db, '_running', False):
                self._db_path.parent.mkdir(parents=True, exist_ok=True)
                self._db = await aiosqlite.connect(self._db_path)
                self._db.row_factory = aiosqlite.Row
                # Enable Write-Ahead Logging for better concurrency.
                # It allows multiple readers to operate while a writer is active.
                await self._db.execute("PRAGMA journal_mode=WAL;")
                logger.info(f"Database connection established to: {self._db_path}")
        return self._db

    async def init(self) -> None:
        """
        Initializes the database by creating tables and applying schema migrations.
        This method is designed to be idempotent and safe to run on startup.
        """
        db = await self._get_db()
        
        # A list of all CREATE TABLE statements.
        tables = [
            # Economy
            '''CREATE TABLE IF NOT EXISTS economy (
                guild_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                wallet INTEGER DEFAULT 0,
                bank INTEGER DEFAULT 0,
                PRIMARY KEY (guild_id, user_id)
            )''',
            # Leveling
            '''CREATE TABLE IF NOT EXISTS leveling (
                guild_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                xp INTEGER DEFAULT 0,
                level INTEGER DEFAULT 0,
                PRIMARY KEY (guild_id, user_id)
            )''',
            # Warnings
            '''CREATE TABLE IF NOT EXISTS warnings (
                warn_id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                moderator_id TEXT NOT NULL,
                reason TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )''',
            # AFK Status
            '''CREATE TABLE IF NOT EXISTS afk (
                guild_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                reason TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (guild_id, user_id)
            )''',
            # User Inventory
            '''CREATE TABLE IF NOT EXISTS user_inventory (
                inventory_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                guild_id TEXT NOT NULL,
                item_id TEXT NOT NULL,
                item_type TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                is_active INTEGER DEFAULT 0 CHECK(is_active IN (0, 1)),
                UNIQUE (user_id, guild_id, item_id)
            )''',
            # Giveaways
            '''CREATE TABLE IF NOT EXISTS giveaways (
                message_id TEXT PRIMARY KEY,
                guild_id TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                prize TEXT NOT NULL,
                end_timestamp REAL NOT NULL,
                winner_count INTEGER NOT NULL,
                is_ended INTEGER DEFAULT 0 CHECK(is_ended IN (0, 1))
            )''',
            '''CREATE TABLE IF NOT EXISTS giveaway_entrants (
                message_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                PRIMARY KEY (message_id, user_id),
                FOREIGN KEY (message_id) REFERENCES giveaways(message_id) ON DELETE CASCADE
            )''',
            # Tickets
            '''CREATE TABLE IF NOT EXISTS tickets (
                channel_id TEXT PRIMARY KEY,
                guild_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                status TEXT DEFAULT 'open' CHECK(status IN ('open', 'closed'))
            )''',
            # Auto Responses
            '''CREATE TABLE IF NOT EXISTS auto_responses (
                response_id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id TEXT NOT NULL,
                trigger TEXT NOT NULL,
                response TEXT NOT NULL,
                creator_id TEXT NOT NULL,
                match_type TEXT NOT NULL DEFAULT 'exact' 
                    CHECK(match_type IN ('exact', 'contains', 'starts_with', 'ends_with', 'regex')),
                response_type TEXT NOT NULL DEFAULT 'text' 
                    CHECK(response_type IN ('text', 'embed', 'dm', 'message', 'reply', 'react')),
                case_sensitive INTEGER NOT NULL DEFAULT 0 
                    CHECK(case_sensitive IN (0, 1)),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (guild_id, trigger)
            )''',


            # Starboard
            '''CREATE TABLE IF NOT EXISTS starboard (
                original_message_id TEXT PRIMARY KEY,
                starboard_message_id TEXT NOT NULL,
                guild_id TEXT NOT NULL
            )''',
            # Level Rewards
            '''CREATE TABLE IF NOT EXISTS level_rewards (
                guild_id TEXT NOT NULL,
                level INTEGER NOT NULL,
                role_id TEXT NOT NULL,
                PRIMARY KEY (guild_id, level)
            )''',
            # Reminders
            '''CREATE TABLE IF NOT EXISTS reminders (
                reminder_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                remind_content TEXT NOT NULL,
                remind_timestamp REAL NOT NULL
            )''',
            # Polls
            '''CREATE TABLE IF NOT EXISTS polls (
                poll_id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                message_id TEXT NOT NULL UNIQUE,
                question TEXT NOT NULL,
                options TEXT NOT NULL, -- JSON encoded list of options
                end_timestamp REAL NOT NULL,
                is_ended INTEGER DEFAULT 0 CHECK(is_ended IN (0, 1))
            )''',
            '''CREATE TABLE IF NOT EXISTS poll_votes (
                poll_id INTEGER NOT NULL,
                user_id TEXT NOT NULL,
                option_index INTEGER NOT NULL,
                PRIMARY KEY (poll_id, user_id),
                FOREIGN KEY (poll_id) REFERENCES polls(poll_id) ON DELETE CASCADE
            )'''
        ]
        
        async with self._lock:
            try:
                await db.execute("BEGIN")
                for table_query in tables:
                    await db.execute(table_query)
                
                # --- Schema Migrations ---
                # This section handles database updates for existing users.
                
                # Get current columns of the auto_responses table
                async with db.execute("PRAGMA table_info(auto_responses)") as cursor:
                    columns = [row['name'] for row in await cursor.fetchall()]
                
                # Migration 1: Add 'match_type'
                if 'match_type' not in columns:
                    logger.info("Upgrading 'auto_responses' table: adding 'match_type' column.")
                    await db.execute("ALTER TABLE auto_responses ADD COLUMN match_type TEXT NOT NULL DEFAULT 'exact' CHECK(match_type IN ('exact', 'contains', 'regex'))")
                    logger.info("Table 'auto_responses' upgraded successfully for 'match_type'.")

                # Migration 2: Add 'response_type'
                if 'response_type' not in columns:
                    logger.info("Upgrading 'auto_responses' table: adding 'response_type' column.")
                    await db.execute("ALTER TABLE auto_responses ADD COLUMN response_type TEXT NOT NULL DEFAULT 'text' CHECK(response_type IN ('text', 'embed', 'dm'))")
                    logger.info("Table 'auto_responses' upgraded successfully for 'response_type'.")

                # Migration 3: Add 'case_sensitive'
                if 'case_sensitive' not in columns:
                    logger.info("Upgrading 'auto_responses' table: adding 'case_sensitive' column.")
                    await db.execute("ALTER TABLE auto_responses ADD COLUMN case_sensitive INTEGER NOT NULL DEFAULT 0 CHECK(case_sensitive IN (0, 1))")
                    logger.info("Table 'auto_responses' upgraded successfully for 'case_sensitive'.")

                # **FIX**: Migration 4: Add 'created_at'
                if 'created_at' not in columns:
                    logger.info("Upgrading 'auto_responses' table: adding 'created_at' column.")
                    # Step 1: Add the column without the non-constant default.
                    await db.execute("ALTER TABLE auto_responses ADD COLUMN created_at DATETIME")
                    # Step 2: Update existing rows to have a value.
                    await db.execute("UPDATE auto_responses SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL")
                    logger.info("Table 'auto_responses' upgraded successfully for 'created_at'.")


                await db.commit()
                logger.info("Database tables initialized and migrations applied successfully.")

            except aiosqlite.Error as e:
                await db.rollback() # Roll back changes if any error occurs
                logger.error(f"Failed to initialize database tables: {e}")
                raise
    async def ping(self) -> bool:
        """
        Simple async ping to test DB connection.
        Returns True if DB is reachable.
        """
        try:
            db = await self._get_db()
            async with db.execute("SELECT 1") as cursor:
                await cursor.fetchone()
            return True
        except Exception as e:
            logger.warning(f"DB ping failed: {e}")
            return False

    async def execute(self, query: str, params: Iterable[Any] = ()) -> None:
        """
        Executes a query that modifies the database (INSERT, UPDATE, DELETE).
        This operation is locked to prevent concurrency issues.
        """
        db = await self._get_db()
        async with self._lock:
            await db.execute(query, params)
            await db.commit()

    async def executemany(self, query: str, seq_of_params: Iterable[Iterable[Any]]) -> None:
        """
        Executes a query multiple times with different parameter sets.
        This operation is locked to prevent concurrency issues.
        """
        db = await self._get_db()
        async with self._lock:
            await db.executemany(query, seq_of_params)
            await db.commit()

    async def fetchone(self, query: str, params: Iterable[Any] = ()) -> Optional[aiosqlite.Row]:
        """
        Fetches a single row from the database (read operation).
        No lock is needed for reads when WAL is enabled.
        """
        db = await self._get_db()
        async with db.execute(query, params) as cursor:
            return await cursor.fetchone()


    async def fetchall(self, query: str, params: Iterable[Any] = ()) -> List[aiosqlite.Row]:
        """
        Fetches all rows from a database query (read operation).
        No lock is needed for reads when WAL is enabled.
        """
        db = await self._get_db()
        async with db.execute(query, params) as cursor:
            return await cursor.fetchall()

    async def close(self) -> None:
        """Closes the database connection if it is open."""
        if self._db:
            await self._db.close()
            self._db = None
            logger.info("Database connection closed.")

    # --- Auto-Responder Specific Methods ---

    async def add_auto_response(
        self,
        guild_id: int,
        trigger: str,
        response: str,
        creator_id: int,
        match_type: str = 'exact',
        response_type: str = 'text',
        case_sensitive: bool = False
    ) -> bool:
        """
        Adds a new auto-response. Returns False if the trigger already exists.
        """
        try:
            await self.execute(
                "INSERT INTO auto_responses (guild_id, trigger, response, creator_id, match_type, response_type, case_sensitive) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (str(guild_id), trigger, response, str(creator_id), match_type, response_type, int(case_sensitive))
            )
            return True
        except aiosqlite.IntegrityError:
            logger.warning(f"Attempted to add a duplicate auto-response trigger '{trigger}' in guild {guild_id}.")
            return False

    async def remove_auto_response(self, guild_id: int, trigger: str) -> bool:
        """
        Removes an auto-response. Returns True if a row was deleted.
        Note: This method doesn't use self.execute because it needs the
        rowcount from the cursor to confirm deletion.
        """
        db = await self._get_db()
        async with self._lock:
            cursor = await db.execute("DELETE FROM auto_responses WHERE guild_id = ? AND trigger = ?", (str(guild_id), trigger))
            await db.commit()
            # cursor.rowcount provides the number of affected rows.
            return cursor.rowcount > 0

    async def get_all_auto_responses(self, guild_id: int) -> List[aiosqlite.Row]:
        """
        Retrieves all auto-responses for a guild.
        """
        return await self.fetchall(
            "SELECT * FROM auto_responses WHERE guild_id = ?",
            (str(guild_id),)
        )