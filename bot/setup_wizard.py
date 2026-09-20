"""
Setup wizard for interactive initial configuration of the bot.
"""
import sys
import asyncio
from pathlib import Path
from getpass import getpass
from typing import Dict, Any, Optional

FULL_CONFIG_TEMPLATE = """# ============================================================
# Discord Music Bot — Configuration
# ============================================================
# Lines starting with # are comments and will be ignored.
# Environment variables override these values (use UPPERCASE key names).
# ============================================================

# ----------------------------------------------------------
# DISCORD SETTINGS (Required)
# ----------------------------------------------------------

# Your Discord bot token from the Developer Portal
DISCORD_BOT_TOKEN={discord_bot_token}

# Channel ID where bot commands are accepted (leave empty for all channels)
DISCORD_COMMAND_CHANNEL_ID={command_channel_id}

# Command prefix for legacy text commands (slash commands are always available)
COMMAND_PREFIX={command_prefix}

# ----------------------------------------------------------
# PLAYLIST SETTINGS (Required)
# ----------------------------------------------------------

# Path to folder containing local music playlists
PLAYLISTS_DIRECTORY={playlists_directory}

# Supported audio file formats (comma-separated)
SUPPORTED_FORMATS={supported_formats}

# ----------------------------------------------------------
# YOUTUBE SETTINGS (Optional)
# ----------------------------------------------------------
# Authentication mode: oauth, token, or disabled
YOUTUBE_AUTH_MODE={youtube_auth_mode}

# Google Cloud OAuth credentials (optional)
YOUTUBE_CLIENT_ID={youtube_client_id}
YOUTUBE_CLIENT_SECRET={youtube_client_secret}
YOUTUBE_ACCESS_TOKEN={youtube_access_token}
YOUTUBE_REFRESH_TOKEN={youtube_refresh_token}

# ----------------------------------------------------------
# BOT PRESENCE / STATUS
# ----------------------------------------------------------

# Status shown when bot is idle
IDLE_STATUS={idle_status}

# Status shown during playback
PLAYING_STATUS={playing_status}

# ----------------------------------------------------------
# PLAYBACK SETTINGS
# ----------------------------------------------------------

# Default volume level (0-100)
DEFAULT_VOLUME={default_volume}

# Default loop mode: off, track, or queue
LOOP_MODE={loop_mode}

# Maximum number of tracks in the queue
MAX_QUEUE_SIZE={max_queue_size}

# ----------------------------------------------------------
# VOICE CHANNEL SETTINGS
# ----------------------------------------------------------

# Automatically leave voice channel when alone
AUTO_LEAVE={auto_leave}

# Seconds to wait before auto-leaving
AUTO_LEAVE_DELAY={auto_leave_delay}

# ----------------------------------------------------------
# PERMISSIONS
# ----------------------------------------------------------

# Discord role name that grants DJ permissions
DJ_ROLE_NAME={dj_role_name}

# ----------------------------------------------------------
# LOGGING CONFIGURATION
# ----------------------------------------------------------
# Presets: EVERYTHING / VERBOSE (DEBUG), STANDARD (INFO), QUIET (WARNING), ERRORS (ERROR)
LOG_LEVEL={log_level}

# Path to the log file
LOG_FILE={log_file}

# Enable writing logs to file (true / false)
LOG_TO_FILE={log_to_file}

# Enable printing logs to the console (true / false)
LOG_TO_CONSOLE={log_to_console}

# Log every command execution (true / false)
LOG_COMMANDS={log_commands}

# Include raw internal discord.py websocket heartbeat frames (true / false)
LOG_DISCORD_INTERNALS={log_discord_internals}

# Enable verbose yt-dlp diagnostic extractor logs (true / false)
LOG_YTDLP_VERBOSE={log_ytdlp_verbose}

# Log audio buffer statistics in debug mode (true / false)
LOG_AUDIO_BUFFER={log_audio_buffer}

# Maximum log file size before rotating (in Megabytes)
LOG_ROTATION_MB={log_rotation_mb}

# Number of rotated backup log files to retain
LOG_BACKUP_COUNT={log_backup_count}

# ----------------------------------------------------------
# HISTORY & STATE
# ----------------------------------------------------------

# Maximum number of tracks to keep in playback history
MAX_HISTORY_SIZE={max_history_size}

# Directory for persistent data (tokens, cache, state)
DATA_DIRECTORY={data_directory}
"""


