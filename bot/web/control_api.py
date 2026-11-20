"""
Internal IPC Control API Cog for DiscordMusicBot.
Provides an aiohttp HTTP server for local RPC and NDJSON event streaming.
"""

import os
import re
import time
import json
import math
import random
import logging
import asyncio
import hmac
from pathlib import Path
from typing import Optional, Dict, Any, Set, List

from aiohttp import web
import discord
from discord.ext import commands

from bot.config import BotConfig
from bot.audio.player import GuildPlayer, PlayerState
from bot.audio.source import AudioTrack, SourceType
from bot.audio.queue import LoopMode
from bot.discord.permissions import get_user_permission, PermissionLevel

logger = logging.getLogger(__name__)

TIER_ORDER = {
    'none': 0,
    'user': 1,
    'dj': 2,
    'admin': 3,
    'owner': 4
}

ACTION_MIN_TIERS = {
    'me': 0,
    'guild.state': 1,
    'guild.channels': 1,
    'join': 1,
    'play': 1,
    'play.local': 1,
    'pause': 2,
    'resume': 2,
    'stop': 2,
    'skip': 2,
    'previous': 2,
    'restart': 2,
    'seek': 2,
    'volume': 2,
    'loop': 2,
    'queue.get': 1,
    'queue.remove': 2,
    'queue.move': 2,
    'queue.clear': 2,
    'queue.shuffle': 2,
    'history': 1,
    'playlists.list': 1,
    'playlists.get': 1,
    'leave': 3,
    'playlists.reload': 3,
}


def clean_ansi(text: str) -> str:
    """Removes ANSI terminal escape codes from string."""
    return re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', str(text)).strip()


