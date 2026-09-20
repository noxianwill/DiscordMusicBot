"""
Bot factory and main MusicBot class for the Discord Music Bot.
"""

import logging
from pathlib import Path
from typing import Optional, Dict, Any

import discord as discord_py
from discord.ext import commands

from bot.config import BotConfig
from bot.playlists.manager import PlaylistManager
from bot.discord.presence import PresenceManager
from bot.utils.state import StateManager
from bot.youtube.service import YouTubeService

__version__ = "1.0.0"

logger = logging.getLogger(__name__)


class MusicBot(commands.Bot):
    """Main Discord bot instance with audio playback capabilities."""

    def __init__(self, config: BotConfig):
        intents = discord_py.Intents.default()
        intents.message_content = True
        intents.voice_states = True

        super().__init__(
            command_prefix=config.command_prefix,
            intents=intents,
            help_command=None
        )
        self.config = config
        self._players: Dict[int, Any] = {}
        self.playlist_manager: Optional[PlaylistManager] = None
        self.presence_manager: Optional[PresenceManager] = None
        self.state_manager: Optional[StateManager] = None
        self.youtube_service: Optional[YouTubeService] = None

    async def setup_hook(self):
        """Initializes services, loads extensions, and syncs application commands."""
        logger.info("Setting up MusicBot services...")

        # Initialize playlist manager
        self.playlist_manager = PlaylistManager(
            playlists_dir=self.config.playlists_directory,
            supported_extensions=self.config.supported_extensions_set()
        )
        try:
            await self.playlist_manager.load()
        except Exception as e:
            logger.warning(f"Failed to load playlists during startup: {e}")

        # Initialize presence manager
        self.presence_manager = PresenceManager(
            self,
            idle_status=self.config.idle_status,
            playing_status_template=self.config.playing_status
        )

        # Initialize state manager
        state_dir = self.config.data_directory / "state"
        self.state_manager = StateManager(state_dir)

        # Initialize YouTube service
        yt_config = {
            'client_id': self.config.youtube_client_id,
            'client_secret': self.config.youtube_client_secret,
            'token_path': self.config.data_directory / "tokens" / "youtube_token.json",
            'auth_mode': self.config.youtube_auth_mode
        }
        self.youtube_service = YouTubeService(yt_config)

        # Load extension cogs
        extensions = [
            'bot.commands.playback',
            'bot.commands.queue',
            'bot.commands.playlist',
            'bot.commands.youtube',
            'bot.commands.general',
            'bot.discord.events',
        ]

        for ext in extensions:
            try:
                await self.load_extension(ext)
                logger.info(f"Loaded extension {ext}")
            except Exception as e:
                logger.error(f"Failed to load extension {ext}: {e}")

        try:
            await self.tree.sync()
            logger.info("Application command tree synced successfully.")
        except Exception as e:
            logger.error(f"Failed to sync command tree: {e}")


def create_bot(config: BotConfig) -> MusicBot:
    """
    Factory function to instantiate a configured MusicBot.

    Args:
        config: BotConfig object.

    Returns:
        MusicBot instance.
    """
    return MusicBot(config)
