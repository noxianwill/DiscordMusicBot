import asyncio
import logging
from pathlib import Path
from tinytag import TinyTag, TinyTagException

from .source import AudioTrack, SourceType

logger = logging.getLogger(__name__)

class MetadataExtractor:
    """Utility class for extracting metadata from local audio files."""
    
    SUPPORTED_EXTENSIONS = {'.mp3', '.flac', '.ogg', '.wav'}

    @staticmethod
    def _extract_sync(file_path: Path) -> AudioTrack:
        """Synchronously extracts metadata using tinytag."""
        track = AudioTrack(
            title=file_path.stem,
            source_type=SourceType.LOCAL_FILE,
            source_uri=str(file_path.absolute()),
        )
        
        if file_path.suffix.lower() not in MetadataExtractor.SUPPORTED_EXTENSIONS:
            return track
            
        try:
            tag = TinyTag.get(str(file_path))
            
            if tag.title:
                track.title = tag.title
            else:
                # Intelligently parse '01 - Song Name.mp3' or 'Artist - Song.mp3'
                parts = file_path.stem.split(" - ", 1)
                if len(parts) == 2:
                    if parts[0].isdigit():
                        track.title = parts[1]
                    else:
                        track.artist = parts[0]
                        track.title = parts[1]
            
            if not track.artist and tag.artist:
                track.artist = tag.artist
                
            track.album = tag.album
            track.duration = tag.duration
            track.metadata = {
                "album_artist": tag.albumartist,
                "track_number": tag.track,
                "year": tag.year
            }
        except (TinyTagException, Exception) as e:
            logger.warning(f"Failed to read metadata for {file_path}: {e}")
            
        return track

    @staticmethod
    async def extract(file_path: Path, requester_id: int = 0, requester_name: str = "") -> AudioTrack:
        """Asynchronously extracts metadata and populates an AudioTrack."""
        track = await asyncio.to_thread(MetadataExtractor._extract_sync, file_path)
        track.requester_id = requester_id
        track.requester_name = requester_name
        return track
