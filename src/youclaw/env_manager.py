"""
YouClaw Environment Manager
Safely reads and writes to the .env file to allow live configuration updates.
"""

import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class EnvManager:
    """Manages reading and writing to the .env file"""
    
    def __init__(self, env_path: str = None):
        from .config import ENV_PATH
        self.env_path = Path(env_path) if env_path else ENV_PATH
    
    def get_all(self) -> dict:
        """Read all environment variables from the file"""
        if not self.env_path.exists():
            return {}
            
        env_vars = {}
        with open(self.env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, val = line.split('=', 1)
                env_vars[key.strip()] = val.strip()
        return env_vars
        
    def set_key(self, key: str, value: str):
        """Update or add a key-value pair in the .env file"""
        lines = []
        found = False
        
        if self.env_path.exists():
            with open(self.env_path, 'r') as f:
                lines = f.readlines()
                
        for i, line in enumerate(lines):
            line_strip = line.strip()
            if line_strip.startswith(f"{key}="):
                lines[i] = f"{key}={value}\n"
                found = True
                break
                
        if not found:
            # Add with a newline if file is not empty and doesn't end with one
            if lines and not lines[-1].endswith('\n'):
                lines[-1] += '\n'
            lines.append(f"{key}={value}\n")
            
        with open(self.env_path, 'w') as f:
            f.writelines(lines)
            
        logger.info(f"Updated .env: {key}=***")

# Global instance
env_manager = EnvManager()
