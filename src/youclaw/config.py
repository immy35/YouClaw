"""
YouClaw Configuration Management
Centralized configuration with environment variable loading and validation.
"""

import os
from dataclasses import dataclass
from typing import Optional
from pathlib import Path
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)

# Permanent Data Directory (~/.youclaw)
DATA_DIR = Path.home() / ".youclaw"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Path to .env file
ENV_PATH = DATA_DIR / ".env"

local_env = Path(".env")
if not ENV_PATH.exists() and local_env.exists():
    import shutil
    try:
        shutil.copy(local_env, ENV_PATH)
        logger.info(f"✨ Migrated {local_env} to stable home.")
    except: pass

# Load environment variables
load_dotenv() # Load from CWD
if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH, override=True) # Absolute priority to stable home


@dataclass
class OllamaConfig:
    """Ollama service configuration"""
    host: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    model: str = os.getenv("OLLAMA_MODEL", "qwen2.5:1.5b-instruct")
    temperature: float = float(os.getenv("OLLAMA_TEMPERATURE", "0.7"))
    max_tokens: int = int(os.getenv("OLLAMA_MAX_TOKENS", "2048"))
    timeout: int = int(os.getenv("OLLAMA_TIMEOUT", "60"))
    
    def __post_init__(self):
        """Validate configuration"""
        if not self.host:
            logger.warning("OLLAMA_HOST not found. Using default: http://localhost:11434")
            self.host = "http://localhost:11434"
        if not self.model:
            logger.warning("OLLAMA_MODEL not found. Using default: qwen2.5:1.5b-instruct")
            self.model = "qwen2.5:1.5b-instruct"


@dataclass
class DiscordConfig:
    """Discord bot configuration"""
    token: Optional[str] = os.getenv("DISCORD_BOT_TOKEN")
    enabled: bool = os.getenv("ENABLE_DISCORD", "true").lower() == "true"
    
    def __post_init__(self):
        """Validate configuration"""
        if self.enabled and not self.token:
            logger.warning("DISCORD_BOT_TOKEN not found. Disabling Discord integration.")
            self.enabled = False


@dataclass
class TelegramConfig:
    """Telegram bot configuration"""
    token: Optional[str] = os.getenv("TELEGRAM_BOT_TOKEN")
    enabled: bool = os.getenv("ENABLE_TELEGRAM", "true").lower() == "true"
    
    def __post_init__(self):
        """Validate configuration"""
        if self.enabled and not self.token:
            logger.warning("TELEGRAM_BOT_TOKEN not found. Disabling Telegram integration.")
            self.enabled = False


@dataclass
class BotConfig:
    """General bot configuration"""
    prefix: str = os.getenv("BOT_PREFIX", "!")
    max_context_messages: int = int(os.getenv("MAX_CONTEXT_MESSAGES", "20"))
    database_path: str = os.getenv("DATABASE_PATH", str(DATA_DIR / "youclaw.db"))
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    search_url: str = os.getenv("SEARCH_ENGINE_URL", "http://57.128.250.34:8080/search")
    admin_user_identity: str = os.getenv("ADMIN_USER_IDENTITY", "telegram:default") # format platform:id
    dashboard_port: int = int(os.getenv("DASHBOARD_PORT", "8080"))
    
    def __post_init__(self):
        """Validate configuration"""
        if self.max_context_messages < 1:
            raise ValueError("MAX_CONTEXT_MESSAGES must be at least 1")
        
        # Create data directory if it doesn't exist
        os.makedirs(os.path.dirname(self.database_path), exist_ok=True)

@dataclass
class EmailConfig:
    """Email service configuration"""
    imap_host: str = os.getenv("EMAIL_IMAP_HOST", "")
    imap_port: int = int(os.getenv("EMAIL_IMAP_PORT", "993"))
    smtp_host: str = os.getenv("EMAIL_SMTP_HOST", "")
    smtp_port: int = int(os.getenv("EMAIL_SMTP_PORT", "587"))
    user: str = os.getenv("EMAIL_USER", "")
    password: str = os.getenv("EMAIL_PASSWORD", "")
    enabled: bool = os.getenv("ENABLE_EMAIL", "false").lower() == "true"


class Config:
    """Main configuration class"""
    
    def __init__(self):
        self.bot = BotConfig()
        self.ollama = OllamaConfig()
        self.discord = DiscordConfig()
        self.telegram = TelegramConfig()
        self.email = EmailConfig()
        self.search_url = os.getenv("SEARCH_ENGINE_URL", "http://57.128.250.34:8080/search")

        # Refresh from database if possible
        try:
            # This is a bit tricky during first init, but refresh_from_db handles it
            pass
        except:
             pass

    async def refresh_from_db(self):
        """Refresh dynamic settings from database"""
        try:
            from .memory_manager import memory_manager
            
            # Override tokens if present in DB
            dt = await memory_manager.get_global_setting("discord_token")
            if dt and dt.strip(): self.discord.token = dt
            
            tt = await memory_manager.get_global_setting("telegram_token")
            if tt and tt.strip(): self.telegram.token = tt
            
            # Override status
            de_val = await memory_manager.get_global_setting("discord_enabled")
            if de_val:
                self.discord.enabled = de_val.lower() == "true"
            
            te_val = await memory_manager.get_global_setting("telegram_enabled")
            if te_val:
                self.telegram.enabled = te_val.lower() == "true"
            
            st = await memory_manager.get_global_setting("search_url")
            if st and st.strip(): self.search_url = st
            
            # Email Settings
            eh = await memory_manager.get_global_setting("email_imap_host")
            if eh: self.email.imap_host = eh
            ep = await memory_manager.get_global_setting("email_imap_port")
            if ep: self.email.imap_port = int(ep)
            sh = await memory_manager.get_global_setting("email_smtp_host")
            if sh: self.email.smtp_host = sh
            sp = await memory_manager.get_global_setting("email_smtp_port")
            if sp: self.email.smtp_port = int(sp)
            eu = await memory_manager.get_global_setting("email_user")
            if eu: self.email.user = eu
            epw = await memory_manager.get_global_setting("email_password")
            if epw: self.email.password = epw
            ee = await memory_manager.get_global_setting("email_enabled")
            if ee: self.email.enabled = ee.lower() == "true"
            
            # Model Persistence
            am = await memory_manager.get_global_setting("active_model")
            if am and am.strip():
                self.ollama.model = am
            # Model Persistence
            am = await memory_manager.get_global_setting("active_model")
            if am and am.strip():
                self.ollama.model = am
            
            # Host Persistence (Fixes "Vanishing URL" bug)
            oh = await memory_manager.get_global_setting("ollama_host")
            if oh and oh.strip():
                self.ollama.host = oh
                # Re-init session if needed handled by client, but host property is dynamic if we used config directly
                # ollama_client uses config.ollama.host property, so this update is immediate.
            
            # Note: ollama_client properties are tied to this config instance
            
            logger.info(f"Config Refreshed: Host={self.ollama.host}, Model={self.ollama.model}, Discord={self.discord.enabled}, Telegram={self.telegram.enabled}")
        except Exception as e:
            logger.error(f"Error refreshing config from DB: {e}")
    
    def __repr__(self):
        return (
            f"Config(\n"
            f"  Ollama: {self.ollama.host} (model: {self.ollama.model})\n"
            f"  Discord: {'enabled' if self.discord.enabled else 'disabled'}\n"
            f"  Telegram: {'enabled' if self.telegram.enabled else 'disabled'}\n"
            f"  Prefix: {self.bot.prefix}\n"
            f"  Database: {self.bot.database_path}\n"
            f")"
        )


# Global config instance
config = Config()
