"""
High level orchestrator for the YouTube metadata service.
"""

import logging
from pathlib import Path
from typing import Optional, Any

from .oauth import YouTubeAuth
from .client import YouTubeClient
from .models import YouTubeVideo, YouTubePlaylistInfo, YouTubeSearchResult

logger = logging.getLogger(__name__)


class YouTubeService:
    """Orchestrates YouTube authentication and API client operations."""

    def __init__(self, config: dict[str, Any]):
        """
        Initialize the YouTube service.

        Args:
            config: A dictionary containing configuration values for YouTube.
                    Expected keys: 'client_id', 'client_secret', 'token_path'
        """
        self.config = config
        token_path = Path(config.get('token_path', 'youtube_token.json'))
        
        self.auth = YouTubeAuth(
            client_id=config.get('client_id'),
            client_secret=config.get('client_secret'),
            token_path=token_path
        )
        self.client: Optional[YouTubeClient] = None
        self._enabled = False

    @property
    def enabled(self) -> bool:
        """Return True if the YouTube service is configured and authenticated."""
        return self._enabled

    async def initialize(self) -> None:
        """
        Initialize the service, load/refresh credentials, and build the client.
        """
        if not self.auth.is_configured:
            logger.info("YouTube client_id or client_secret not configured. YouTube metadata service will be disabled.")
            self._enabled = False
            return

        creds = self.auth.load_credentials()
        if creds:
            creds = self.auth.refresh_if_needed(creds)
            
        if creds and creds.valid:
            self.client = YouTubeClient(creds)
            self._enabled = True
            logger.info("YouTube metadata service successfully initialized.")
        else:
            logger.warning("YouTube credentials not valid or missing. Call run_auth_flow() or configure tokens manually.")
            self._enabled = False

    async def search(self, query: str, max_results: int = 5) -> list[YouTubeSearchResult]:
        """
        Search for YouTube videos.

        Args:
            query: The search term.
            max_results: Maximum results to return.

        Returns:
            List of YouTubeSearchResult.
        """
        if not self.enabled or not self.client:
            logger.warning("YouTube service is disabled. Cannot perform search.")
            return []
        return await self.client.search(query, max_results)

    async def get_video(self, video_id: str) -> Optional[YouTubeVideo]:
        """
        Get metadata for a specific YouTube video.

        Args:
            video_id: The video ID.

        Returns:
            YouTubeVideo or None if not found/disabled.
        """
        if not self.enabled or not self.client:
            logger.warning("YouTube service is disabled. Cannot get video.")
            return None
        return await self.client.get_video(video_id)

    async def get_playlist_info(self, playlist_id: str) -> Optional[YouTubePlaylistInfo]:
        """
        Get metadata for a YouTube playlist.

        Args:
            playlist_id: The playlist ID.

        Returns:
            YouTubePlaylistInfo or None if not found/disabled.
        """
        if not self.enabled or not self.client:
            logger.warning("YouTube service is disabled. Cannot get playlist info.")
            return None
        return await self.client.get_playlist_info(playlist_id)

    async def get_playlist_items(self, playlist_id: str, limit: int = 50) -> list[YouTubeVideo]:
        """
        Get items from a YouTube playlist.

        Args:
            playlist_id: The playlist ID.
            limit: Maximum items to fetch.

        Returns:
            List of YouTubeVideo objects.
        """
        if not self.enabled or not self.client:
            logger.warning("YouTube service is disabled. Cannot get playlist items.")
            return []
        return await self.client.get_playlist_items(playlist_id, limit)
