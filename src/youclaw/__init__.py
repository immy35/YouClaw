"""
YouClaw - Your Personal AI Assistant
Universal Neural Core for Telegram, Discord, and Web Dashboard
"""

__version__ = "4.8.9"
__author__ = "Imran"

from .bot import youclaw_bot, main
from .config import config
from .memory_manager import memory_manager
from .ollama_client import ollama_client
from .scheduler_manager import scheduler_manager
from .skills_manager import skill_manager

__all__ = [
    "youclaw_bot",
    "main",
    "config",
    "memory_manager",
    "ollama_client",
    "scheduler_manager",
    "skill_manager",
]
