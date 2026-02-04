"""
YouClaw Vector Manager
Handles semantic search and embedding storage for long-term memory.
"""

import logging
import json
import numpy as np
from typing import List, Dict, Any, Optional
import aiosqlite
import base64
from .ollama_client import ollama_client

logger = logging.getLogger(__name__)

class VectorManager:
    """Manages semantic memory using vector embeddings"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.db: Optional[aiosqlite.Connection] = None

    async def initialize(self):
        """Initialize the vector database table"""
        self.db = await aiosqlite.connect(self.db_path)
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS vector_memory (
                message_id INTEGER PRIMARY KEY,
                embedding BLOB NOT NULL,
                FOREIGN KEY (message_id) REFERENCES conversations (id)
            )
        """)
        await self.db.commit()
        logger.info("Vector manager initialized")

    @staticmethod
    def _encode_vector(vec: List[float]) -> bytes:
        """Encode list of floats to binary for storage"""
        return np.array(vec, dtype=np.float32).tobytes()

    @staticmethod
    def _decode_vector(bin_vec: bytes) -> np.ndarray:
        """Decode binary back to numpy array"""
        return np.frombuffer(bin_vec, dtype=np.float32)

    async def save_embedding(self, message_id: int, text: str):
        """Generate and save embedding for a message"""
        embedding = await ollama_client.get_embeddings(text)
        if not embedding:
            logger.warning(f"Failed to generate embedding for message {message_id}")
            return

        bin_vec = self._encode_vector(embedding)
        await self.db.execute(
            "INSERT OR REPLACE INTO vector_memory (message_id, embedding) VALUES (?, ?)",
            (message_id, bin_vec)
        )
        await self.db.commit()

    async def search_semantic(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Search for semantically similar messages"""
        query_vec = await ollama_client.get_embeddings(query)
        if not query_vec:
            return []

        query_np = np.array(query_vec, dtype=np.float32)
        
        # This is a brute-force search (fine for small local DBs)
        # For larger DBs, we'd use HNSW or Faiss
        results = []
        async with self.db.execute("""
            SELECT vm.message_id, vm.embedding, c.content, c.role, c.timestamp 
            FROM vector_memory vm
            JOIN conversations c ON vm.message_id = c.id
        """) as cursor:
            async for msg_id, bin_vec, content, role, ts in cursor:
                msg_vec = self._decode_vector(bin_vec)
                
                # Cosine similarity
                similarity = np.dot(query_np, msg_vec) / (np.linalg.norm(query_np) * np.linalg.norm(msg_vec))
                
                results.append({
                    "id": msg_id,
                    "content": content,
                    "role": role,
                    "timestamp": ts,
                    "similarity": float(similarity)
                })

        # Sort by similarity and return top N
        results.sort(key=lambda x: x['similarity'], reverse=True)
        return results[:limit]

# The instance will be managed by memory_manager to avoid circular imports
