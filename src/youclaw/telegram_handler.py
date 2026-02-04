"""
YouClaw Telegram Handler
Handles Telegram-specific message processing and bot interactions.
"""

from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
import logging
import asyncio
from typing import Optional
from .config import config
from .ollama_client import ollama_client
from .memory_manager import memory_manager
from .search_client import search_client
from .commands import command_handler
import base64
import io

logger = logging.getLogger(__name__)


class TelegramHandler:
    """Handles Telegram platform integration"""
    
    def __init__(self):
        self.app: Optional[Application] = None
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming Telegram messages"""
        if not update.message or not update.message.text:
            return
        
        # Get user info
        user_id = str(update.effective_user.id)
        chat_id = str(update.effective_chat.id)
        content = update.message.text
        username = update.effective_user.username or update.effective_user.first_name
        
        # Send typing action
        await update.message.chat.send_action("typing")
        
        # Check if it's a command
        command_response = await command_handler.handle_command(
            platform="telegram",
            user_id=user_id,
            message=content,
            channel_id=chat_id
        )
        
        if command_response:
            await self.send_message(update, command_response)
            return
        
        # Get user profile and onboarding status
        profile = await memory_manager.get_user_profile(platform="telegram", user_id=user_id)
        
        # Get conversation history
        history = await memory_manager.get_conversation_history(
            platform="telegram",
            user_id=user_id,
            channel_id=chat_id
        )
        
        # Add current message to history
        await memory_manager.add_message(
            platform="telegram",
            user_id=user_id,
            role="user",
            content=content,
            channel_id=chat_id,
            metadata={"username": username}
        )
        
        # Build messages for LLM
        messages = history + [{"role": "user", "content": content}]
        
        # Get AI response
        logger.info(f"Starting generic chat for user {user_id}...")
        
        try:
            # Use autonomous reasoning loop with tools (Reminders, etc.)
            response = await ollama_client.chat_with_tools(
                messages=messages,
                user_profile=profile,
                context={"platform": "telegram", "user_id": user_id}
            )
            
            if response and response.strip():
                await self.send_message(update, response)
            else:
                await update.message.reply_text("Hmm, I'm not sure what to say.")
            
            logger.info(f"Chat complete for user {user_id}")
            
        except Exception as e:
            logger.error(f"Error during reasoning: {e}")
            error_msg = "I'm sorry, I hit a snag while thinking. Can you try again?"
            await update.message.reply_text(error_msg)
            response = error_msg
        
        # Simple heuristic to 'complete' onboarding if they gave personal info
        if not profile['onboarding_completed']:
             if len(history) > 2:
                  await memory_manager.update_user_profile(
                       platform="telegram", 
                       user_id=user_id, 
                       onboarding_completed=True
                  )
        
        # Save AI response to memory
        await memory_manager.add_message(
            platform="telegram",
            user_id=user_id,
            role="assistant",
            content=response,
            channel_id=chat_id
        )
    
    async def send_message(self, update: Update, content: str):
        """Send a message, handling Telegram's 4096 char limit"""
        if len(content) <= 4096:
            await update.message.reply_text(content)
        else:
            # Split into chunks
            chunks = [content[i:i+4096] for i in range(0, len(content), 4096)]
            for chunk in chunks:
                await update.message.reply_text(chunk)
    
    async def start(self):
        """Start the Telegram bot"""
        if not config.telegram.enabled:
            logger.info("Telegram is disabled in config")
            return
        
        logger.info("Starting Telegram bot...")
        
        # Create application
        self.app = Application.builder().token(config.telegram.token).build()
        
        # Add message handler
        self.app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message)
        )
        
        # Add command handler for /start
        async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
            await update.message.reply_text(
                "🦞 **YouClaw - Your Personal AI Assistant**\n\n"
                "Hello! I'm YouClaw, powered by local AI (Ollama).\n\n"
                "Just send me a message and I'll respond intelligently. "
                "I remember our conversations!\n\n"
                "Type /help to see available commands."
            )
        
        from telegram.ext import CommandHandler
        self.app.add_handler(CommandHandler("start", start_command))
        
        # Start polling
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling()
        
        logger.info("Telegram bot started")
        
        # Keep alive until cancelled
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            logger.info("Telegram handler task cancelled")
    
    async def stop(self):
        """Stop the Telegram bot"""
        if self.app:
            await self.app.updater.stop()
            await self.app.stop()
            await self.app.shutdown()
            logger.info("Telegram bot stopped")


# Global Telegram handler instance
telegram_handler = TelegramHandler()
