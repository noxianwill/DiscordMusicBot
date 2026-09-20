"""
Configuration loader and dataclass for the Discord Music Bot.
"""

import os
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class BotConfig:
    """Strongly-typed configuration container for the Discord Music Bot."""
    discord_bot_token: str
    command_channel_id: Optional[int] = None
    playlists_directory: Path = field(default_factory=lambda: Path('./playlists'))
    default_volume: int = 75
    dj_role_name: str = 'DJ'
    auto_leave: bool = True
    auto_leave_delay: int = 300
    idle_status: str = 'Ready to play'
    playing_status: str = 'Playing: {title}'
    max_queue_size: int = 100
    max_history_size: int = 50
    supported_formats: str = '.mp3,.flac,.ogg,.wav'
    youtube_auth_mode: str = 'disabled'
    youtube_client_id: Optional[str] = None
    youtube_client_secret: Optional[str] = None
    youtube_access_token: Optional[str] = None
    youtube_refresh_token: Optional[str] = None
    data_directory: Path = field(default_factory=lambda: Path('./data'))
    log_level: str = 'INFO'
    raw_log_level: str = 'INFO'
    log_file: Path = field(default_factory=lambda: Path('./logs/bot.log'))
    log_to_file: bool = True
    log_to_console: bool = True
    log_discord_internals: bool = False
    log_commands: bool = True
    log_ytdlp_verbose: bool = False
    log_audio_buffer: bool = False
    log_rotation_mb: int = 10
    log_backup_count: int = 5
    command_prefix: str = '!'
    loop_mode: str = 'off'

    @property
    def playlists_dir(self) -> str:
        """Alias returning playlists directory as string for backward compatibility."""
        return str(self.playlists_directory)

    @property
    def prefix(self) -> str:
        """Alias for command prefix."""
        return self.command_prefix

    @property
    def ytdl_enabled(self) -> bool:
        """Boolean indicating whether YouTube playback via yt-dlp is available."""
        return True

    def supported_extensions_set(self) -> Set[str]:
        """Returns the set of normalized supported audio extensions (e.g. {'.mp3', '.flac'})."""
        return {
            ext.strip().lower()
            for ext in self.supported_formats.split(',')
            if ext.strip()
        }


def load_config(file_path: Path | str) -> BotConfig:
    """
    Loads configuration from a key=value file and applies environment variable overrides.

    Args:
        file_path: Path to config file.

    Returns:
        BotConfig instance with validated and parsed options.
    """
    file_path = Path(file_path)
    config_dict = {}

    if file_path.exists():
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' in line:
                    key, value = line.split('=', 1)
                    config_dict[key.strip().lower()] = value.strip()

    # Apply environment variable overrides (checks uppercase env vars)
    env_keys = [
        'DISCORD_BOT_TOKEN', 'DISCORD_COMMAND_CHANNEL_ID', 'COMMAND_PREFIX',
        'PLAYLISTS_DIRECTORY', 'SUPPORTED_FORMATS', 'YOUTUBE_AUTH_MODE',
        'YOUTUBE_CLIENT_ID', 'YOUTUBE_CLIENT_SECRET', 'YOUTUBE_ACCESS_TOKEN',
        'YOUTUBE_REFRESH_TOKEN', 'IDLE_STATUS', 'PLAYING_STATUS',
        'DEFAULT_VOLUME', 'LOOP_MODE', 'MAX_QUEUE_SIZE', 'AUTO_LEAVE',
        'AUTO_LEAVE_DELAY', 'DJ_ROLE_NAME', 'LOG_LEVEL', 'LOG_FILE',
        'LOG_TO_FILE', 'LOG_TO_CONSOLE', 'LOG_DISCORD_INTERNALS',
        'LOG_COMMANDS', 'LOG_YTDLP_VERBOSE', 'LOG_AUDIO_BUFFER',
        'LOG_ROTATION_MB', 'LOG_BACKUP_COUNT', 'MAX_HISTORY_SIZE',
        'DATA_DIRECTORY'
    ]
    for env_key in env_keys:
        val = os.getenv(env_key)
        if val is not None and val != "":
            config_dict[env_key.lower()] = val.strip()

    # Token check
    token = config_dict.get('discord_bot_token') or os.getenv('DISCORD_BOT_TOKEN')
    if not token:
        raise ValueError("Missing required configuration: DISCORD_BOT_TOKEN")

    parsed = {'discord_bot_token': token}

    # Command channel ID
    raw_channel = config_dict.get('discord_command_channel_id') or config_dict.get('command_channel_id')
    if raw_channel:
        try:
            parsed['command_channel_id'] = int(raw_channel)
        except ValueError:
            parsed['command_channel_id'] = None
    else:
        parsed['command_channel_id'] = None

    # Playlists directory
    raw_playlists = config_dict.get('playlists_directory') or config_dict.get('playlists_dir')
    if raw_playlists:
        parsed['playlists_directory'] = Path(raw_playlists)
    else:
        parsed['playlists_directory'] = Path('./playlists')

    # Data directory
    if 'data_directory' in config_dict:
        parsed['data_directory'] = Path(config_dict['data_directory'])

    # Log file
    raw_log_file = config_dict.get('log_file')
    if raw_log_file:
        parsed['log_file'] = Path(raw_log_file)
    else:
        parsed['log_file'] = Path('./logs/bot.log')

    # Numeric fields
    for int_key in ['default_volume', 'auto_leave_delay', 'max_queue_size', 'max_history_size', 'log_rotation_mb', 'log_backup_count']:
        if int_key in config_dict and config_dict[int_key]:
            try:
                parsed[int_key] = int(config_dict[int_key])
            except ValueError:
                pass

    # Boolean fields
    for bool_key in [
        'auto_leave', 'log_to_file', 'log_to_console', 'log_discord_internals',
        'log_commands', 'log_ytdlp_verbose', 'log_audio_buffer'
    ]:
        if bool_key in config_dict:
            val = str(config_dict[bool_key]).lower()
            parsed[bool_key] = val in ('true', '1', 'yes', 'on')

    # String fields
    for str_key in [
        'dj_role_name', 'idle_status', 'playing_status', 'supported_formats',
        'youtube_auth_mode', 'youtube_client_id', 'youtube_client_secret',
        'youtube_access_token', 'youtube_refresh_token',
        'command_prefix', 'loop_mode'
    ]:
        if str_key in config_dict and config_dict[str_key]:
            parsed[str_key] = config_dict[str_key]

    # Log level with alias normalization (e.g. EVERYTHING/VERBOSE -> DEBUG)
    LEVEL_ALIASES = {
        'VERBOSE': 'DEBUG',
        'EVERYTHING': 'DEBUG',
        'ALL': 'DEBUG',
        'STANDARD': 'INFO',
        'NORMAL': 'INFO',
        'QUIET': 'WARNING',
        'MINIMAL': 'WARNING',
        'ERRORS': 'ERROR',
        'ERROR_ONLY': 'ERROR',
    }
    raw_level = (config_dict.get('log_level') or 'INFO').upper()
    parsed['raw_log_level'] = raw_level
    parsed['log_level'] = LEVEL_ALIASES.get(raw_level, raw_level)

    return BotConfig(**parsed)


class ConfigLoader:
    """Compatibility class wrapper for loading BotConfig."""

    def __init__(self, file_path: Path | str):
        self.file_path = Path(file_path)

    def load(self) -> BotConfig:
        return load_config(self.file_path)
