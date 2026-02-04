"""
YouClaw Memory Manager
Persistent conversation memory and context management using SQLite.
"""

import aiosqlite
import asyncio
import logging
import json
from typing import List, Dict, Optional
from datetime import datetime
from .config import config
from .vector_manager import VectorManager

logger = logging.getLogger(__name__)


class MemoryManager:
    """Manages persistent conversation memory across platforms"""
    
    def __init__(self):
        self.db_path = config.bot.database_path
        self.max_context = config.bot.max_context_messages
        self.db: Optional[aiosqlite.Connection] = None
        self.vector_manager = VectorManager(self.db_path)
    
    async def initialize(self):
        """Initialize the database and create tables"""
        self.db = await aiosqlite.connect(self.db_path)
        await self.vector_manager.initialize()
        
        # Create conversations table
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                user_id TEXT NOT NULL,
                channel_id TEXT,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                metadata TEXT
            )
        """)
        
        # Create user profile table
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS user_profiles (
                platform TEXT NOT NULL,
                user_id TEXT NOT NULL,
                name TEXT,
                interests TEXT,
                onboarding_completed INTEGER DEFAULT 0,
                last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (platform, user_id)
            )
        """)
        
        # Create user preferences table
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS user_preferences (
                platform TEXT NOT NULL,
                user_id TEXT NOT NULL,
                preference_key TEXT NOT NULL,
                preference_value TEXT,
                PRIMARY KEY (platform, user_id, preference_key)
            )
        """)

        # Create global settings table
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS global_settings (
                setting_key TEXT PRIMARY KEY,
                setting_value TEXT,
                last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create users table for dashboard auth
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT DEFAULT 'user',
                linked_platform TEXT,
                linked_user_id TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create user secrets table (for individual tokens/keys)
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS user_secrets (
                platform TEXT NOT NULL,
                user_id TEXT NOT NULL,
                secret_key TEXT NOT NULL,
                secret_value TEXT,
                last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (platform, user_id, secret_key)
            )
        """)
        
        # Initialize default settings if they don't exist
        defaults = [
            ('search_enabled', 'true'),
            ('personality_enabled', 'true'),
            ('onboarding_enabled', 'true'),
            ('discord_enabled', 'false'),
            ('telegram_enabled', 'true'),
            ('discord_token', ''),
            ('telegram_token', '')
        ]
        for key, val in defaults:
             await self.db.execute("INSERT OR IGNORE INTO global_settings (setting_key, setting_value) VALUES (?, ?)", (key, val))
        
        # Create indexes for faster queries
        await self.db.execute("""
            CREATE INDEX IF NOT EXISTS idx_conversations_user 
            ON conversations(platform, user_id, timestamp DESC)
        """)
        
        await self.db.commit()
        logger.info(f"Memory manager initialized: {self.db_path}")

    def _hash_password(self, password: str) -> str:
        """Securely hash a password for storage"""
        import hashlib
        return hashlib.sha256(password.encode()).hexdigest()

    async def create_user(self, username: str, password: str, role: str = 'admin') -> bool:
        """Create a new dashboard user. Everyone is admin in this personal version."""
        try:
            pw_hash = self._hash_password(password)
            await self.db.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, 'admin')",
                (username, pw_hash)
            )
            await self.db.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to create user: {e}")
            return False

    async def verify_user(self, username: str, password: str) -> Optional[Dict]:
        """Verify user credentials and return user info with token"""
        pw_hash = self._hash_password(password)
        async with self.db.execute(
            "SELECT id, username, role, linked_platform, linked_user_id FROM users WHERE username = ? AND password_hash = ?",
            (username, pw_hash)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                # Generate a session token based on credentials and a deployment-specific secret
                import hashlib
                token_base = f"{username}{pw_hash}{config.bot.prefix}"
                token = hashlib.sha256(token_base.encode()).hexdigest()
                
                return {
                    "id": row[0],
                    "username": row[1],
                    "role": row[2],
                    "linked_platform": row[3],
                    "linked_user_id": row[4],
                    "token": token
                }
        return None

    async def link_account(self, username: str, platform: str, user_id: str):
        """Link a dashboard user to a Telegram/Discord identity"""
        await self.db.execute(
            "UPDATE users SET linked_platform = ?, linked_user_id = ? WHERE username = ?",
            (platform, user_id, username)
        )
        await self.db.commit()
        logger.info(f"Linked dashboard user {username} to {platform}:{user_id}")

    async def get_linked_identity(self, username: str) -> Optional[tuple]:
        """Get the platform:id linked to a username"""
        async with self.db.execute(
            "SELECT linked_platform, linked_user_id FROM users WHERE username = ?",
            (username,)
        ) as cursor:
            row = await cursor.fetchone()
            if row and row[0] and row[1]:
                return row[0], row[1]
        return None, None
    
    async def close(self):
        """Close the database connection"""
        if self.db:
            await self.db.close()
            logger.info("Memory manager closed")
    
    async def add_message(
        self,
        platform: str,
        user_id: str,
        role: str,
        content: str,
        channel_id: Optional[str] = None,
        metadata: Optional[Dict] = None
    ):
        """
        Add a message to conversation history.
        
        Args:
            platform: Platform name (discord, telegram)
            user_id: User identifier
            role: Message role (user, assistant, system)
            content: Message content
            channel_id: Optional channel/chat identifier
            metadata: Optional metadata dict
        """
        metadata_json = json.dumps(metadata) if metadata else None
        
        await self.db.execute("""
            INSERT INTO conversations 
            (platform, user_id, channel_id, role, content, metadata)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (platform, user_id, channel_id, role, content, metadata_json))
        
        await self.db.commit()

        # Phase 1: Semantic Indexing
        try:
            # We need the last inserted ID
            async with self.db.execute("SELECT last_insert_rowid()") as cursor:
                message_id = (await cursor.fetchone())[0]
                # Trigger embedding in background to not block the chat response
                asyncio.create_task(self.vector_manager.save_embedding(message_id, content))
        except Exception as ve:
            logger.error(f"Failed to trigger semantic indexing: {ve}")
    
    async def get_conversation_history(
        self,
        platform: str,
        user_id: str,
        channel_id: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, str]]:
        """
        Get conversation history for a user.
        
        Args:
            platform: Platform name
            user_id: User identifier
            channel_id: Optional channel filter
            limit: Max number of messages (defaults to max_context)
        
        Returns:
            List of message dicts with 'role' and 'content'
        """
        limit = limit or self.max_context
        
        query = """
            SELECT role, content FROM conversations
            WHERE platform = ? AND user_id = ?
        """
        params = [platform, user_id]
        
        if channel_id:
            query += " AND channel_id = ?"
            params.append(channel_id)
        
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        
        async with self.db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            
            # Reverse to get chronological order
            messages = [
                {"role": row[0], "content": row[1]}
                for row in reversed(rows)
            ]
            
            return messages
    
    async def clear_conversation(
        self,
        platform: str,
        user_id: str,
        channel_id: Optional[str] = None
    ):
        """Clear conversation history for a user"""
        query = "DELETE FROM conversations WHERE platform = ? AND user_id = ?"
        params = [platform, user_id]
        
        if channel_id:
            query += " AND channel_id = ?"
            params.append(channel_id)
        
        await self.db.execute(query, params)
        await self.db.commit()
        logger.info(f"Cleared conversation for {platform}:{user_id}")
    
    async def set_user_preference(
        self,
        platform: str,
        user_id: str,
        key: str,
        value: str
    ):
        """Set a user preference"""
        await self.db.execute("""
            INSERT OR REPLACE INTO user_preferences
            (platform, user_id, preference_key, preference_value)
            VALUES (?, ?, ?, ?)
        """, (platform, user_id, key, value))
        
        await self.db.commit()
    
    async def get_user_preference(
        self,
        platform: str,
        user_id: str,
        key: str,
        default: Optional[str] = None
    ) -> Optional[str]:
        """Get a user preference"""
        async with self.db.execute("""
            SELECT preference_value FROM user_preferences
            WHERE platform = ? AND user_id = ? AND preference_key = ?
        """, (platform, user_id, key)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else default

    async def get_user_profile(self, platform: str, user_id: str) -> Dict:
        """Get user profile information"""
        async with self.db.execute("""
            SELECT name, interests, onboarding_completed FROM user_profiles
            WHERE platform = ? AND user_id = ?
        """, (platform, user_id)) as cursor:
            row = await cursor.fetchone()
            if row:
                return {
                    "name": row[0],
                    "interests": row[1],
                    "onboarding_completed": bool(row[2])
                }
            return {"name": None, "interests": None, "onboarding_completed": False}

    async def update_user_profile(self, platform: str, user_id: str, **kwargs):
        """Update user profile information"""
        fields = []
        values = []
        for key, value in kwargs.items():
            if key in ['name', 'interests', 'onboarding_completed']:
                if key == 'onboarding_completed':
                    value = 1 if value else 0
                fields.append(f"{key} = ?")
                values.append(value)
        
        if not fields:
            return

        values.extend([platform, user_id])
        
        # Try to update first
        query = f"UPDATE user_profiles SET {', '.join(fields)}, last_updated = CURRENT_TIMESTAMP WHERE platform = ? AND user_id = ?"
        cursor = await self.db.execute(query, values)
        
        if cursor.rowcount == 0:
            # If no rows updated, insert new profile
            insert_fields = ['platform', 'user_id'] + list(kwargs.keys())
            insert_placeholders = ['?'] * len(insert_fields)
            insert_values = [platform, user_id] + [1 if k == 'onboarding_completed' and v else v for k, v in kwargs.items()]
            
            await self.db.execute(f"""
                INSERT INTO user_profiles ({', '.join(insert_fields)})
                VALUES ({', '.join(insert_placeholders)})
            """, insert_values)

        await self.db.commit()
    
    async def get_global_setting(self, key: str, default: str = None) -> str:
        """Get a global setting"""
        async with self.db.execute("SELECT setting_value FROM global_settings WHERE setting_key = ?", (key,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else default

    async def set_global_setting(self, key: str, value: str):
        """Set a global setting"""
        await self.db.execute("""
            INSERT OR REPLACE INTO global_settings (setting_key, setting_value, last_updated)
            VALUES (?, ?, CURRENT_TIMESTAMP)
        """, (key, str(value)))
        await self.db.commit()

    async def get_user_secret(self, platform: str, user_id: str, key: str, default: str = None) -> str:
        """Get a user-specific secret (e.g., personal API key)"""
        async with self.db.execute("""
            SELECT secret_value FROM user_secrets 
            WHERE platform = ? AND user_id = ? AND secret_key = ?
        """, (platform, user_id, key)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else default

    async def set_user_secret(self, platform: str, user_id: str, key: str, value: str):
        """Set a user-specific secret"""
        await self.db.execute("""
            INSERT OR REPLACE INTO user_secrets (platform, user_id, secret_key, secret_value, last_updated)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (platform, user_id, key, str(value)))
        await self.db.commit()

    async def get_stats(self) -> Dict:
        """Get database statistics"""
        async with self.db.execute("""
            SELECT COUNT(*) FROM conversations
        """) as cursor:
            total_messages = (await cursor.fetchone())[0]
        
        async with self.db.execute("""
            SELECT COUNT(DISTINCT user_id) FROM conversations
        """) as cursor:
            unique_users = (await cursor.fetchone())[0]
        
        return {
            "total_messages": total_messages,
            "unique_users": unique_users,
            "database_path": self.db_path
        }

    async def get_semantic_context(self, query: str, limit: int = 5) -> str:
        """Get semantic context as a formatted string for LLM"""
        results = await self.vector_manager.search_semantic(query, limit=limit)
        if not results:
            return ""
        
        context_parts = ["### SEMANTIC MEMORY (PAST CONTEXT) ###"]
        for res in results:
            context_parts.append(f"[{res['timestamp']}] {res['role'].upper()}: {res['content']}")
        
        return "\n".join(context_parts) + "\n"


# Global memory manager instance
memory_manager = MemoryManager()
