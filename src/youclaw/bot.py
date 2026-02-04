"""
YouClaw - Your Personal AI Assistant
Main bot orchestrator that runs Discord and Telegram handlers concurrently.
"""

import asyncio
import logging
import signal
import sys
from .config import config
from .ollama_client import ollama_client
from .memory_manager import memory_manager
from .scheduler_manager import scheduler_manager
from .discord_handler import discord_handler
from .telegram_handler import telegram_handler
from .dashboard import run_dashboard
from .skills_manager import skill_manager

# Set up logging
logging.basicConfig(
    level=getattr(logging, config.bot.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('youclaw.log')
    ]
)

logger = logging.getLogger(__name__)


class YouClaw:
    """Main YouClaw bot orchestrator"""
    
    def __init__(self):
        self.running = False
        self.platform_tasks = []
        self.dashboard_task = None
        self.stop_event = asyncio.Event()
    
    async def initialize(self):
        """Initialize bot cores"""
        logger.info("🦞 Initializing YouClaw...")
        
        # Initialize memory manager
        await memory_manager.initialize()
        
        # Initialize Ollama client
        await ollama_client.initialize()
        
        # Initialize scheduler manager
        scheduler_manager.initialize(self, config.bot.database_path)
        
        # Load dynamic skills
        skill_manager.load_dynamic_skills()
        
        logger.info("🤖 YouClaw Cores Initialized")
        
        # Check Ollama health
        if not await ollama_client.check_health():
            logger.error("❌ Ollama is not available!")
            # Don't exit here, maybe user will fix it via dashboard? 
            # Actually, we need Ollama for core features, but dashboard should stay up.
        
        # Load initial config from DB
        await config.refresh_from_db()
        logger.info("🚀 YouClaw initialization complete!")
    
    async def _start_platforms(self):
        """Internal method to start enabled platforms"""
        # Clear existing tasks
        for task in self.platform_tasks:
            task.cancel()
        self.platform_tasks = []
        
        if config.discord.enabled and config.discord.token:
            logger.info("Starting Discord handler...")
            task = asyncio.create_task(discord_handler.start())
            self.platform_tasks.append(task)
        elif config.discord.enabled:
            logger.warning("Discord enabled but no token provided!")

        if config.telegram.enabled and config.telegram.token:
            logger.info("Starting Telegram handler...")
            task = asyncio.create_task(telegram_handler.start())
            self.platform_tasks.append(task)
        elif config.telegram.enabled:
            logger.warning("Telegram enabled but no token provided!")

        if not self.platform_tasks:
            logger.info("No platform handlers started. Bot is in standby mode.")

    async def start(self):
        """Start all enabled platform handlers"""
        self.running = True
        await self._start_platforms()
        
        logger.info("✅ All platforms started. YouClaw is now online! 🦞")
        
        # Keep running until stop_event is set
        await self.stop_event.wait()
    
    async def restart_handlers(self):
        """Refresh config and restart platform handlers ONLY (keep dashboard alive)"""
        logger.info("♻️ Restarting handlers with fresh config...")
        
        # Stop current platform handlers
        await discord_handler.stop()
        await telegram_handler.stop()
        
        # Refresh configuration from database
        await config.refresh_from_db()
        
        # Start platforms again
        await self._start_platforms()
        logger.info("✅ Handlers restarted successfully")

    async def shutdown(self):
        """Gracefully shutdown all components"""
        logger.info("🛑 Shutting down YouClaw...")
        self.running = False
        
        # Set stop event to break the start() wait
        self.stop_event.set()
        
        # Cancel all platform tasks
        for task in self.platform_tasks:
            task.cancel()
        
        # Cancel dashboard
        if self.dashboard_task:
            self.dashboard_task.cancel()
        
        # Stop platform handlers
        await discord_handler.stop()
        await telegram_handler.stop()
        
        # Close connections
        await ollama_client.close()
        await memory_manager.close()
        
        logger.info("👋 YouClaw shutdown complete")
    
    def handle_signal(self, sig):
        """Handle shutdown signals"""
        logger.info(f"Received signal {sig}, initiating shutdown...")
        asyncio.create_task(self.shutdown())


# Global bot instance
youclaw_bot = YouClaw()

async def main():
    """Main entry point"""
    # Initialize cores
    await youclaw_bot.initialize()
    
    # Set up signal handlers
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda s=sig: youclaw_bot.handle_signal(s))
    
    try:
        # Start Dashboard as a background task
        # We pass the bot instance so the dashboard can control it
        logger.info("Starting Web Dashboard...")
        youclaw_bot.dashboard_task = asyncio.create_task(run_dashboard(youclaw_bot, port=8080))
        
        # Start bot handlers (this blocks until shutdown)
        await youclaw_bot.start()
    
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
    finally:
        await youclaw_bot.shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

