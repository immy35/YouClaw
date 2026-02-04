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
        self.pending_approvals: Dict[str, Dict[str, Any]] = {}  # Format: {request_id: {name, args, ...}}
        self.dynamic_dir = "dynamic_skills"
        if not os.path.exists(self.dynamic_dir):
            os.makedirs(self.dynamic_dir)
    
    def skill(self, name: str = None, description: str = None, admin_only: bool = False, risk_level: str = "LOW"):
        """
        Decorator to register a function as a skill.
        
        Args:
            name: Optional custom name
            description: Optional description
            admin_only: If True, restricted to admin users
            risk_level: "LOW" (safe), "MEDIUM", or "HIGH" (requires approval)
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
                "admin_only": admin_only,
                "risk_level": risk_level
            }
            
            logger.info(f"registered skill: {skill_name} (risk: {risk_level}, admin: {admin_only})")
            
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

    async def execute_skill(self, name: str, arguments: Dict[str, Any], bypass_security: bool = False) -> Any:
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

                logger.warning(f"🛑 Security Alert: Unauthorized access attempt to '{name}' by {current_id}")
                return f"Permission Denied: Skill '{name}' is reserved for the bot administrator."

        # Security: Iron Dome Interception
        if not bypass_security and skill.get('risk_level') == "HIGH":
            import uuid
            request_id = str(uuid.uuid4())[:8]
            self.pending_approvals[request_id] = {
                "name": name,
                "arguments": arguments,
                "timestamp": __import__('time').time(),
                "initiator": arguments.get('user_id', 'unknown')
            }
            logger.info(f"🛡️ Iron Dome Intercepted {name}: Pending Approval {request_id}")
            # Return a special signal string that the Handler will parse
            return f"[SECURITY_INTERCEPT] ID:{request_id} COMMAND:{name}"

        try:
            # Filter arguments to verify they match function signature
            valid_args = {}
            for param_name in skill['parameters']:
                if param_name in arguments:
                    valid_args[param_name] = arguments[param_name]
            
            logger.info(f"Executing skill '{name}' with filtered args: {valid_args}")
            if skill['is_async']:
                result = await skill['func'](**valid_args)
            else:
                result = skill['func'](**valid_args)
            return result
        except Exception as e:
            logger.error(f"Error executing skill '{name}': {e}", exc_info=True)
            return f"Error: {str(e)}"

            logger.error(f"Error executing skill '{name}': {e}", exc_info=True)
            return f"Error: {str(e)}"

    async def confirm_execution(self, request_id: str) -> str:
        """Confirm and execute a pending skill"""
        if request_id not in self.pending_approvals:
            return "Error: Request expired or invalid."
            
        data = self.pending_approvals.pop(request_id)
        logger.info(f"✅ Iron Dome Approved: Executing {data['name']}")
        return await self.execute_skill(data['name'], data['arguments'], bypass_security=True)

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
