import discord
import asyncio
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

class PresenceManager:
    """Manages the bot's rich presence on Discord.
    
    Handles transitions between idle, playing, and paused states with
    debouncing to avoid hitting Discord's rate limits when tracks change rapidly.
    """

    def __init__(self, bot, idle_status: str = "Idle", playing_status_template: str = "Playing: {title}"):
        self.bot = bot
        self.idle_status = idle_status
        self.playing_status_template = playing_status_template
        self._lock = asyncio.Lock()
        self._last_update_time = 0.0
        self._min_interval = 5.0  # minimum seconds between Discord API calls
        self._pending_task: Optional[asyncio.Task] = None
        self._current_state: Optional[str] = None  # track current state to avoid redundant updates

    async def _do_update(self, activity: discord.Activity, status: discord.Status, state_key: str):
        """Execute the actual Discord presence update with rate limiting."""
        async with self._lock:
            # Skip if state hasn't changed (e.g. repeated idle calls)
            if self._current_state == state_key:
                return

            now = time.time()
            elapsed = now - self._last_update_time
            if elapsed < self._min_interval:
                await asyncio.sleep(self._min_interval - elapsed)

            try:
                await self.bot.change_presence(activity=activity, status=status)
                self._last_update_time = time.time()
                self._current_state = state_key
                logger.debug(f"Presence updated: {state_key}")
            except Exception as e:
                logger.error(f"Failed to update presence: {e}")

    def _schedule_update(self, activity: discord.Activity, status: discord.Status, state_key: str):
        """Schedule a presence update, cancelling any pending one (debounce)."""
        if self._pending_task and not self._pending_task.done():
            self._pending_task.cancel()
        self._pending_task = asyncio.ensure_future(self._do_update(activity, status, state_key))

    async def set_idle(self):
        """Set the bot's presence to idle status (custom status from config)."""
        activity = discord.CustomActivity(name=self.idle_status)
        self._schedule_update(activity, discord.Status.online, f"idle:{self.idle_status}")
        logger.debug(f"Presence scheduled: idle -> '{self.idle_status}'")

    async def set_playing(self, title: str, artist: Optional[str] = None, playlist: Optional[str] = None):
        """Set the bot's presence to show currently playing track."""
        kwargs = {
            "title": title or "Unknown Title",
            "artist": artist or "Unknown Artist",
            "playlist": playlist or ""
        }

        status_text = self.playing_status_template.format(**kwargs).strip()
        # Clean up any dangling separators if some info is missing
        if status_text.endswith("-"):
            status_text = status_text[:-1].strip()

        activity = discord.Activity(type=discord.ActivityType.listening, name=status_text)
        self._schedule_update(activity, discord.Status.online, f"playing:{status_text}")
        logger.debug(f"Presence scheduled: playing -> '{status_text}'")

    async def set_paused(self):
        """Set the bot's presence to paused status."""
        activity = discord.Activity(type=discord.ActivityType.listening, name="Paused")
        self._schedule_update(activity, discord.Status.idle, "paused")
        logger.debug("Presence scheduled: paused")

