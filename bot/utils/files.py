"""
File and directory utilities for the bot.
"""
import re
from pathlib import Path
from typing import List, Set

def ensure_directories(*dirs: Path) -> None:
    """
    Ensure the given directories exist, creating them if necessary.
    
    Args:
        *dirs: Path objects to ensure.
    """
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)

def is_audio_file(path: Path, supported: Set[str]) -> bool:
    """
    Check if a path corresponds to a supported audio file.
    
    Args:
        path: Path to check.
        supported: Set of supported extensions (e.g., {'.mp3', '.flac'}).
        
    Returns:
        bool: True if it's an audio file.
    """
    return path.is_file() and path.suffix.lower() in supported

def is_hidden_file(path: Path) -> bool:
    """
    Check if a file or directory is hidden.
    
    Args:
        path: Path to check.
        
    Returns:
        bool: True if hidden.
    """
    return path.name.startswith('.')

def get_audio_files(directory: Path, supported: Set[str], recursive: bool = True) -> List[Path]:
    """
    List supported audio files in a directory.
    
    Args:
        directory: The directory to search.
        supported: Set of supported extensions.
        recursive: Whether to search recursively.
        
    Returns:
        List[Path]: Sorted list of audio file paths.
    """
    files = []
    
    if not directory.exists() or not directory.is_dir():
        return files
        
    try:
        if recursive:
            iterator = directory.rglob('*')
        else:
            iterator = directory.iterdir()
            
        for path in iterator:
            if not is_hidden_file(path) and is_audio_file(path, supported):
                files.append(path)
                
    except (OSError, PermissionError):
        pass
        
    return sorted(files)

def safe_filename(name: str) -> str:
    """
    Sanitize a string to be used as a filename.
    
    Args:
        name: The name to sanitize.
        
    Returns:
        str: Sanitized filename.
    """
    # Keep alphanumeric, spaces, hyphens, and underscores
    sanitized = re.sub(r'[^\w\s-]', '', name).strip()
    return re.sub(r'[-\s]+', '-', sanitized)
