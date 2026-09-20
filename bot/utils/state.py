"""
State management for per-guild bot state.
"""
import json
import asyncio
import logging
import aiofiles
import aiofiles.os
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class StateManager:
    """Manager for persisting and retrieving per-guild state."""
    
    def __init__(self, state_dir: Path):
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[int, Dict[str, Any]] = {}
        self._locks: Dict[int, asyncio.Lock] = {}
        
    def _get_lock(self, guild_id: int) -> asyncio.Lock:
        if guild_id not in self._locks:
            self._locks[guild_id] = asyncio.Lock()
        return self._locks[guild_id]
        
    def _get_path(self, guild_id: int) -> Path:
        return self.state_dir / f"guild_{guild_id}.json"

    async def load_guild(self, guild_id: int) -> Dict[str, Any]:
        """
        Load state for a specific guild.
        
        Args:
            guild_id: The Discord guild ID.
            
        Returns:
            Dict containing the guild state.
        """
        async with self._get_lock(guild_id):
            if guild_id in self._cache:
                return self._cache[guild_id].copy()
                
            path = self._get_path(guild_id)
            state = {
                "volume": 75,
                "loop_mode": "off",
                "last_playlist": None
            }
            
            if path.exists():
                try:
                    async with aiofiles.open(path, 'r', encoding='utf-8') as f:
                        content = await f.read()
                        data = json.loads(content)
                        state.update(data)
                except Exception as e:
                    logger.error(f"Failed to load state for guild {guild_id}: {e}")
                    
            self._cache[guild_id] = state
            return state.copy()

    async def save_guild(self, guild_id: int, state: Dict[str, Any]) -> None:
        """
        Save state for a specific guild atomically.
        
        Args:
            guild_id: The Discord guild ID.
            state: The state dictionary to save.
        """
        async with self._get_lock(guild_id):
            self._cache[guild_id] = state.copy()
            
            path = self._get_path(guild_id)
            temp_path = path.with_suffix('.tmp')
            
            try:
                # Write to temp file first
                async with aiofiles.open(temp_path, 'w', encoding='utf-8') as f:
                    await f.write(json.dumps(state, indent=2))
                    
                # Rename atomically
                await aiofiles.os.replace(temp_path, path)
            except Exception as e:
                logger.error(f"Failed to save state for guild {guild_id}: {e}")
                if temp_path.exists():
                    try:
                        await aiofiles.os.remove(temp_path)
                    except Exception:
                        pass
