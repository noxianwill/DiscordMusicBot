"""
Logging configuration for the Discord Music Bot.
"""
import re
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional, List, Union

ANSI_ESCAPE_RE = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')


class AnsiStripFilter(logging.Filter):
    """Logging filter to strip ANSI escape codes from log records (keeps files clean)."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = ANSI_ESCAPE_RE.sub('', record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(
                ANSI_ESCAPE_RE.sub('', arg) if isinstance(arg, str) else arg
                for arg in record.args
            )
        return True


class SecretFilter(logging.Filter):
    """Logging filter to redact sensitive tokens and secrets from log output."""
    def __init__(self, secrets: Optional[List[str]] = None):
        super().__init__()
        self.secrets = [s for s in (secrets or []) if s]

    def filter(self, record: logging.LogRecord) -> bool:
        """Filter log records and mask any secrets."""
        if not self.secrets:
            return True

        if isinstance(record.msg, str):
            msg = record.msg
            for secret in self.secrets:
                msg = msg.replace(secret, "***REDACTED***")
            record.msg = msg

        if isinstance(record.args, tuple):
            args = list(record.args)
            for i, arg in enumerate(args):
                if isinstance(arg, str):
                    for secret in self.secrets:
                        args[i] = args[i].replace(secret, "***REDACTED***")
            record.args = tuple(args)

        return True


def setup_logging(
    log_level: str = "INFO",
    log_file: Union[Path, str] = Path("./logs/bot.log"),
    log_to_file: bool = True,
    log_to_console: bool = True,
    log_discord_internals: bool = False,
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 5,
    secrets: Optional[List[str]] = None,
    log_dir: Optional[Union[Path, str]] = None,
) -> None:
    """
    Configure the logging system for the bot.

    Args:
        log_level: The string representation of the logging level.
        log_file: File path where logs should be written.
        log_to_file: Whether to write logs to file.
        log_to_console: Whether to write logs to terminal/stdout.
        log_discord_internals: Whether to include internal discord.py heartbeat/packet logs.
        max_bytes: Maximum size of the log file before rotating.
        backup_count: Number of rotated backup log files to retain.
        secrets: List of secret strings to redact from logs.
        log_dir: Backward-compatibility argument for log directory.
    """
    if secrets is None:
        secrets = []

    level = getattr(logging, log_level.upper(), logging.INFO)

    # Configure the root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Clear existing handlers to prevent duplicate lines on re-setup
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    formatter = logging.Formatter(
        '[%(asctime)s] [%(levelname)-8s] [%(name)-20s] %(message)s'
    )

    secret_filter = SecretFilter(secrets)
    ansi_filter = AnsiStripFilter()

    # Console handler
    if log_to_console:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        console_handler.addFilter(secret_filter)
        root_logger.addHandler(console_handler)

    # File handler
    if log_to_file:
        if log_dir is not None and log_file == Path("./logs/bot.log"):
            log_path = Path(log_dir) / "bot.log"
        else:
            log_path = Path(log_file)

        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8'
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        file_handler.addFilter(ansi_filter)
        file_handler.addFilter(secret_filter)
        root_logger.addHandler(file_handler)

    # Configure discord.py loggers:
    # If log_discord_internals is False, cap discord loggers to WARNING to avoid
    # thousands of heartbeat and raw gateway packet spam entries.
    discord_loggers = [
        logging.getLogger('discord'),
        logging.getLogger('discord.http'),
        logging.getLogger('discord.gateway'),
        logging.getLogger('discord.client'),
    ]
    for d_logger in discord_loggers:
        if log_discord_internals:
            d_logger.setLevel(level)
        else:
            d_logger.setLevel(logging.WARNING)
