import asyncio
import random
from enum import Enum, auto
from typing import List, Optional, Tuple

from .source import AudioTrack

class LoopMode(Enum):
    """Playback loop modes."""
    OFF = auto()
    TRACK = auto()
    QUEUE = auto()

class PlaybackQueue:
    """Thread-safe queue for managing playback order."""
    
    def __init__(self, max_size: int = 1000):
        self._tracks: List[AudioTrack] = []
        self.current_index: int = -1
        self.loop_mode: LoopMode = LoopMode.OFF
        self._lock = asyncio.Lock()
        self.max_size = max_size

    async def add(self, track: AudioTrack) -> bool:
        """Adds a single track to the end of the queue."""
        async with self._lock:
            if len(self._tracks) >= self.max_size:
                return False
            self._tracks.append(track)
            if self.current_index == -1:
                self.current_index = 0
            return True

    async def add_many(self, tracks: List[AudioTrack]) -> int:
        """Adds multiple tracks to the end of the queue."""
        async with self._lock:
            added = 0
            for track in tracks:
                if len(self._tracks) >= self.max_size:
                    break
                self._tracks.append(track)
                added += 1
            if self.current_index == -1 and added > 0:
                self.current_index = 0
            return added

    async def remove(self, index: int) -> Optional[AudioTrack]:
        """Removes a track at the specified index."""
        async with self._lock:
            if 0 <= index < len(self._tracks):
                track = self._tracks.pop(index)
                if index < self.current_index:
                    self.current_index -= 1
                elif index == self.current_index and self.current_index >= len(self._tracks):
                    self.current_index = len(self._tracks) - 1 if self._tracks else -1
                return track
            return None

    async def move(self, from_idx: int, to_idx: int) -> bool:
        """Moves a track from one index to another."""
        async with self._lock:
            if 0 <= from_idx < len(self._tracks) and 0 <= to_idx < len(self._tracks):
                track = self._tracks.pop(from_idx)
                self._tracks.insert(to_idx, track)
                
                # Update current_index to track the playing song
                if from_idx == self.current_index:
                    self.current_index = to_idx
                elif from_idx < self.current_index <= to_idx:
                    self.current_index -= 1
                elif to_idx <= self.current_index < from_idx:
                    self.current_index += 1
                return True
            return False

    async def clear(self):
        """Clears all tracks from the queue."""
        async with self._lock:
            self._tracks.clear()
            self.current_index = -1

    async def shuffle(self):
        """Shuffles the remaining upcoming tracks."""
        async with self._lock:
            if self.current_index < 0 or len(self._tracks) <= self.current_index + 1:
                return
            
            upcoming_tracks = self._tracks[self.current_index + 1:]
            random.shuffle(upcoming_tracks)
            self._tracks = self._tracks[:self.current_index + 1] + upcoming_tracks

    async def current(self) -> Optional[AudioTrack]:
        """Returns the currently playing track."""
        async with self._lock:
            if 0 <= self.current_index < len(self._tracks):
                return self._tracks[self.current_index]
            return None

    async def advance(self) -> Optional[AudioTrack]:
        """Advances to the next track, respecting the current loop mode."""
        async with self._lock:
            if not self._tracks:
                return None
                
            if self.loop_mode == LoopMode.TRACK:
                pass # current_index stays same
            elif self.loop_mode == LoopMode.QUEUE:
                self.current_index = (self.current_index + 1) % len(self._tracks)
            else:
                if self.current_index + 1 < len(self._tracks):
                    self.current_index += 1
                else:
                    self.current_index = len(self._tracks) # past the end
                    return None
                    
            if 0 <= self.current_index < len(self._tracks):
                return self._tracks[self.current_index]
            return None

    async def go_back(self) -> Optional[AudioTrack]:
        """Moves back to the previous track."""
        async with self._lock:
            if not self._tracks:
                return None
                
            if self.current_index > 0:
                self.current_index -= 1
            else:
                if self.loop_mode == LoopMode.QUEUE:
                    self.current_index = len(self._tracks) - 1
                else:
                    self.current_index = 0
                    
            return self._tracks[self.current_index]

    async def get_page(self, page: int, per_page: int = 10) -> Tuple[List[AudioTrack], int, int]:
        """Returns a paginated view of the queue."""
        async with self._lock:
            total_pages = max(1, (len(self._tracks) + per_page - 1) // per_page)
            page = max(1, min(page, total_pages))
            start = (page - 1) * per_page
            end = start + per_page
            return self._tracks[start:end], page, total_pages

    def __len__(self) -> int:
        return len(self._tracks)

    @property
    def is_empty(self) -> bool:
        return len(self._tracks) == 0

    async def upcoming(self) -> List[AudioTrack]:
        """Returns all tracks scheduled to play after the current one."""
        async with self._lock:
            if 0 <= self.current_index < len(self._tracks):
                return self._tracks[self.current_index + 1:]
            return []
