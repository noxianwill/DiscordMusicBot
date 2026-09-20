"""
Validation utilities for the bot.
"""
import re
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, parse_qs

def sanitize_playlist_name(name: str) -> str:
    """
    Remove dangerous characters from a playlist name to prevent path traversal.
    
    Args:
        name: The playlist name to sanitize.
        
    Returns:
        str: Sanitized playlist name.
    """
    # Remove null bytes, slashes, and backslashes
    name = name.replace('\0', '').replace('/', '').replace('\\', '')
    # Strip dangerous relative path segments
    name = re.sub(r'^\.+', '', name)
    # Strip whitespace
    return name.strip()

def is_safe_path(path: Path, base_dir: Path) -> bool:
    """
    Ensure that a path stays within the specified base directory.
    
    Args:
        path: The path to check.
        base_dir: The base directory it must be within.
        
    Returns:
        bool: True if safe, False otherwise.
    """
    try:
        resolved_path = path.resolve()
        resolved_base = base_dir.resolve()
        return resolved_base in resolved_path.parents or resolved_path == resolved_base
    except (ValueError, RuntimeError, OSError):
        return False

def validate_volume(value: int) -> int:
    """
    Clamp the volume value between 0 and 100.
    
    Args:
        value: The volume value to validate.
        
    Returns:
        int: Clamped volume value.
    """
    return max(0, min(100, int(value)))

def validate_queue_position(pos: int, queue_size: int) -> int:
    """
    Validate and clamp a queue position.
    
    Args:
        pos: The requested position (1-indexed).
        queue_size: The total size of the queue.
        
    Returns:
        int: Validated 1-indexed position.
    """
    return max(1, min(queue_size, int(pos)))

def is_url(text: str) -> bool:
    """
    Check if the given text is a valid URL.
    
    Args:
        text: Text to check.
        
    Returns:
        bool: True if URL, False otherwise.
    """
    try:
        result = urlparse(text)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False

def is_youtube_url(text: str) -> bool:
    """
    Check if the given text is a YouTube URL.
    
    Args:
        text: Text to check.
        
    Returns:
        bool: True if it's a YouTube URL.
    """
    if not is_url(text):
        return False
    
    parsed = urlparse(text)
    hostname = parsed.hostname or ''
    return hostname.endswith('youtube.com') or hostname == 'youtu.be'

def extract_youtube_id(url: str) -> Optional[str]:
    """
    Extract the video ID from a YouTube URL.
    
    Args:
        url: The YouTube URL.
        
    Returns:
        Optional[str]: The video ID or None.
    """
    parsed = urlparse(url)
    hostname = parsed.hostname or ''
    
    if hostname == 'youtu.be':
        return parsed.path[1:]
    
    if hostname.endswith('youtube.com'):
        if parsed.path == '/watch':
            qs = parse_qs(parsed.query)
            return qs.get('v', [None])[0]
        elif parsed.path.startswith('/embed/') or parsed.path.startswith('/v/'):
            return parsed.path.split('/')[2]
            
    return None

def extract_youtube_playlist_id(url: str) -> Optional[str]:
    """
    Extract the playlist ID from a YouTube URL.
    
    Args:
        url: The YouTube URL.
        
    Returns:
        Optional[str]: The playlist ID or None.
    """
    parsed = urlparse(url)
    hostname = parsed.hostname or ''
    
    if hostname.endswith('youtube.com') and 'list' in parse_qs(parsed.query):
        qs = parse_qs(parsed.query)
        return qs.get('list', [None])[0]
        
    return None
