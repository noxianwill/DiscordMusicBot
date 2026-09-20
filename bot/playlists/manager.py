"""
Manager for local playlists.
"""

import logging
import re
from pathlib import Path
from typing import Optional

from .models import Playlist
from .scanner import PlaylistScanner

logger = logging.getLogger(__name__)


class PlaylistManager:
    """Manages the caching, loading, and searching of local playlists."""

    def __init__(self, playlists_dir: Path, supported_extensions: set[str]):
        """
        Initialize the playlist manager.

        Args:
            playlists_dir: Base directory containing playlist subdirectories.
            supported_extensions: Set of supported audio extensions.
        """
        self.playlists_dir = playlists_dir.resolve()
        self.scanner = PlaylistScanner(playlists_dir, supported_extensions)
        self._playlists: dict[str, Playlist] = {}

    async def load(self) -> None:
        """Perform an initial full scan on startup."""
        await self.reload()

    async def reload(self) -> None:
        """Rescan all playlists and update the cache."""
        logger.info(f"Scanning playlists in {self.playlists_dir}...")
        playlists = await self.scanner.scan_all()
        
        self._playlists.clear()
        total_tracks = 0
        for playlist in playlists:
            if not self._is_valid_name(playlist.name):
                logger.warning(f"Skipping playlist with invalid name: {playlist.name}")
                continue
            
            self._playlists[playlist.name.lower()] = playlist
            total_tracks += playlist.track_count
            
        logger.info(f"Scan complete: {len(self._playlists)} playlists found, {total_tracks} total tracks.")

    def get_playlist(self, name: str) -> Optional[Playlist]:
        """
        Retrieve a playlist by its name (case-insensitive).

        Args:
            name: The name of the playlist to find.

        Returns:
            The Playlist object if found, else None.
        """
        return self._playlists.get(name.lower())

    def get_all(self) -> list[Playlist]:
        """
        Return all loaded playlists sorted by name.

        Returns:
            A list of all Playlist objects.
        """
        return sorted(self._playlists.values(), key=lambda p: p.name.lower())

    def get_names(self) -> list[str]:
        """
        Return all playlist names for autocomplete or listing.

        Returns:
            A list of playlist names.
        """
        return sorted(p.name for p in self._playlists.values())

    def search(self, query: str) -> list[Playlist]:
        """
        Fuzzy match playlist names based on a search query.

        Args:
            query: The search query.

        Returns:
            A list of playlists that match the query.
        """
        query_lower = query.lower()
        results = []
        for playlist in self.get_all():
            if query_lower in playlist.name.lower():
                results.append(playlist)
        return results

    def _is_valid_name(self, name: str) -> bool:
        """
        Validate playlist names to prevent path traversal and ensure proper characters.
        Allows alphanumeric characters, spaces, hyphens, and underscores.
        """
        if ".." in name or "/" in name or "\\" in name:
            return False
        return bool(re.match(r'^[\w\s\-]+$', name))
