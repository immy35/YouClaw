"""
YouClaw Skill Manager
A system to register and execute bot capabilities (skills).
"""

import logging
import inspect
import functools
import json
import os
import importlib.util
from typing import Dict, Any, Callable, List, Optional

logger = logging.getLogger(__name__)

class SkillManager:
    """Manages bot skills and tool registration"""
    
    def __init__(self):
        self.skills: Dict[str, Dict[str, Any]] = {}
        self.dynamic_dir = "dynamic_skills"
        if not os.path.exists(self.dynamic_dir):
            os.makedirs(self.dynamic_dir)
    
    def skill(self, name: str = None, description: str = None, admin_only: bool = False):
        """
        Decorator to register a function as a skill.
        
        Args:
            name: Optional custom name for the skill (defaults to function name)
            description: Optional description (defaults to function docstring)
        """
        def decorator(func: Callable):
            skill_name = name or func.__name__
            skill_description = description or (func.__doc__.strip() if func.__doc__ else "No description available")
            
            # Extract parameters from signature
            sig = inspect.signature(func)
            parameters = {}
            for param_name, param in sig.parameters.items():
                parameters[param_name] = {
                    "type": str(param.annotation) if param.annotation != inspect.Parameter.empty else "string",
                    "default": param.default if param.default != inspect.Parameter.empty else None,
                    "required": param.default == inspect.Parameter.empty
                }
            
            self.skills[skill_name] = {
                "name": skill_name,
                "description": skill_description,
                "func": func,
                "parameters": parameters,
                "is_async": inspect.iscoroutinefunction(func),
                "admin_only": admin_only # Added admin_only flag
            }
            
            logger.info(f"registered skill: {skill_name} (admin_only: {admin_only})")
            
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                return func(*args, **kwargs)
            return wrapper
            
        return decorator

    async def get_skills_doc(self) -> str:
        """Get tool definitions as a string for LLM prompting"""
        tools_list = []
        for name, info in self.skills.items():
            params_str = ", ".join([f"{k} ({v['type']}{', required' if v['required'] else ''})" for k, v in info['parameters'].items()])
            tools_list.append(f"- {name}: {info['description']}\n  Params: {params_str}")
        
        return "\n".join(tools_list)

    def get_tool_definitions(self) -> str:
        # Legacy support
        return self.get_skills_doc()

    async def execute_skill(self, name: str, arguments: Dict[str, Any]) -> Any:
        """Execute a registered skill by name"""
        if name not in self.skills:
            return f"Error: Skill '{name}' not found"
        
        skill = self.skills[name]
        
        # Security: Admin-only skill gating
        if skill.get('admin_only'):
            platform = arguments.get('platform')
            user_id = arguments.get('user_id')
            
            # For now, we'll use a simple check. We could also check the DB users table.
            from .config import config
            admin_id = config.bot.admin_user_identity # e.g. "telegram:123456"
            current_id = f"{platform}:{user_id}"
            
            if current_id != admin_id:
                logger.warning(f"🛑 Security Alert: Unauthorized access attempt to '{name}' by {current_id}")
                return f"Permission Denied: Skill '{name}' is reserved for the bot administrator."

        try:
            logger.info(f"Executing skill '{name}' with args: {arguments}")
            if skill['is_async']:
                result = await skill['func'](**arguments)
            else:
                result = skill['func'](**arguments)
            return result
        except Exception as e:
            logger.error(f"Error executing skill '{name}': {e}", exc_info=True)
            return f"Error: {str(e)}"

    def load_dynamic_skills(self):
        """Scan dynamic_skills folder and import them"""
        logger.info(f"Scanning for dynamic skills in {self.dynamic_dir}...")
        for filename in os.listdir(self.dynamic_dir):
            if filename.endswith(".py") and not filename.startswith("__"):
                skill_name = filename[:-3]
                path = os.path.join(self.dynamic_dir, filename)
                
                try:
                    spec = importlib.util.spec_from_file_location(skill_name, path)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    logger.info(f"Loaded dynamic skill: {skill_name}")
                except Exception as e:
                    logger.error(f"Failed to load dynamic skill {skill_name}: {e}")

# Global skill manager instance
skill_manager = SkillManager()
