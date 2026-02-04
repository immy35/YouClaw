"""
YouClaw Command Handler
Handles bot commands across all platforms.
"""

import logging
from typing import Optional, Dict, Any
from .ollama_client import ollama_client
from .memory_manager import memory_manager

logger = logging.getLogger(__name__)


class CommandHandler:
    """Handles bot commands"""
    
    def __init__(self, prefix: str = "!"):
        self.prefix = prefix
        self.commands = {
            "help": self.cmd_help,
            "reset": self.cmd_reset,
            "model": self.cmd_model,
            "stats": self.cmd_stats,
            "models": self.cmd_models,
        }
    
    def is_command(self, message: str) -> bool:
        """Check if message is a command"""
        return message.strip().startswith(self.prefix) or message.strip().startswith("/")
    
    def parse_command(self, message: str) -> tuple[str, list[str]]:
        """Parse command and arguments"""
        # Remove prefix
        if message.startswith(self.prefix):
            message = message[len(self.prefix):]
        elif message.startswith("/"):
            message = message[1:]
        
        parts = message.strip().split()
        command = parts[0].lower() if parts else ""
        args = parts[1:] if len(parts) > 1 else []
        
        return command, args
    
    async def handle_command(
        self,
        platform: str,
        user_id: str,
        message: str,
        **kwargs
    ) -> Optional[str]:
        """
        Handle a command and return response.
        
        Args:
            platform: Platform name (discord, telegram)
            user_id: User identifier
            message: Command message
            **kwargs: Additional platform-specific data
        
        Returns:
            Response string or None if not a command
        """
        if not self.is_command(message):
            return None
        
        command, args = self.parse_command(message)
        
        if command in self.commands:
            try:
                return await self.commands[command](platform, user_id, args, **kwargs)
            except Exception as e:
                logger.error(f"Error executing command {command}: {e}")
                return f"❌ Error executing command: {str(e)}"
        else:
            return f"❓ Unknown command: `{command}`. Type `{self.prefix}help` for available commands."
    
    async def cmd_help(self, platform: str, user_id: str, args: list, **kwargs) -> str:
        """Show help message"""
        return """🦞 **YouClaw - Your Personal AI Assistant**

**Available Commands:**
• `!help` or `/help` - Show this help message
• `!reset` or `/reset` - Clear conversation history
• `!model [name]` or `/model [name]` - Show or switch AI model
• `!models` or `/models` - List available models
• `!stats` or `/stats` - Show bot statistics

**How to use:**
Just talk to me naturally! I'll remember our conversation and provide intelligent responses using my local AI brain (Ollama).

I work across Discord and Telegram, and I'll remember you on both platforms!"""
    
    async def cmd_reset(self, platform: str, user_id: str, args: list, **kwargs) -> str:
        """Reset conversation history"""
        channel_id = kwargs.get("channel_id")
        await memory_manager.clear_conversation(platform, user_id, channel_id)
        return "🔄 Conversation history cleared! Starting fresh."
    
    async def cmd_model(self, platform: str, user_id: str, args: list, **kwargs) -> str:
        """Show or switch model"""
        if not args:
            # Show current model
            return f"🤖 Current model: `{ollama_client.model}`\n\nUse `!model <name>` to switch models."
        
        # Switch model
        model_name = args[0]
        success = await ollama_client.switch_model(model_name)
        
        if success:
            return f"✅ Switched to model: `{model_name}`"
        else:
            models = await ollama_client.get_available_models()
            models_list = "\n• ".join(models) if models else "None"
            return f"❌ Model `{model_name}` not found.\n\n**Available models:**\n• {models_list}"
    
    async def cmd_models(self, platform: str, user_id: str, args: list, **kwargs) -> str:
        """List available models"""
        models = await ollama_client.get_available_models()
        
        if not models:
            return "❌ No models found. Make sure Ollama is running and has models installed."
        
        current = ollama_client.model
        models_list = "\n".join([
            f"• `{m}` {'← current' if m == current else ''}"
            for m in models
        ])
        
        return f"🤖 **Available Models:**\n{models_list}\n\nUse `!model <name>` to switch."
    
    async def cmd_stats(self, platform: str, user_id: str, args: list, **kwargs) -> str:
        """Show bot statistics"""
        stats = await memory_manager.get_stats()
        health = await ollama_client.check_health()
        
        return f"""📊 **YouClaw Statistics**

**Memory:**
• Total messages: {stats['total_messages']}
• Unique users: {stats['unique_users']}
• Database: `{stats['database_path']}`

**AI Engine:**
• Model: `{ollama_client.model}`
• Status: {'🟢 Online' if health else '🔴 Offline'}
• Host: `{ollama_client.host}`"""


# Global command handler instance
command_handler = CommandHandler()