class ControlApiCog(commands.Cog):
    """Cog running local HTTP IPC server for bot control."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.ipc_port: Optional[int] = None
        self.ipc_token: Optional[str] = None
        self.app: Optional[web.Application] = None
        self.runner: Optional[web.AppRunner] = None
        self.site: Optional[web.TCPSite] = None
        self._start_time = time.time()
        self._app_info: Optional[discord.AppInfo] = None
        self._app_info_time: float = 0.0
        self._events_task: Optional[asyncio.Task] = None
        self._event_subscribers: Set[asyncio.Queue] = set()
        self._last_guild_states: Dict[int, Dict[str, Any]] = {}
        self._last_guild_queues: Dict[int, Dict[str, Any]] = {}
        self._playback_trackers: Dict[int, Dict[str, Any]] = {}

    async def cog_load(self):
        port_env = os.getenv("MUSICBOT_IPC_PORT")
        token_env = os.getenv("MUSICBOT_IPC_TOKEN")

        if not port_env or not token_env:
            logger.debug("MUSICBOT_IPC_PORT and MUSICBOT_IPC_TOKEN not both set; control API disabled (plain mode).")
            return

        try:
            self.ipc_port = int(port_env)
            self.ipc_token = token_env
        except ValueError:
            logger.error(f"Invalid MUSICBOT_IPC_PORT: {port_env}")
            return

        self.app = web.Application()
        self.app.router.add_post("/rpc", self.handle_rpc)
        self.app.router.add_get("/events", self.handle_events)
        self.app.router.add_get("/health", self.handle_health)

        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, "127.0.0.1", self.ipc_port)
        await self.site.start()

        self._events_task = asyncio.create_task(self._events_worker())
        logger.info(f"Control API listening on 127.0.0.1:{self.ipc_port}")

    async def cog_unload(self):
        if self._events_task:
            self._events_task.cancel()
            try:
                await self._events_task
            except asyncio.CancelledError:
                pass
            self._events_task = None

        for q in list(self._event_subscribers):
            try:
                q.put_nowait(None)
            except Exception:
                pass
        self._event_subscribers.clear()

        if self.runner:
            await self.runner.cleanup()
            self.runner = None
            self.site = None
            logger.info("Control API stopped.")

    def _check_auth(self, request: web.Request) -> bool:
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return False
        token = auth[7:].strip()
        if not self.ipc_token:
            return False
        return hmac.compare_digest(token, self.ipc_token)

    async def handle_health(self, request: web.Request) -> web.Response:
        if not self._check_auth(request):
            return web.Response(status=401, text="Unauthorized")
        return web.json_response({"ok": True, "ready": self.bot.is_ready()})

    async def get_owner_ids(self) -> Set[int]:
        now = time.time()
        if not self._app_info or (now - self._app_info_time > 600):
            try:
                self._app_info = await self.bot.application_info()
                self._app_info_time = now
            except Exception as e:
                logger.warning(f"Failed to fetch application_info: {e}")

        owner_ids = set()
        if self._app_info:
            if getattr(self._app_info, 'owner', None):
                owner_ids.add(self._app_info.owner.id)
            if getattr(self._app_info, 'team', None) and self._app_info.team.members:
                for member in self._app_info.team.members:
                    owner_ids.add(member.id)

        cfg = getattr(self.bot, 'config', None)
        if cfg:
            owner_ids.update(getattr(cfg, 'panel_owner_ids_set', set()))

        return owner_ids

    async def tier(self, user_id: int, guild: Optional[discord.Guild]) -> str:
        if user_id == 0:
            return 'owner'
        owner_ids = await self.get_owner_ids()
        if user_id in owner_ids:
            return 'owner'

        if not guild:
            return 'none'

        member = guild.get_member(user_id)
        if member is None:
            try:
                member = await guild.fetch_member(user_id)
            except (discord.NotFound, discord.HTTPException):
                member = None

        if member is None:
            return 'none'

        if member.guild_permissions.administrator or member.guild_permissions.manage_guild:
            return 'admin'

        dj_role_name = getattr(self.bot.config, 'dj_role_name', 'DJ')
        perm_level = get_user_permission(member, dj_role_name)
        if perm_level >= PermissionLevel.DJ:
            return 'dj'

        return 'user'

    def get_player(self, guild_id: int) -> GuildPlayer:
        if guild_id not in self.bot._players:
            self.bot._players[guild_id] = GuildPlayer(self.bot, guild_id)
            default_vol = getattr(self.bot.config, 'default_volume', 75)
            self.bot._players[guild_id].volume = default_vol / 100.0
        return self.bot._players[guild_id]

    async def handle_rpc(self, request: web.Request) -> web.Response:
        if not self._check_auth(request):
            return web.Response(status=401, text="Unauthorized")

        if not self.bot.is_ready():
            try:
                await asyncio.wait_for(self.bot.wait_until_ready(), timeout=30.0)
            except asyncio.TimeoutError:
                return web.json_response({
                    "ok": False,
                    "code": "BOT_OFFLINE",
                    "error": "Bot is still starting"
                })

        try:
            body = await request.json()
        except Exception:
            return web.json_response({
                "ok": False,
                "code": "BAD_REQUEST",
                "error": "Invalid JSON body"
            })

        action = body.get("action")
        user_id_raw = body.get("userId")
        guild_id_raw = body.get("guildId")
        params = body.get("params") or {}

        if not action or not user_id_raw:
            return web.json_response({
                "ok": False,
                "code": "BAD_REQUEST",
                "error": "Missing action or userId"
            })

        try:
            user_id = int(user_id_raw)
        except ValueError:
            return web.json_response({
                "ok": False,
                "code": "BAD_REQUEST",
                "error": "Invalid userId format"
            })

        guild: Optional[discord.Guild] = None
        if guild_id_raw is not None:
            try:
                guild = self.bot.get_guild(int(guild_id_raw))
            except ValueError:
                return web.json_response({
                    "ok": False,
                    "code": "BAD_REQUEST",
                    "error": "Invalid guildId format"
                })

        min_tier_val = ACTION_MIN_TIERS.get(action)
        if min_tier_val is None:
            return web.json_response({
                "ok": False,
                "code": "BAD_REQUEST",
                "error": f"Unknown action: {action}"
            })

        user_tier_name = await self.tier(user_id, guild)
        user_tier_val = TIER_ORDER.get(user_tier_name, 0)

        # Non-zero min tier requires appropriate permission
        if min_tier_val > 0:
            if not guild:
                owner_ids = await self.get_owner_ids()
                if user_id not in owner_ids:
                    return web.json_response({
                        "ok": False,
                        "code": "BAD_REQUEST",
                        "error": "Guild context required for this action"
                    })
            elif user_tier_val < min_tier_val:
                return web.json_response({
                    "ok": False,
                    "code": "FORBIDDEN",
                    "error": f"Requires tier {min_tier_val}, your tier is {user_tier_name}"
                })

        try:
            handler = getattr(self, f"_action_{action.replace('.', '_')}", None)
            if not handler:
                return web.json_response({
                    "ok": False,
                    "code": "BAD_REQUEST",
                    "error": f"Action handler not implemented: {action}"
                })
            result = await handler(user_id=user_id, guild=guild, params=params, tier=user_tier_name)
            return web.json_response(result)
        except Exception as e:
            clean_err = clean_ansi(str(e))
            logger.error(f"Error executing RPC action {action}: {clean_err}", exc_info=True)
            return web.json_response({
                "ok": False,
                "code": "INTERNAL",
                "error": clean_err or "Internal bot error"
            })

    # -------------------------------------------------------------
    # Action Handlers
    # -------------------------------------------------------------

    async def _action_me(self, user_id: int, guild: Optional[discord.Guild], params: Dict[str, Any], tier: str) -> Dict[str, Any]:
        owner_ids = await self.get_owner_ids()
        is_owner = (user_id in owner_ids)

        bot_user = self.bot.user
        uptime_s = int(time.time() - self._start_time)

        user_guilds = []
        for g in self.bot.guilds:
            g_tier = 'owner' if is_owner else await self.tier(user_id, g)
            if g_tier != 'none' or is_owner:
                user_guilds.append({
                    "id": str(g.id),
                    "name": g.name,
                    "icon": g.icon.url if g.icon else None,
                    "tier": g_tier
                })

        from bot import __version__ as bot_version
        return {
            "ok": True,
            "data": {
                "bot": {
                    "id": str(bot_user.id) if bot_user else "",
                    "name": bot_user.name if bot_user else "DiscordMusicBot",
                    "avatar": bot_user.display_avatar.url if bot_user else None,
                    "version": bot_version,
                    "latencyMs": round(self.bot.latency * 1000, 1),
                    "uptimeS": uptime_s,
                    "guildCount": len(self.bot.guilds)
                },
                "ownerIds": [str(x) for x in owner_ids],
                "isOwner": is_owner,
                "guilds": user_guilds
            }
        }

    async def _action_guild_state(self, user_id: int, guild: discord.Guild, params: Dict[str, Any], tier: str) -> Dict[str, Any]:
        state_data = await self._build_guild_state(guild)
        return {"ok": True, "data": state_data}

    async def _build_guild_state(self, guild: discord.Guild) -> Dict[str, Any]:
        player: Optional[GuildPlayer] = self.bot._players.get(guild.id)
        vc = guild.voice_client

        voice_channel = None
        if vc and getattr(vc, 'channel', None):
            voice_channel = {
                "id": str(vc.channel.id),
                "name": vc.channel.name
            }

        is_playing = (player.state == PlayerState.PLAYING) if player else False
        is_paused = (player.state == PlayerState.PAUSED) if player else False

        current_data = None
        if player and (is_playing or is_paused):
            curr = await player.queue.current()
            if curr:
                source_type_str = curr.source_type.name.lower() if hasattr(curr.source_type, 'name') else str(curr.source_type).lower()

                tracker = self._playback_trackers.get(guild.id)
                now = time.time()
                curr_key = f"{curr.title}_{curr.duration}_{curr.source_uri}"
                if not tracker or tracker.get("key") != curr_key:
                    tracker = {
                        "key": curr_key,
                        "start_time": now,
                        "seek_offset": 0.0,
                        "paused_at": now if is_paused else None,
                        "total_paused": 0.0
                    }
                    self._playback_trackers[guild.id] = tracker
                else:
                    if is_paused and tracker.get("paused_at") is None:
                        tracker["paused_at"] = now
                    elif is_playing and tracker.get("paused_at") is not None:
                        tracker["total_paused"] += (now - tracker["paused_at"])
                        tracker["paused_at"] = None

                if tracker.get("paused_at") is not None:
                    elapsed = tracker["paused_at"] - tracker["start_time"] - tracker["total_paused"] + tracker["seek_offset"]
                else:
                    elapsed = now - tracker["start_time"] - tracker["total_paused"] + tracker["seek_offset"]

                elapsed = max(0.0, elapsed)
                if curr.duration and curr.duration > 0:
                    elapsed = min(elapsed, float(curr.duration))

                current_data = {
                    "title": curr.title,
                    "artist": curr.artist or "",
                    "duration": curr.duration,
                    "elapsed": round(elapsed, 1),
                    "thumbnail": curr.thumbnail_url,
                    "url": curr.source_uri,
                    "sourceType": source_type_str,
                    "requester": curr.requester_name
                }
        else:
            self._playback_trackers.pop(guild.id, None)

        volume_pct = int(player.volume * 100) if player else getattr(self.bot.config, 'default_volume', 75)
        loop_mode = player.queue.loop_mode.name.lower() if player else 'off'
        queue_len = len(player.queue) if player else 0

        return {
            "voiceChannel": voice_channel,
            "isPlaying": is_playing,
            "isPaused": is_paused,
            "current": current_data,
            "volume": volume_pct,
            "loop": loop_mode,
            "queueLength": queue_len
        }

    async def _action_guild_channels(self, user_id: int, guild: discord.Guild, params: Dict[str, Any], tier: str) -> Dict[str, Any]:
        member = guild.get_member(user_id)
        user_vc_id = None
        if member and member.voice and member.voice.channel:
            user_vc_id = str(member.voice.channel.id)

        channels = []
        for ch in guild.voice_channels:
            channels.append({
                "id": str(ch.id),
                "name": ch.name,
                "memberCount": len(ch.members),
                "userIsHere": any(m.id == user_id for m in ch.members)
            })

        return {
            "ok": True,
            "data": {
                "channels": channels,
                "userVoiceChannelId": user_vc_id
            }
        }

    async def _action_join(self, user_id: int, guild: discord.Guild, params: Dict[str, Any], tier: str) -> Dict[str, Any]:
        ch_id = params.get("channelId")
        member = guild.get_member(user_id)

        target_channel = None
        if not ch_id or ch_id == "mine":
            if not member or not member.voice or not member.voice.channel:
                return {"ok": False, "code": "NOT_IN_VOICE", "error": "You are not currently in a voice channel"}
            target_channel = member.voice.channel
        else:
            try:
                target_channel = guild.get_channel(int(ch_id))
            except ValueError:
                return {"ok": False, "code": "BAD_REQUEST", "error": "Invalid channelId format"}

            if not target_channel or not isinstance(target_channel, discord.VoiceChannel):
                return {"ok": False, "code": "NOT_FOUND", "error": "Voice channel not found"}

        if guild.voice_client:
            await guild.voice_client.move_to(target_channel)
        else:
            await target_channel.connect(self_deaf=True)

        return {"ok": True, "data": {"channelId": str(target_channel.id), "name": target_channel.name}}

    async def _action_leave(self, user_id: int, guild: discord.Guild, params: Dict[str, Any], tier: str) -> Dict[str, Any]:
        if guild.voice_client:
            player = self.get_player(guild.id)
            await player.destroy()
            self.bot._players.pop(guild.id, None)
            try:
                await guild.voice_client.disconnect()
            except Exception:
                pass
        return {"ok": True, "data": {}}

    async def _action_play(self, user_id: int, guild: discord.Guild, params: Dict[str, Any], tier: str) -> Dict[str, Any]:
        query = str(params.get("query", "")).strip()
        if not query:
            return {"ok": False, "code": "BAD_REQUEST", "error": "Query is required"}

        # Disallow raw local file paths via /play (local files only through play.local)
        if Path(query).exists():
            return {
                "ok": False,
                "code": "BAD_REQUEST",
                "error": "Direct local paths are not allowed; use the Local Playlists tab."
            }

        member = guild.get_member(user_id)
        requester_name = member.display_name if member else str(user_id)

        # Connect if not connected
        if not guild.voice_client:
            target_channel = None
            if params.get("channelId"):
                try:
                    target_channel = guild.get_channel(int(params["channelId"]))
                except ValueError:
                    pass
            elif member and member.voice and member.voice.channel:
                target_channel = member.voice.channel

            if not target_channel or not isinstance(target_channel, discord.VoiceChannel):
                return {
                    "ok": False,
                    "code": "NOT_IN_VOICE",
                    "error": "Bot is not in voice and no voice channel was specified/detected."
                }
            await target_channel.connect(self_deaf=True)

        player = self.get_player(guild.id)

        try:
            if "list=" in query and ("youtube.com" in query or "youtu.be" in query):
                tracks = await player.play_youtube_playlist(
                    query,
                    requester_id=user_id,
                    requester_name=requester_name
                )
                return {
                    "ok": True,
                    "data": {
                        "type": "playlist",
                        "count": len(tracks)
                    }
                }
            else:
                track = await player.play_youtube(
                    query,
                    requester_id=user_id,
                    requester_name=requester_name
                )
                return {
                    "ok": True,
                    "data": {
                        "type": "track",
                        "title": track.title,
                        "artist": track.artist,
                        "duration": track.duration
                    }
                }
        except Exception as e:
            clean_err = clean_ansi(str(e))
            return {"ok": False, "code": "INTERNAL", "error": clean_err}

    async def _action_play_local(self, user_id: int, guild: discord.Guild, params: Dict[str, Any], tier: str) -> Dict[str, Any]:
        playlist_name = params.get("playlist")
        file_name = params.get("file")
        shuffle = bool(params.get("shuffle", False))

        if not playlist_name:
            return {"ok": False, "code": "BAD_REQUEST", "error": "Playlist name required"}

        if not self.bot.playlist_manager:
            return {"ok": False, "code": "INTERNAL", "error": "Playlist manager not initialized"}

        playlist = self.bot.playlist_manager.get_playlist(playlist_name)
        if not playlist:
            return {"ok": False, "code": "NOT_FOUND", "error": f"Playlist '{playlist_name}' not found"}

        member = guild.get_member(user_id)
        requester_name = member.display_name if member else str(user_id)

        if not guild.voice_client:
            target_channel = None
            if params.get("channelId"):
                try:
                    target_channel = guild.get_channel(int(params["channelId"]))
                except ValueError:
                    pass
            elif member and member.voice and member.voice.channel:
                target_channel = member.voice.channel

            if not target_channel or not isinstance(target_channel, discord.VoiceChannel):
                return {
                    "ok": False,
                    "code": "NOT_IN_VOICE",
                    "error": "You must join a voice channel or specify channelId."
                }
            await target_channel.connect(self_deaf=True)

        player = self.get_player(guild.id)

        if file_name:
            ptr = next((t for t in playlist.tracks if t.filename == file_name), None)
            if not ptr:
                return {"ok": False, "code": "NOT_FOUND", "error": f"File '{file_name}' not in playlist"}
            track = AudioTrack(
                title=ptr.title,
                artist=ptr.artist,
                album=ptr.album,
                duration=ptr.duration,
                source_type=SourceType.LOCAL_FILE,
                source_uri=str(ptr.file_path),
                requester_id=user_id,
                requester_name=requester_name,
                playlist_name=playlist.name
            )
            await player.play(track)
            return {"ok": True, "data": {"type": "track", "title": track.title}}
        else:
            if not playlist.tracks:
                return {"ok": False, "code": "BAD_REQUEST", "error": "Playlist is empty"}

            tracks = [
                AudioTrack(
                    title=ptr.title,
                    artist=ptr.artist,
                    album=ptr.album,
                    duration=ptr.duration,
                    source_type=SourceType.LOCAL_FILE,
                    source_uri=str(ptr.file_path),
                    requester_id=user_id,
                    requester_name=requester_name,
                    playlist_name=playlist.name
                )
                for ptr in playlist.tracks
            ]
            if shuffle:
                random.shuffle(tracks)

            await player.play(tracks[0])
            if len(tracks) > 1:
                await player.queue.add_many(tracks[1:])

            return {"ok": True, "data": {"type": "playlist", "count": len(tracks)}}

    async def _action_pause(self, user_id: int, guild: discord.Guild, params: Dict[str, Any], tier: str) -> Dict[str, Any]:
        player = self.get_player(guild.id)
        await player.pause()
        return {"ok": True, "data": {}}

    async def _action_resume(self, user_id: int, guild: discord.Guild, params: Dict[str, Any], tier: str) -> Dict[str, Any]:
        player = self.get_player(guild.id)
        await player.resume()
        return {"ok": True, "data": {}}

    async def _action_stop(self, user_id: int, guild: discord.Guild, params: Dict[str, Any], tier: str) -> Dict[str, Any]:
        player = self.get_player(guild.id)
        await player.stop()
        return {"ok": True, "data": {}}

    async def _action_skip(self, user_id: int, guild: discord.Guild, params: Dict[str, Any], tier: str) -> Dict[str, Any]:
        player = self.get_player(guild.id)
        await player.skip()
        return {"ok": True, "data": {}}

    async def _action_previous(self, user_id: int, guild: discord.Guild, params: Dict[str, Any], tier: str) -> Dict[str, Any]:
        player = self.get_player(guild.id)
        await player.previous()
        return {"ok": True, "data": {}}

    async def _action_restart(self, user_id: int, guild: discord.Guild, params: Dict[str, Any], tier: str) -> Dict[str, Any]:
        player = self.get_player(guild.id)
        await player.seek(0)
        tracker = self._playback_trackers.get(guild.id)
        if tracker:
            now = time.time()
            tracker["start_time"] = now
            tracker["seek_offset"] = 0.0
            tracker["paused_at"] = now if (player.state == PlayerState.PAUSED) else None
            tracker["total_paused"] = 0.0
        return {"ok": True, "data": {}}

    async def _action_seek(self, user_id: int, guild: discord.Guild, params: Dict[str, Any], tier: str) -> Dict[str, Any]:
        seconds = float(params.get("seconds", 0))
        player = self.get_player(guild.id)
        await player.seek(seconds)
        tracker = self._playback_trackers.get(guild.id)
        if tracker:
            now = time.time()
            tracker["start_time"] = now
            tracker["seek_offset"] = seconds
            tracker["paused_at"] = now if (player.state == PlayerState.PAUSED) else None
            tracker["total_paused"] = 0.0
        return {"ok": True, "data": {"seconds": seconds}}

    async def _action_volume(self, user_id: int, guild: discord.Guild, params: Dict[str, Any], tier: str) -> Dict[str, Any]:
        vol_pct = max(0, min(100, int(params.get("volume", 75))))
        player = self.get_player(guild.id)
        await player.set_volume(vol_pct / 100.0)
        return {"ok": True, "data": {"volume": vol_pct}}

    async def _action_loop(self, user_id: int, guild: discord.Guild, params: Dict[str, Any], tier: str) -> Dict[str, Any]:
        mode_str = str(params.get("mode", "off")).upper()
        mode = LoopMode.OFF
        if mode_str == "TRACK":
            mode = LoopMode.TRACK
        elif mode_str == "QUEUE":
            mode = LoopMode.QUEUE

        player = self.get_player(guild.id)
        await player.set_loop(mode)
        return {"ok": True, "data": {"mode": mode.name.lower()}}

    async def _action_queue_get(self, user_id: int, guild: discord.Guild, params: Dict[str, Any], tier: str) -> Dict[str, Any]:
        player = self.get_player(guild.id)
        curr = await player.queue.current()
        upcoming = await player.queue.upcoming()

        current_data = None
        if curr:
            source_type_str = curr.source_type.name.lower() if hasattr(curr.source_type, 'name') else str(curr.source_type).lower()
            current_data = {
                "title": curr.title,
                "artist": curr.artist or "",
                "duration": curr.duration,
                "thumbnail": curr.thumbnail_url,
                "url": curr.source_uri,
                "sourceType": source_type_str,
                "requester": curr.requester_name
            }

        upcoming_list = []
        for idx, t in enumerate(upcoming):
            upcoming_list.append({
                "index": idx,
                "title": t.title,
                "artist": t.artist or "",
                "duration": t.duration,
                "thumbnail": t.thumbnail_url,
                "requester": t.requester_name
            })

        return {
            "ok": True,
            "data": {
                "current": current_data,
                "upcoming": upcoming_list,
                "loop": player.queue.loop_mode.name.lower(),
                "length": len(player.queue)
            }
        }

    async def _action_queue_remove(self, user_id: int, guild: discord.Guild, params: Dict[str, Any], tier: str) -> Dict[str, Any]:
        index = int(params.get("index", -1))
        player = self.get_player(guild.id)
        removed = await player.queue.remove(index)
        if not removed:
            return {"ok": False, "code": "NOT_FOUND", "error": "Queue item not found"}
        return {"ok": True, "data": {"title": removed.title}}

    async def _action_queue_move(self, user_id: int, guild: discord.Guild, params: Dict[str, Any], tier: str) -> Dict[str, Any]:
        from_idx = int(params.get("from", -1))
        to_idx = int(params.get("to", -1))
        player = self.get_player(guild.id)
        ok = await player.queue.move(from_idx, to_idx)
        if not ok:
            return {"ok": False, "code": "BAD_REQUEST", "error": "Invalid queue positions"}
        return {"ok": True, "data": {}}

    async def _action_queue_clear(self, user_id: int, guild: discord.Guild, params: Dict[str, Any], tier: str) -> Dict[str, Any]:
        player = self.get_player(guild.id)
        await player.queue.clear()
        return {"ok": True, "data": {}}

    async def _action_queue_shuffle(self, user_id: int, guild: discord.Guild, params: Dict[str, Any], tier: str) -> Dict[str, Any]:
        player = self.get_player(guild.id)
        await player.queue.shuffle()
        return {"ok": True, "data": {}}

    async def _action_history(self, user_id: int, guild: discord.Guild, params: Dict[str, Any], tier: str) -> Dict[str, Any]:
        limit = min(50, max(1, int(params.get("limit", 20))))
        player = self.get_player(guild.id)
        history_tracks = list(player.history)[-limit:]
        history_data = []
        for t in reversed(history_tracks):
            history_data.append({
                "title": t.title,
                "artist": t.artist or "",
                "duration": t.duration,
                "thumbnail": t.thumbnail_url,
                "requester": t.requester_name
            })
        return {"ok": True, "data": history_data}

    async def _action_playlists_list(self, user_id: int, guild: Optional[discord.Guild], params: Dict[str, Any], tier: str) -> Dict[str, Any]:
        if not self.bot.playlist_manager:
            return {"ok": True, "data": []}
        pl_dir = self.bot.playlist_manager.playlists_dir
        all_pl = {p.name.lower(): p for p in self.bot.playlist_manager.get_all()}

        result = []
        if pl_dir.exists() and pl_dir.is_dir():
            for entry in sorted(pl_dir.iterdir(), key=lambda e: e.name.lower()):
                if entry.is_dir() and not entry.name.startswith('.'):
                    p = all_pl.get(entry.name.lower())
                    count = p.track_count if p else 0
                    result.append({"name": entry.name, "trackCount": count})
        else:
            result = [{"name": p.name, "trackCount": p.track_count} for p in all_pl.values()]

        return {
            "ok": True,
            "data": result
        }

    async def _action_playlists_get(self, user_id: int, guild: Optional[discord.Guild], params: Dict[str, Any], tier: str) -> Dict[str, Any]:
        name = str(params.get("name", "")).strip()
        if not self.bot.playlist_manager:
            return {"ok": False, "code": "NOT_FOUND", "error": "Playlist manager unavailable"}

        playlist = self.bot.playlist_manager.get_playlist(name)
        if not playlist:
            await self.bot.playlist_manager.reload()
            playlist = self.bot.playlist_manager.get_playlist(name)
        if not playlist:
            # Check if directory exists on disk but has 0 tracks
            try:
                base_dir = self.bot.playlist_manager.playlists_dir.resolve()
                cand = (base_dir / name).resolve()
                if cand.exists() and cand.is_dir() and (cand == base_dir or base_dir in cand.parents):
                    return {
                        "ok": True,
                        "data": {
                            "name": cand.name,
                            "tracks": []
                        }
                    }
            except Exception:
                pass
            return {"ok": False, "code": "NOT_FOUND", "error": f"Playlist '{name}' not found"}

        return {
            "ok": True,
            "data": {
                "name": playlist.name,
                "tracks": [
                    {
                        "file": ptr.filename,
                        "title": ptr.title,
                        "artist": ptr.artist or "",
                        "duration": ptr.duration
                    }
                    for ptr in playlist.tracks
                ]
            }
        }

    async def _action_playlists_reload(self, user_id: int, guild: Optional[discord.Guild], params: Dict[str, Any], tier: str) -> Dict[str, Any]:
        if self.bot.playlist_manager:
            await self.bot.playlist_manager.reload()
        return {"ok": True, "data": {}}

    # -------------------------------------------------------------
    # NDJSON Event Stream (/events)
    # -------------------------------------------------------------

    async def handle_events(self, request: web.Request) -> web.StreamResponse:
        if not self._check_auth(request):
            return web.Response(status=401, text="Unauthorized")

        response = web.StreamResponse(
            status=200,
            reason="OK",
            headers={"Content-Type": "application/x-ndjson", "Cache-Control": "no-cache"}
        )
        await response.prepare(request)

        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._event_subscribers.add(queue)

        try:
            while True:
                evt = await queue.get()
                if evt is None:
                    break
                line = json.dumps(evt) + "\n"
                await response.write(line.encode("utf-8"))
        except (asyncio.CancelledError, ConnectionResetError):
            pass
        finally:
            self._event_subscribers.discard(queue)

        return response

    async def _events_worker(self):
        """Background loop taking periodic guild snapshots and emitting diffs."""
        last_ping = time.time()

        while True:
            try:
                await asyncio.sleep(1.0)
                if not self.bot.is_ready():
                    continue

                now = time.time()
                # 5s ping with live latency
                if now - last_ping >= 5.0:
                    last_ping = now
                    lat = None
                    try:
                        if getattr(self.bot, 'latency', None) is not None and not math.isinf(self.bot.latency):
                            lat = round(self.bot.latency * 1000, 1)
                    except Exception:
                        pass
                    self._broadcast_event({
                        "kind": "ping",
                        "data": {
                            "latencyMs": lat
                        }
                    })

                # Snapshot active guilds
                for guild in self.bot.guilds:
                    if not guild.voice_client and guild.id not in self.bot._players:
                        continue

                    # Check state
                    state = await self._build_guild_state(guild)
                    last_st = self._last_guild_states.get(guild.id)
                    if state != last_st:
                        self._last_guild_states[guild.id] = state
                        self._broadcast_event({
                            "kind": "state",
                            "guildId": str(guild.id),
                            "data": state
                        })

                    # Check queue length/current
                    player = self.bot._players.get(guild.id)
                    q_snap = {
                        "len": len(player.queue) if player else 0,
                        "loop": player.queue.loop_mode.name if player else "OFF",
                        "cur_idx": player.queue.current_index if player else -1
                    }
                    last_q = self._last_guild_queues.get(guild.id)
                    if q_snap != last_q:
                        self._last_guild_queues[guild.id] = q_snap
                        if player:
                            curr = await player.queue.current()
                            upcoming = await player.queue.upcoming()
                            self._broadcast_event({
                                "kind": "queue",
                                "guildId": str(guild.id),
                                "data": {
                                    "current": {
                                        "title": curr.title,
                                        "artist": curr.artist or "",
                                        "duration": curr.duration,
                                        "thumbnail": curr.thumbnail_url,
                                        "url": curr.source_uri,
                                        "requester": curr.requester_name
                                    } if curr else None,
                                    "upcoming": [
                                        {
                                            "index": idx,
                                            "title": t.title,
                                            "artist": t.artist or "",
                                            "duration": t.duration,
                                            "thumbnail": t.thumbnail_url,
                                            "requester": t.requester_name
                                        }
                                        for idx, t in enumerate(upcoming)
                                    ],
                                    "loop": player.queue.loop_mode.name.lower()
                                }
                            })
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in control_api events worker: {e}", exc_info=True)

    def _broadcast_event(self, evt: Dict[str, Any]):
        for q in list(self._event_subscribers):
            try:
                q.put_nowait(evt)
            except asyncio.QueueFull:
                pass


async def setup(bot: commands.Bot):
    await bot.add_cog(ControlApiCog(bot))
