"""
Entry point for running the Discord Music Bot.
"""

import argparse
import logging
import signal
import sys
import shutil
from pathlib import Path
from typing import Optional

from bot.config import ConfigLoader, load_config, BotConfig
from bot.logging_config import setup_logging
__version__ = "1.0.0"
from bot.setup_wizard import SetupWizard

logger = logging.getLogger("music_bot.main")


def print_diagnostics(config: BotConfig, config_ok: bool) -> None:
    """Print startup diagnostics for the bot."""
    print("============================================")
    print(f"Discord Music Bot v{__version__}")
    print("============================================")
    print(f"Configuration:  {'OK' if config_ok else 'FAILED'}")

    ffmpeg_path = shutil.which('ffmpeg')
    print(f"FFmpeg:         {'OK' if ffmpeg_path else 'NOT FOUND'}")

    playlists_dir = Path(config.playlists_directory)
    if playlists_dir.exists() and playlists_dir.is_dir():
        count = sum(1 for p in playlists_dir.iterdir() if p.is_dir())
        print(f"Playlists Dir:  OK ({count} playlists found in {playlists_dir})")
    else:
        print(f"Playlists Dir:  NOT FOUND ({playlists_dir})")

    deno_path = shutil.which('deno')
    print(f"Deno (JS Solver):{'OK' if deno_path else 'NOT FOUND (Install deno for YouTube challenge solving)'}")

    cookie_found = False
    for cp in [Path("cookies.txt"), Path("data/cookies.txt"), Path(config.data_directory) / "cookies.txt"]:
        if cp.exists():
            cookie_found = True
            print(f"Cookies:        OK ({cp} found)")
            break
    if not cookie_found:
        print("Cookies:        NOT FOUND (cookies.txt missing - needed for YouTube on cloud servers)")

    yt_mode = config.youtube_auth_mode
    youtube_status = f"API ({yt_mode})" if yt_mode != "disabled" else "yt-dlp stream only"
    print(f"YouTube:        {youtube_status}")
    raw_lvl = getattr(config, 'raw_log_level', config.log_level).upper()
    level_display = f"{config.log_level} ({raw_lvl})" if raw_lvl != config.log_level else config.log_level
    print(f"Log Level:      {level_display}")
    log_dest = str(config.log_file) if config.log_to_file else "Disabled"
    print(f"Log File:       {log_dest}")
    print(f"Log Console:    {'Enabled' if config.log_to_console else 'Disabled'}")
    print(f"Data Dir:       {config.data_directory}")
    print(f"Cmd Prefix:     {config.command_prefix}")
    print("============================================")


def handle_shutdown(signum, frame):
    """Handle graceful shutdown signals."""
    logger.info("Received shutdown signal. Exiting...")
    sys.exit(0)


def main() -> None:
    parser = argparse.ArgumentParser(description="Discord Music Bot")
    parser.add_argument("--setup", action="store_true", help="Run the interactive setup wizard")
    parser.add_argument("--check-config", action="store_true", help="Check configuration and print diagnostics")
    parser.add_argument("--config", type=str, default="config.txt", help="Path to configuration file")
    args = parser.parse_args()

    # Register signal handlers for clean shutdown (Windows compatible)
    try:
        signal.signal(signal.SIGINT, handle_shutdown)
        signal.signal(signal.SIGTERM, handle_shutdown)
    except Exception as e:
        logger.debug(f"Failed to setup signal handlers: {e}")

    config_path = Path(args.config)

    if args.setup:
        wizard = SetupWizard()
        wizard.run(config_path)
        sys.exit(0)

    # Initial setup logging with defaults
    setup_logging()

    if not config_path.exists():
        print(f"Error: {config_path} not found.")
        print("Please copy config.example.txt to config.txt and configure it.")
        print("Alternatively, run with --setup to launch the setup wizard.")
        sys.exit(1)

    config: Optional[BotConfig] = None
    config_ok = False
    try:
        config = load_config(config_path)
        config_ok = True
    except Exception as e:
        print(f"Configuration Error: {e}")
        if args.check_config:
            sys.exit(1)

    if args.check_config:
        if config:
            print_diagnostics(config, config_ok)
        else:
            print("Failed to load configuration.")
        sys.exit(0 if config_ok else 1)

    if not config_ok or not config:
        print("Failed to start due to configuration errors.")
        sys.exit(1)

    # Re-initialize logging with configured options
    setup_logging(
        log_level=config.log_level,
        log_file=config.log_file,
        log_to_file=config.log_to_file,
        log_to_console=config.log_to_console,
        log_discord_internals=config.log_discord_internals,
        max_bytes=config.log_rotation_mb * 1024 * 1024,
        backup_count=config.log_backup_count,
        secrets=[config.discord_bot_token, config.youtube_client_secret]
    )

    if not shutil.which('ffmpeg'):
        print("Warning: FFmpeg was not found in PATH. Audio playback will fail if FFmpeg is not installed.")

    print_diagnostics(config, config_ok)
    logger.info("Starting Discord Music Bot...")

    from bot import create_bot
    bot = create_bot(config)
    try:
        bot.run(config.discord_bot_token, log_handler=None)
    except Exception as e:
        logger.error(f"Failed to run bot: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