class SetupWizard:
    """Interactive wizard to generate or update the bot configuration."""

    def run(self, config_path: Path = Path('config.txt')) -> None:
        """
        Run the interactive setup wizard synchronously.

        Args:
            config_path: Path to the configuration file to write.
        """
        config_path = Path(config_path)
        print("=== Discord Music Bot Setup Wizard ===")
        print("This wizard will help you create or update your config.txt file.\n")

        existing_config = {}
        if config_path.exists():
            print(f"Found existing config at {config_path}. Values will be updated.")
            with open(config_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, val = line.split('=', 1)
                        existing_config[key.strip().lower()] = val.strip()

        config_data = {}

        # Token
        while True:
            token = getpass("Enter Discord Bot Token (input will be hidden): ").strip()
            if not token:
                token = existing_config.get('discord_bot_token', '')
            if token:
                config_data['discord_bot_token'] = token
                break
            print("Error: Discord bot token is required.")

        # Command Channel ID
        while True:
            existing_channel = existing_config.get('discord_command_channel_id') or existing_config.get('command_channel_id', '')
            channel_id = input(f"Enter Command Channel ID (optional, press Enter to skip) [{existing_channel}]: ").strip()
            if not channel_id:
                channel_id = existing_channel

            if not channel_id:
                config_data['command_channel_id'] = ''
                config_data['discord_command_channel_id'] = ''
                break
            if channel_id.isdigit():
                config_data['command_channel_id'] = channel_id
                config_data['discord_command_channel_id'] = channel_id
                break
            print("Error: Command Channel ID must be numeric.")

        # Playlists Directory
        while True:
            existing_pl = existing_config.get('playlists_directory') or existing_config.get('playlists_dir', './playlists')
            playlists_dir = input(f"Enter Playlists Directory path [{existing_pl}]: ").strip()
            if not playlists_dir:
                playlists_dir = existing_pl

            p = Path(playlists_dir)
            try:
                p.mkdir(parents=True, exist_ok=True)
                config_data['playlists_directory'] = playlists_dir
                break
            except Exception as e:
                print(f"Error creating/verifying directory: {e}")

        # YouTube Auth
        existing_auth = existing_config.get('youtube_auth_mode', 'disabled')
        auth_mode = input(f"Enable YouTube Auth? (oauth, token, disabled) [{existing_auth}]: ").strip()
        if not auth_mode:
            auth_mode = existing_auth
        if auth_mode not in ('oauth', 'token', 'disabled'):
            auth_mode = 'disabled'

        config_data['youtube_auth_mode'] = auth_mode

        if auth_mode == 'oauth':
            client_id = input(f"Enter YouTube Client ID [{existing_config.get('youtube_client_id', '')}]: ").strip()
            if not client_id:
                client_id = existing_config.get('youtube_client_id', '')
            config_data['youtube_client_id'] = client_id

            client_secret = getpass("Enter YouTube Client Secret: ").strip()
            if not client_secret:
                client_secret = existing_config.get('youtube_client_secret', '')
            config_data['youtube_client_secret'] = client_secret
        else:
            config_data['youtube_client_id'] = existing_config.get('youtube_client_id', '')
            config_data['youtube_client_secret'] = existing_config.get('youtube_client_secret', '')

        # All defaults
        all_defaults = {
            'discord_bot_token': '',
            'command_channel_id': '',
            'discord_command_channel_id': '',
            'command_prefix': '!',
            'playlists_directory': './playlists',
            'supported_formats': '.mp3,.flac,.ogg,.wav',
            'youtube_auth_mode': 'disabled',
            'youtube_client_id': '',
            'youtube_client_secret': '',
            'youtube_access_token': '',
            'youtube_refresh_token': '',
            'idle_status': 'Ready to play',
            'playing_status': 'Playing: {title}',
            'default_volume': '75',
            'loop_mode': 'off',
            'max_queue_size': '100',
            'auto_leave': 'true',
            'auto_leave_delay': '300',
            'dj_role_name': 'DJ',
            'log_level': 'INFO',
            'log_file': './logs/bot.log',
            'log_to_file': 'true',
            'log_to_console': 'true',
            'log_commands': 'true',
            'log_discord_internals': 'false',
            'log_ytdlp_verbose': 'false',
            'log_audio_buffer': 'false',
            'log_rotation_mb': '10',
            'log_backup_count': '5',
            'max_history_size': '50',
            'data_directory': './data',
        }

        # Merge defaults -> existing -> wizard inputs
        final_values = dict(all_defaults)
        final_values.update(existing_config)
        final_values.update(config_data)

        # Write config
        print(f"\nWriting configuration to {config_path}...")

        example_template = Path('config.example.txt')
        if not example_template.exists():
            example_template = Path(__file__).resolve().parent.parent / 'config.example.txt'

        if example_template.exists():
            # Use config.example.txt as template to preserve exact formatting
            lines = []
            with open(example_template, 'r', encoding='utf-8') as f:
                for line in f:
                    stripped = line.strip()
                    if stripped and not stripped.startswith('#') and '=' in stripped:
                        key, _ = stripped.split('=', 1)
                        clean_key = key.strip().lower()
                        # Map alias keys
                        val = final_values.get(clean_key)
                        if val is None:
                            if clean_key == 'discord_command_channel_id':
                                val = final_values.get('command_channel_id', '')
                            elif clean_key == 'playlists_directory':
                                val = final_values.get('playlists_dir', './playlists')
                            else:
                                val = ''
                        lines.append(f"{key.strip()}={val}\n")
                    else:
                        lines.append(line)
            content = "".join(lines)
        else:
            # Fallback to built-in template
            content = FULL_CONFIG_TEMPLATE.format(**final_values)

        with open(config_path, 'w', encoding='utf-8') as f:
            f.write(content)

        print("\nSetup complete! All default options and comments have been written to config.txt.")
        print("You can now start the bot using: python3 main.py")

    async def run_async(self, config_path: Path = Path('config.txt')) -> None:
        """Asynchronous wrapper for running the wizard."""
        await asyncio.to_thread(self.run, config_path)


if __name__ == '__main__':
    wizard = SetupWizard()
    wizard.run(Path('config.txt'))
