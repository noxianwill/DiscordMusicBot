"""
Models for the YouTube metadata service.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class YouTubeVideo:
    """Represents metadata for a YouTube video."""
    video_id: str
    title: str
    channel_title: str
    duration_seconds: int
    url: str
    thumbnail_url: str
    view_count: Optional[int] = None
    published_at: Optional[str] = None


@dataclass
class YouTubePlaylistInfo:
    """Represents metadata for a YouTube playlist."""
    playlist_id: str
    title: str
    channel_title: str
    item_count: int
    url: str
    thumbnail_url: str


@dataclass
class YouTubeSearchResult:
    """Represents a single search result from YouTube."""
    video_id: str
    title: str
    channel_title: str
    url: str
    thumbnail_url: str


def duration_display(seconds: int) -> str:
    """
    Format a duration in seconds to a string like '3:42' or '1:20:05'.

    Args:
        seconds: Duration in seconds.

    Returns:
        Formatted duration string.
    """
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"
