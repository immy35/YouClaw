"""
YouClaw Discord Handler
Handles Discord-specific message processing and bot interactions.
"""

import discord
from discord.ext import commands as discord_commands
import logging
from typing import Optional
from .config import config
from .ollama_client import ollama_client
from .memory_manager import memory_manager
from .search_client import search_client
from .commands import command_handler
import asyncio

logger = logging.getLogger(__name__)


class DiscordHandler:
    """Handles Discord platform integration"""
    
    def __init__(self):
        # Set up Discord intents
        intents = discord.Intents.default()
        intents.message_content = True  # Required to read message content
        intents.messages = True
        intents.guilds = True
        
        self.bot = discord_commands.Bot(command_prefix=config.bot.prefix, intents=intents)
        self.setup_events()
    
    def setup_events(self):
        """Set up Discord event handlers"""
        
        @self.bot.event
        async def on_ready():
            logger.info(f"Discord bot logged in as {self.bot.user}")
            await self.bot.change_presence(
                activity=discord.Activity(
                    type=discord.ActivityType.listening,
                    name="your messages | !help"
                )
            )
        
        @self.bot.event
        async def on_message(message: discord.Message):
            # Ignore messages from the bot itself
            if message.author == self.bot.user:
                return
            
            # Ignore messages from other bots
            if message.author.bot:
                return
            
            # Only respond to DMs or mentions
            is_dm = isinstance(message.channel, discord.DMChannel)
            is_mentioned = self.bot.user in message.mentions
            
            if not (is_dm or is_mentioned):
                return
            
            # Get user info
            user_id = str(message.author.id)
            channel_id = str(message.channel.id) if not is_dm else None
            content = message.content
            
            # Remove mention from content
            if is_mentioned:
                content = content.replace(f"<@{self.bot.user.id}>", "").strip()
            
            # Show typing indicator
            async with message.channel.typing():
                # Check if it's a command
                command_response = await command_handler.handle_command(
                    platform="discord",
                    user_id=user_id,
                    message=content,
                    channel_id=channel_id
                )
                
                if command_response:
                    await self.send_message(message.channel, command_response)
                    return
                
                # Get conversation history
                history = await memory_manager.get_conversation_history(
                    platform="discord",
                    user_id=user_id,
                    channel_id=channel_id
                )
                
                # Add current message to history
                await memory_manager.add_message(
                    platform="discord",
                    user_id=user_id,
                    role="user",
                    content=content,
                    channel_id=channel_id,
                    metadata={"username": str(message.author)}
                )
                
                # Build messages for LLM
                messages = history + [{"role": "user", "content": content}]
                
                # Get user profile and onboarding status
                profile = await memory_manager.get_user_profile(platform="discord", user_id=user_id)
                
                # Check global settings
                search_enabled = (await memory_manager.get_global_setting("search_enabled", "true")).lower() == "true"
                
                # Decide if we need to search
                search_context = None
                if search_enabled and any(word in content.lower() for word in ['search', 'find', 'who is', 'what is', 'latest', 'news']):
                     search_results = await search_client.search(content)
                     search_context = search_results

                # Get AI response with autonomous tool use
                logger.info(f"Starting Discord reasoning loop for user {user_id}...")
                
                try:
                    # Use chat_with_tools for autonomous behavior
                    response = await ollama_client.chat_with_tools(
                        messages=messages,
                        user_profile=profile,
                        context={"user_id": user_id, "platform": "discord"}
                    )
                    
                    if response.strip():
                        await self.send_message(message.channel, response)
                    else:
                        await message.channel.send("Hmm, I'm a bit speechless.")
                    
                    logger.info(f"Reasoning complete for user {user_id}")
                    
                except Exception as e:
                    logger.error(f"Error during Discord reasoning: {e}")
                    error_msg = "Oops, I lost my train of thought. Can we try again?"
                    await message.channel.send(error_msg)
                    response = error_msg
                
                # Simple heuristic to 'complete' onboarding
                if not profile['onboarding_completed']:
                     if len(history) > 2:
                          await memory_manager.update_user_profile(
                               platform="discord", 
                               user_id=user_id, 
                               onboarding_completed=True
                          )
                
                # Save AI response to memory
                await memory_manager.add_message(
                    platform="discord",
                    user_id=user_id,
                    role="assistant",
                    content=response,
                    channel_id=channel_id
                )
    
    async def send_message(self, channel, content: str):
        """Send a message, handling Discord's 2000 char limit"""
        if len(content) <= 2000:
            await channel.send(content)
        else:
            # Split into chunks
            chunks = [content[i:i+2000] for i in range(0, len(content), 2000)]
            for chunk in chunks:
                await channel.send(chunk)
    
    async def start(self):
        """Start the Discord bot"""
        if not config.discord.enabled:
            logger.info("Discord is disabled in config")
            return
        
        logger.info("Starting Discord bot...")
        await self.bot.start(config.discord.token)
    
    async def stop(self):
        """Stop the Discord bot"""
        if self.bot:
            await self.bot.close()
            logger.info("Discord bot stopped")


# Global Discord handler instance
discord_handler = DiscordHandler()
