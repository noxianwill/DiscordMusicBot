"""
Scanner for reading local filesystem playlists.
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional

try:
    from tinytag import TinyTag, TinyTagException
    HAS_TINYTAG = True
except ImportError:
    HAS_TINYTAG = False
    TinyTag = None
    class TinyTagException(Exception):
        """Fallback exception when tinytag is not installed."""
        pass

from .models import Playlist, PlaylistTrack

logger = logging.getLogger(__name__)


class PlaylistScanner:
    """Scans directories for audio files and extracts metadata."""

    def __init__(self, playlists_dir: Path, supported_extensions: set[str]):
        """
        Initialize the scanner.

        Args:
            playlists_dir: Base directory containing playlist subdirectories.
            supported_extensions: Set of supported extensions (e.g., {'.mp3', '.flac'}).
        """
        self.playlists_dir = playlists_dir.resolve()
        self.supported_extensions = {ext.lower() for ext in supported_extensions}

    async def scan_all(self) -> list[Playlist]:
        """
        Scan all subdirectories in the playlists directory for playlists.

        Returns:
            A list of loaded Playlist objects.
        """
        return await asyncio.to_thread(self._scan_all_sync)

    async def scan_playlist(self, playlist_dir: Path) -> Playlist:
        """
        Scan a single playlist directory.

        Args:
            playlist_dir: Path to the playlist directory.

        Returns:
            A Playlist object containing the discovered tracks.
        """
        return await asyncio.to_thread(self._scan_playlist_sync, playlist_dir)

    def _scan_all_sync(self) -> list[Playlist]:
        """Synchronous implementation of scanning all playlists."""
        playlists = []
        if not self.playlists_dir.exists() or not self.playlists_dir.is_dir():
            logger.warning(f"Playlists directory not found: {self.playlists_dir}")
            return playlists

        for entry in self.playlists_dir.iterdir():
            if entry.is_dir() and not self._is_hidden(entry):
                try:
                    playlist = self._scan_playlist_sync(entry)
                    if playlist.track_count > 0:
                        playlists.append(playlist)
                except Exception as e:
                    logger.error(f"Error scanning playlist {entry.name}: {e}")

        return playlists

    def _scan_playlist_sync(self, playlist_dir: Path) -> Playlist:
        """Synchronous implementation of scanning a single playlist."""
        resolved_dir = playlist_dir.resolve()
        
        # Prevent path traversal
        if not resolved_dir.is_relative_to(self.playlists_dir):
            raise ValueError(f"Playlist directory {resolved_dir} is outside base directory {self.playlists_dir}")

        playlist_name = resolved_dir.name
        tracks: list[PlaylistTrack] = []

        for file_path in resolved_dir.rglob("*"):
            if file_path.is_file() and not self._is_hidden(file_path) and self._is_audio_file(file_path):
                track = self._extract_metadata(file_path)
                if track:
                    tracks.append(track)

        # Sort tracks by track_number metadata first, then filename
        tracks.sort(key=lambda t: (t.track_number if t.track_number is not None else float('inf'), t.filename.lower()))

        return Playlist(name=playlist_name, directory=resolved_dir, tracks=tracks)

    def _is_audio_file(self, path: Path) -> bool:
        """Check if the file has a supported audio extension."""
        return path.suffix.lower() in self.supported_extensions

    def _is_hidden(self, path: Path) -> bool:
        """Check if the file or directory is hidden."""
        return path.name.startswith('.') or path.name.startswith('_')

    def _extract_metadata(self, file_path: Path) -> Optional[PlaylistTrack]:
        """Extract metadata from an audio file using TinyTag (falls back to filename)."""
        if not HAS_TINYTAG:
            return PlaylistTrack(
                filename=file_path.name,
                file_path=file_path,
                title=file_path.stem,
            )

        try:
            tag = TinyTag.get(str(file_path))
            
            # Use filename as title if metadata title is missing
            title = tag.title if tag.title else file_path.stem

            try:
                track_num = int(tag.track) if tag.track else None
            except ValueError:
                track_num = None

            try:
                year = int(tag.year) if tag.year else None
            except ValueError:
                year = None

            return PlaylistTrack(
                filename=file_path.name,
                file_path=file_path,
                title=title,
                artist=tag.artist,
                album=tag.album,
                track_number=track_num,
                duration=tag.duration,
                year=year
            )
        except TinyTagException as e:
            logger.warning(f"Failed to read metadata for {file_path}: {e}")
            # Fallback to basic file info
            return PlaylistTrack(
                filename=file_path.name,
                file_path=file_path,
                title=file_path.stem,
            )
        except Exception as e:
            logger.error(f"Unexpected error extracting metadata from {file_path}: {e}")
            return None
