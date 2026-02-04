"""
YouClaw Scheduler Manager
Handles background tasks, heartbeats, and proactive notifications.
"""

import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from typing import Dict, Any, Callable, Optional
from datetime import datetime
import asyncio

logger = logging.getLogger(__name__)

class SchedulerManager:
    """Manages proactive bot tasks and cron jobs"""
    
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.bot_instance = None
    
    def initialize(self, bot_instance, db_path: str):
        """Initialize the scheduler with persistence"""
        self.bot_instance = bot_instance
        
        # Configure job store
        job_stores = {
            'default': SQLAlchemyJobStore(url=f'sqlite:///{db_path}')
        }
        
        self.scheduler.configure(jobstores=job_stores)
        self.scheduler.start()
        logger.info("Scheduler initialized and started")

    async def add_notification_job(
        self, 
        platform: str, 
        user_id: str, 
        message: str, 
        run_date: datetime,
        job_id: Optional[str] = None
    ):
        """Schedule a one-time notification message"""
        self.scheduler.add_job(
            self.send_notification,
            'date',
            run_date=run_date,
            args=[platform, user_id, message],
            id=job_id,
            replace_existing=True
        )
        logger.info(f"Scheduled notification for {user_id} on {platform} at {run_date}")

    async def add_cron_job(
        self,
        platform: str,
        user_id: str,
        message_func: Callable,
        cron_expression: str,
        job_id: str
    ):
        """Schedule a recurring tasks using cron expression"""
        # message_func should be an async function that returns a string to send
        self.scheduler.add_job(
            self.run_cron_task,
            'cron',
            args=[platform, user_id, message_func],
            id=job_id,
            replace_existing=True,
            **self._parse_cron(cron_expression)
        )
        logger.info(f"Scheduled cron job {job_id} for {user_id}")

    def _parse_cron(self, expr: str) -> Dict:
        """Simple parser for cron expressions (placeholder for robust parser)"""
        # For now, expect a simple format or use default
        # Format: "minute hour day month day_of_week"
        parts = expr.split()
        if len(parts) == 5:
            return {
                'minute': parts[0],
                'hour': parts[1],
                'day': parts[2],
                'month': parts[3],
                'day_of_week': parts[4]
            }
        return {'hour': 8} # Default 8 AM daily

    async def send_notification(self, platform: str, user_id: str, message: str):
        """Actual delivery of the message via the bot handlers"""
        await send_notification_task(platform, user_id, message)

    async def add_ai_cron_job(self, platform: str, user_id: str, prompt: str, cron_expr: str, job_id: str):
        """Schedule a recurring AI reasoning task"""
        self.scheduler.add_job(
            run_ai_job_task,
            'cron',
            args=[platform, user_id, prompt],
            id=job_id,
            replace_existing=True,
            **self._parse_cron(cron_expr)
        )
        logger.info(f"Scheduled AI Pulse job {job_id} for {user_id}: {prompt[:30]}...")

    async def add_watcher_job(self, platform: str, user_id: str, target_url: str, interval_minutes: int, job_id: str):
        """Schedule a background URL monitoring task"""
        self.scheduler.add_job(
            run_watcher_task,
            'interval',
            minutes=interval_minutes,
            args=[platform, user_id, target_url],
            id=job_id,
            replace_existing=True
        )
        logger.info(f"Scheduled Watcher job {job_id} for {user_id}: {target_url}")

# --- Top-Level Job Tasks (Moved outside class for serialization) ---

async def send_notification_task(platform: str, user_id: str, message: str):
    """Actual delivery of the message via the bot handlers or history"""
    from .memory_manager import memory_manager
    
    try:
        if platform == "telegram":
            from .telegram_handler import telegram_handler
            if telegram_handler.app:
                await telegram_handler.app.bot.send_message(chat_id=user_id, text=message)
            else:
                logger.error("Telegram App not initialized")
        elif platform == "discord":
            from .discord_handler import discord_handler
            if discord_handler.bot:
                user = await discord_handler.bot.fetch_user(int(user_id))
                if user:
                    await user.send(message)
                else:
                    logger.error(f"Discord user {user_id} not found")
        if platform == "dashboard" or True: # Always save to DB for history
            await memory_manager.add_message(
                platform=platform,
                user_id=user_id,
                role="assistant",
                content=message,
                metadata={"source": "scheduler"}
            )
        logger.info(f"Proactive message sent to {user_id} on {platform}")
    except Exception as e:
        logger.error(f"Failed to send proactive message: {e}")

async def run_cron_task_worker(platform: str, user_id: str, task_func: Callable):
    """Run a recurring task and send its output"""
    try:
        message = await task_func()
        if message:
            await send_notification_task(platform, user_id, message)
    except Exception as e:
        logger.error(f"Error in cron task execution: {e}")

async def run_ai_job_task(platform: str, user_id: str, prompt: str):
    """Executes a full AI reasoning loop and sends the result to the user"""
    from .memory_manager import memory_manager
    from .ollama_client import ollama_client
    from datetime import datetime
    
    logger.info(f"Running AI Cron Job for {user_id} on {platform}: {prompt[:50]}")
    
    # Fetch recent history to avoid repetition
    history = await memory_manager.get_conversation_history(platform, user_id, limit=5)
    
    # Build context for the AI
    context = {
        "platform": platform,
        "user_id": user_id,
        "current_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    # Enhance prompt with variation instructions
    enhanced_prompt = (
        f"### MISSION BRIEFING:\n{prompt}\n\n"
        "### MISSION DIRECTIVES:\n"
        "1. NO REPETITION: If your history shows you've said this before, pivot to a new angle.\n"
        "2. ACCURACY: If this mission requires news, prices, or status, you MUST check your REAL-TIME VISION.\n"
        f"3. CHRONOS: Current system time is {context['current_time']}.\n"
    )
    
    try:
        # Trigger full reasoning loop with history
        response = await ollama_client.chat_with_tools(
            messages=history + [{"role": "user", "content": enhanced_prompt}],
            context=context
        )
        
        if response:
            logger.info(f"AI Cron Job for {user_id} produced response (length: {len(response)}). Sending...")
            await send_notification_task(platform, user_id, f"### ⚡ **Cron Job Update**\n\n{response}")
            logger.info(f"AI Cron Job for {user_id} delivered.")
        else:
            logger.warning(f"AI Cron Job for {user_id} produced empty response.")
    except Exception as e:
        logger.error(f"Error in AI Cron Job execution: {e}", exc_info=True)

async def run_watcher_task(platform: str, user_id: str, target_url: str):
    """Monitors a URL and notifies the user of status changes"""
    import aiohttp
    
    logger.info(f"Running Watcher for {user_id} on {platform}: {target_url}")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(target_url, timeout=10) as response:
                status = response.status
                if status != 200:
                    await send_notification_task(
                        platform, 
                        user_id, 
                        f"⚠️ **Watchdog Alert!**\n\nTarget `{target_url}` is reporting status: `{status}`."
                    )
    except Exception as e:
        logger.error(f"Watcher failed for {target_url}: {e}")
        await send_notification_task(
            platform, 
            user_id, 
            f"🚨 **Watchdog Failure!**\n\nI couldn't reach `{target_url}`. Error: `{str(e)}`"
        )

# Global scheduler instance
scheduler_manager = SchedulerManager()
