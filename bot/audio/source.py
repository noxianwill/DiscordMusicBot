import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional, Dict, Any

class SourceType(Enum):
    """Enumeration of supported audio source types."""
    LOCAL_FILE = auto()
    YOUTUBE = auto()

@dataclass
class AudioTrack:
    """Represents a single audio track with its metadata and source information."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    artist: Optional[str] = None
    album: Optional[str] = None
    duration: Optional[float] = None
    source_type: SourceType = SourceType.LOCAL_FILE
    source_uri: str = ""
    stream_url: Optional[str] = None
    requester_id: int = 0
    requester_name: str = ""
    playlist_name: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    thumbnail_url: Optional[str] = None

    def display_title(self) -> str:
        """Returns the formatted title, combining artist and title if available."""
        if self.artist:
            return f"{self.artist} - {self.title}"
        return self.title

    def duration_str(self) -> str:
        """Returns the duration formatted as MM:SS or HH:MM:SS."""
        if self.duration is None:
            return "Unknown"
        
        total_seconds = int(self.duration)
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"
