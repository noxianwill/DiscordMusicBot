"""
Models for the playlist system.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class PlaylistTrack:
    """Represents a single track within a playlist."""
    filename: str
    file_path: Path
    title: str
    artist: Optional[str] = None
    album: Optional[str] = None
    track_number: Optional[int] = None
    duration: Optional[float] = None
    year: Optional[int] = None


@dataclass
class Playlist:
    """Represents a local filesystem-based playlist."""
    name: str
    directory: Path
    tracks: list[PlaylistTrack] = field(default_factory=list)

    @property
    def total_duration(self) -> float:
        """Calculate the total duration of the playlist in seconds."""
        return sum((track.duration or 0.0) for track in self.tracks)

    @property
    def track_count(self) -> int:
        """Get the total number of tracks in the playlist."""
        return len(self.tracks)
