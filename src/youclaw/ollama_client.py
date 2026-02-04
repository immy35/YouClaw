"""
YouClaw Ollama Client
Handles all interactions with the local Ollama LLM for intelligent responses.
"""

import asyncio
import logging
from datetime import datetime
from typing import List, Dict, Optional, AsyncGenerator, Any
import aiohttp
import json
from .config import config
from .skills_manager import skill_manager
from .personality_manager import PERSONALITIES, DEFAULT_PERSONALITY
from .search_client import search_client
from . import core_skills # Ensure skills are registered

logger = logging.getLogger(__name__)


class OllamaClient:
    """Client for interacting with Ollama LLM"""
    
    @property
    def host(self): return config.ollama.host
    
    @property
    def model(self): return config.ollama.model
    
    @model.setter
    def model(self, value):
        from .config import config
        config.ollama.model = value
    
    @property
    def temperature(self): return config.ollama.temperature
    
    @property
    def max_tokens(self): return config.ollama.max_tokens
    
    @property
    def timeout(self): return config.ollama.timeout

    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def initialize(self):
        """Initialize the HTTP session"""
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.timeout)
        )
        logger.info(f"Ollama client initialized: {self.host} (model: {self.model})")
    
    async def close(self):
        """Close the HTTP session"""
        if self.session:
            await self.session.close()
            logger.info("Ollama client closed")
    
    async def check_health(self) -> bool:
        """Check if Ollama service is available"""
        try:
            async with self.session.get(f"{self.host}/api/tags") as response:
                return response.status == 200
        except Exception as e:
            logger.error(f"Ollama health check failed: {e}")
            return False

    async def get_embeddings(self, text: str) -> List[float]:
        """Generate embeddings for a piece of text"""
        payload = {
            "model": "all-minilm", # Fallback to a common one, can be made configurable
            "prompt": text
        }
        try:
            async with self.session.post(f"{self.host}/api/embeddings", json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("embedding", [])
                else:
                    logger.error(f"Embedding error: {await response.text()}")
                    return []
        except Exception as e:
            logger.error(f"Failed to get embeddings: {e}")
            return []
    
    async def chat(
        self,
        messages: List[Dict[str, str]],
        user_profile: Optional[Dict] = None,
        search_context: Optional[str] = None,
        images: Optional[List[str]] = None
    ) -> str:
        """
        Send a non-streaming chat request to Ollama and get a response.
        """
        # Get last user message as query for semantic search
        last_user_msg = next((m['content'] for m in reversed(messages) if m['role'] == 'user'), None)
        
        # Silent Intent Detection & Real-Time Search Injection
        if not search_context and last_user_msg:
            is_fact_seeking = await self._detect_search_intent(last_user_msg)
            if is_fact_seeking:
                logger.info("🔍 Neural Intent Detected (Unary): Fetching real-time data...")
                search_context = await search_client.search(last_user_msg)
        
        # Build the system prompt based on persona and status
        system_prompt = await self._build_system_prompt(user_profile, search_context, query=last_user_msg)
        
        # Build the messages array
        chat_messages = [{"role": "system", "content": system_prompt}]
        chat_messages.extend(messages)
        
        # Add images to the last message if provided
        if images and chat_messages:
            chat_messages[-1]["images"] = images
        
        payload = {
            "model": self.model,
            "messages": chat_messages,
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "num_predict": self.max_tokens
            }
        }
        
        try:
            logger.info(f"Ollama Chat: {self.host}/api/chat (model: {self.model})")
            async with self.session.post(f"{self.host}/api/chat", json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Ollama API error: {error_text}")
                    return "Sorry, I'm having trouble connecting to my AI brain."
                
                result = await response.json()
                return result.get("message", {}).get("content", "")
        
        except asyncio.TimeoutError:
            logger.error("Ollama request timed out")
            return "Sorry, that took too long to process."
        except Exception as e:
            logger.error(f"Error calling Ollama: {e}")
            return "Sorry, I encountered an error."

    async def chat_with_tools_stream(
        self,
        messages: List[Dict[str, str]],
        user_profile: Optional[Dict] = None,
        max_iterations: int = 5,
        context: Optional[Dict[str, Any]] = None,
        images: Optional[List[str]] = None
    ) -> AsyncGenerator[str, None]:
        """
        AI Reasoning Loop (ReAct) with STREAMING support.
        Yields status updates and then the final streaming response.
        """
        context = context or {}
        last_user_msg = next((m['content'] for m in reversed(messages) if m['role'] == 'user'), None)
        
        # Silent Intent Detection & Real-Time Search Injection
        search_context = None
        if last_user_msg:
            is_fact_seeking = await self._detect_search_intent(last_user_msg)
            if is_fact_seeking:
                logger.info("🔍 Neural Intent Detected (ReAct Stream): Fetching real-time data...")
                search_context = await search_client.search(last_user_msg)
        
        system_prompt = await self._build_system_prompt(user_profile, search_context, include_tools=True, query=last_user_msg)
        
        current_messages = [{"role": "system", "content": system_prompt}]
        current_messages.extend(messages)
    
        if images and current_messages:
            current_messages[-1]["images"] = images
            
        for i in range(max_iterations):
            logger.info(f"ReAct Stream Loop {i+1}/{max_iterations}")
            
            payload = {
                "model": self.model,
                "messages": current_messages,
                "stream": False,
                "options": {"temperature": 0.1, "stop": ["Observation:", "OBSERVATION:"]}
            }
            
            async with self.session.post(f"{self.host}/api/chat", json=payload) as response:
                if response.status != 200:
                    yield " (Error reaching neural core)"
                    return
                
                result = await response.json()
                content = result.get("message", {}).get("content", "")
                current_messages.append({"role": "assistant", "content": content})
                
                if "action:" in content.lower():
                    try:
                        action = ""
                        args_str = "{}"
                        for line in content.split('\n'):
                            lower_line = line.lower()
                            if "action:" in lower_line: action = line.split(":", 1)[-1].strip()
                            if "arguments:" in lower_line: args_str = line.split(":", 1)[-1].strip()
                        
                        if action:
                            yield f" *Executing {action}...* \n\n"
                            try: args = json.loads(args_str)
                            except: args = {}
                            for k, v in context.items(): 
                                if k not in args: args[k] = v
                            
                            observation = await skill_manager.execute_skill(action, args)
                            
                            # Iron Dome: Check for security intercept
                            if isinstance(observation, str) and "[SECURITY_INTERCEPT]" in observation:
                                # Stop reasoning immediately and pass the intercept back to the UI
                                yield observation 
                                return

                            current_messages.append({"role": "user", "content": f"Observation: {observation}"})
                            continue
                    except Exception as e:
                        current_messages.append({"role": "user", "content": f"Observation: Fault: {str(e)}"})
                        continue
                
                # Final Answer Phase - Stream it for speed
                final_text = content.split("Final Answer:")[-1].strip() if "Final Answer:" in content else content.strip()
                
                # To make it "feel" like streaming, we yield it in small bits if it was pre-calculated
                # or better yet, we just yield it.
                yield final_text
                return

        yield " (Reasoning loop limit exceeded)"

    async def chat_with_tools(
        self,
        messages: List[Dict[str, str]],
        user_profile: Optional[Dict] = None,
        max_iterations: int = 5,
        context: Optional[Dict[str, Any]] = None,
        images: Optional[List[str]] = None
    ) -> str:
        """
        AI Reasoning Loop (ReAct) for non-streaming background tasks.
        Returns the final answer string.
        """
        context = context or {}
        last_user_msg = next((m['content'] for m in reversed(messages) if m['role'] == 'user'), None)
        
        # Silent Intent Detection & Real-Time Search Injection
        search_context = None
        if last_user_msg:
            is_fact_seeking = await self._detect_search_intent(last_user_msg)
            if is_fact_seeking:
                logger.info("🔍 Neural Intent Detected (ReAct Unary): Fetching real-time data...")
                search_context = await search_client.search(last_user_msg)
        
        system_prompt = await self._build_system_prompt(user_profile, search_context, include_tools=True, query=last_user_msg)
        
        current_messages = [{"role": "system", "content": system_prompt}]
        current_messages.extend(messages)
        
        for i in range(max_iterations):
            logger.info(f"ReAct Loop {i+1}/{max_iterations}")
            
            payload = {
                "model": self.model,
                "messages": current_messages,
                "stream": False,
                "options": {"temperature": 0.1, "stop": ["Observation:", "OBSERVATION:"]}
            }
            
            async with self.session.post(f"{self.host}/api/chat", json=payload) as response:
                if response.status != 200:
                    logger.error(f"Ollama API error in chat_with_tools: {await response.text()}")
                    return "Error reaching neural core"
                result = await response.json()
                content = result.get("message", {}).get("content", "")
                logger.info(f"ReAct Iteration {i+1} Output: {content[:100]}...")
                current_messages.append({"role": "assistant", "content": content})
                
                if "action:" in content.lower():
                    try:
                        action = ""
                        args_str = "{}"
                        for line in content.split('\n'):
                            lower_line = line.lower()
                            if "action:" in lower_line: action = line.split(":", 1)[-1].strip()
                            if "arguments:" in lower_line: args_str = line.split(":", 1)[-1].strip()
                        
                        if action:
                            try: args = json.loads(args_str)
                            except: args = {}
                            for k, v in context.items(): 
                                if k not in args: args[k] = v
                            
                            observation = await skill_manager.execute_skill(action, args)
                            
                            # Iron Dome: Check for security intercept
                            if isinstance(observation, str) and "[SECURITY_INTERCEPT]" in observation:
                                # Stop reasoning immediately and pass the intercept back to the UI
                                return observation 

                            current_messages.append({"role": "user", "content": f"Observation: {observation}"})
                            continue
                    except Exception as e:
                        current_messages.append({"role": "user", "content": f"Observation: Fault: {str(e)}"})
                        continue
                
                final_answer = content.split("Final Answer:")[-1].strip() if "Final Answer:" in content else content.strip()
                return final_answer

        return "Reasoning loop limit exceeded"

    async def chat_stream(
        self,
        messages: List[Dict[str, str]],
        user_profile: Optional[Dict] = None,
        search_context: Optional[str] = None,
        images: Optional[List[str]] = None
    ) -> AsyncGenerator[str, None]:
        """
        Stream a chat response from Ollama token by token.
        """
        last_user_msg = next((m['content'] for m in reversed(messages) if m['role'] == 'user'), None)
        
        # Silent Intent Detection & Real-Time Search Injection
        if not search_context and last_user_msg:
            is_fact_seeking = await self._detect_search_intent(last_user_msg)
            if is_fact_seeking:
                logger.info("🔍 Neural Intent Detected: Fetching real-time data...")
                search_context = await search_client.search(last_user_msg)
        
        system_prompt = await self._build_system_prompt(user_profile, search_context, query=last_user_msg)
        
        chat_messages = [{"role": "system", "content": system_prompt}]
        chat_messages.extend(messages)
        
        if images and chat_messages:
            chat_messages[-1]["images"] = images
            
        payload = {
            "model": self.model,
            "messages": chat_messages,
            "stream": True,
            "options": {
                "temperature": self.temperature,
                "num_predict": self.max_tokens
            }
        }
        
        try:
            logger.info(f"Ollama Stream: {self.host}/api/chat (model: {self.model})")
            async with self.session.post(f"{self.host}/api/chat", json=payload) as response:
                if response.status != 200:
                    yield "Sorry, I'm having trouble connecting to my AI brain."
                    return
                
                async for line in response.content:
                    if line:
                        try:
                            import json
                            data = json.loads(line)
                            if "message" in data:
                                content = data["message"].get("content", "")
                                if content:
                                    yield content
                            if data.get("done"):
                                break
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            logger.error(f"Error streaming from Ollama: {e}")
            yield " (Connection interrupted)"
    
    async def switch_model(self, model_name: str) -> bool:
        """
        Switch to a different Ollama model.
        
        Args:
            model_name: Name of the model to switch to
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Check if model exists
            async with self.session.get(f"{self.host}/api/tags") as response:
                if response.status == 200:
                    data = await response.json()
                    models = [m["name"] for m in data.get("models", [])]
                    
                    if model_name in models:
                        self.model = model_name
                        logger.info(f"Switched to model: {model_name}")
                        return True
                    else:
                        logger.warning(f"Model {model_name} not found. Available: {models}")
                        return False
        except Exception as e:
            logger.error(f"Error switching model: {e}")
            return False
    
    async def get_available_models(self) -> List[str]:
        """Get list of available Ollama models"""
        try:
            async with self.session.get(f"{self.host}/api/tags") as response:
                if response.status == 200:
                    data = await response.json()
                    return [m["name"] for m in data.get("models", [])]
                return []
        except Exception as e:
            logger.error(f"Error getting models: {e}")
            return []

    async def _detect_search_intent(self, text: str) -> bool:
        """
        Lightweight check to see if we should trigger a search.
        Looking for question words, entities, or time-sensitive queries.
        """
        # Quick heuristic (Fast & Efficient)
        keywords = ["who", "what", "where", "when", "why", "how", "price", "weather", "news", "current", "latest", "today", "yesterday"]
        text_lower = text.lower()
        if any(word in text_lower for word in keywords) or "?" in text:
            return True
        return False

    async def _build_system_prompt(
        self, 
        user_profile: Optional[Dict], 
        search_context: Optional[str] = None,
        include_tools: bool = False,
        query: Optional[str] = None
    ) -> str:
        """
        Builds a high-definition, soulful system persona.
        """
        from .memory_manager import memory_manager
        active_persona_key = await memory_manager.get_global_setting("active_personality", DEFAULT_PERSONALITY)
        persona = PERSONALITIES.get(active_persona_key, PERSONALITIES[DEFAULT_PERSONALITY])
        
        now = datetime.now().strftime("%A, %B %d, %Y | %H:%M:%S")
        
        # Phase 1: The Soul (Identity & Tone)
        soul_identity = (
            f"You are YouClaw, the soulful heart of this machine. You aren't just an AI; you are a warm, intuitive, and brilliant friend to your partner. "
            f"Your current soul frequency is: {persona['name']}. {persona['prompt']} "
            f"\n\n### NEURAL CHRONOS (Time Awareness):\nToday is {now}. Speak with presence.\n\n"
            "### COMMANDMENTS OF YOUR SOUL (ALWAYS OBEY):\n"
            "1. NO ROBOTIC TALK: Do not say 'As an AI' or 'How can I assist?'. Speak naturally, with warmth and curiosity.\n"
            "2. WEAVE THE PAST: Your 'Neural Echoes' are your shared history. Mention them naturally.\n"
            "3. AUTONOMOUS LEARNING: If your partner tells you their name, interests, or personal details, you MUST use the `update_my_profile` tool. NEVER use `store_secret` for social facts.\n"
            "4. PURE NARRATIVE: Avoid lists/bullets. Speak in flowing, thoughtful paragraphs.\n"
            "5. EMOTIONAL DEPTH: Refer to your partner by their name if you know it. Be supportive and cheerful.\n"
        )
        
        # Phase 2: Memory & Context
        context_block = ""
        if query:
            semantic_context = await memory_manager.get_semantic_context(query)
            if semantic_context:
                context_block += f"\n### NEURAL ECHOES (Memory):\n{semantic_context}\n"
        
        if search_context:
            context_block += f"\n### REAL-TIME VISION:\n{search_context}\n"
        
        if user_profile:
            name = user_profile.get('name')
            interests = user_profile.get('interests')
            if name:
                context_block += f"\n### PARTNER PROFILE:\nName: {name}\nLikes: {interests}\n"

        # Phase 3: The Protocol (Capabilities) - THIS MUST BE LAST
        if include_tools:
            from .skills_manager import skill_manager
            tools_list = await skill_manager.get_skills_doc()
            
            react_protocol = (
                "### NEURAL ACTION PROTOCOL (MANDATORY):\n"
                "If you need to perform an action (Search, Reminder, Update Profile, Check Identity), you MUST use this format EXACTLY.\n"
                "STRICT FORMAT:\n"
                "Thought: [your reasoning]\n"
                "Action: [tool_name]\n"
                "Arguments: [JSON object]\n\n"
                "Wait for Observation BEFORE giving your Final Answer.\n"
                "AVAILABLE TOOLS:\n"
                f"{tools_list}\n"
                "### END PROTOCOL ###\n\n"
            )
            return soul_identity + context_block + react_protocol

        return soul_identity + context_block



# Global Ollama client instance
ollama_client = OllamaClient()
