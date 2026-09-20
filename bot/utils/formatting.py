"""
Formatting utilities for the bot.
"""
from typing import Any

def format_duration(seconds: float) -> str:
    """
    Format duration in seconds to MM:SS or HH:MM:SS.
    
    Args:
        seconds: Duration in seconds.
        
    Returns:
        str: Formatted duration string.
    """
    seconds = int(seconds)
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"

def format_duration_long(seconds: float) -> str:
    """
    Format duration to a long string (e.g., '3 minutes, 42 seconds').
    
    Args:
        seconds: Duration in seconds.
        
    Returns:
        str: Formatted long duration string.
    """
    seconds = int(seconds)
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    
    parts = []
    if hours > 0:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes > 0:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    if secs > 0 or not parts:
        parts.append(f"{secs} second{'s' if secs != 1 else ''}")
        
    return ", ".join(parts)

def truncate(text: str, max_len: int) -> str:
    """
    Truncate text to max_len and append ellipsis if necessary.
    
    Args:
        text: Text to truncate.
        max_len: Maximum length.
        
    Returns:
        str: Truncated text.
    """
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + "..."

def format_track_line(index: int, track: Any, is_current: bool) -> str:
    """
    Format a track for display in a queue.
    
    Args:
        index: Track position index.
        track: Track object (must have title, duration properties).
        is_current: Whether this is the currently playing track.
        
    Returns:
        str: Formatted queue line.
    """
    prefix = "▶ " if is_current else f"`{index}.` "
    title = truncate(getattr(track, 'title', 'Unknown Track'), 50)
    duration = format_duration(getattr(track, 'duration', 0))
    
    return f"{prefix} **{title}** [{duration}]"

def format_filesize(bytes_size: int) -> str:
    """
    Format file size to human readable string.
    
    Args:
        bytes_size: Size in bytes.
        
    Returns:
        str: Human readable file size.
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.1f} PB"

def progress_bar(current: float, total: float, length: int = 12) -> str:
    """
    Create a visual progress bar.
    
    Args:
        current: Current progress value.
        total: Total value.
        length: Length of the progress bar in characters.
        
    Returns:
        str: Progress bar string.
    """
    if total <= 0:
        return "🔘" + "▬" * (length - 1)
        
    progress = max(0.0, min(1.0, current / total))
    filled_blocks = int(length * progress)
    
    bar = ""
    for i in range(length):
        if i == filled_blocks:
            bar += "🔘"
        else:
            bar += "▬"
            
    if filled_blocks == length:
        bar = "▬" * (length - 1) + "🔘"
        
    return bar

def mask_token(token: str) -> str:
    """
    Mask a token for safe display showing first 4 and last 4 characters.
    
    Args:
        token: The token to mask.
        
    Returns:
        str: Masked token.
    """
    if not token:
        return ""
    if len(token) <= 8:
        return "***"
    return f"{token[:4]}{'*' * (len(token)-8)}{token[-4:]}"
