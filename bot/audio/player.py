import asyncio
import collections
import logging
import queue
import subprocess
import threading
import time
import os
import re
import shutil
import sys
from enum import Enum, auto
from pathlib import Path
from typing import Optional, List, Dict, Any

import discord
import yt_dlp

from .source import AudioTrack, SourceType
from .queue import PlaybackQueue, LoopMode
from .voice import VoiceManager

logger = logging.getLogger(__name__)

def get_ytdlp_cmd() -> List[str]:
    """
    Returns the executable command list for running yt-dlp.
    Guarantees execution even if yt-dlp is not on system PATH by:
    1. Checking the virtualenv / Python bin directory where the running interpreter lives.
    2. Checking system PATH via shutil.which.
    3. Falling back to [sys.executable, '-m', 'yt_dlp'].
    """
    venv_bin = Path(sys.executable).parent
    for name in ('yt-dlp', 'yt-dlp.exe'):
        candidate = venv_bin / name
        if candidate.exists() and candidate.is_file():
            return [str(candidate)]

    which_bin = shutil.which('yt-dlp')
    if which_bin:
        return [which_bin]

    return [sys.executable, '-m', 'yt_dlp']


def find_cookie_file() -> Optional[Path]:
    """Finds cookies.txt across standard and fallback locations."""
    candidates = [
        Path("cookies.txt"),
        Path("data/cookies.txt"),
        Path.home() / "DiscordMusicBot" / "cookies.txt",
        Path.home() / "musicbot" / "cookies.txt",
    ]
    for p in candidates:
        try:
            if p.exists() and p.is_file() and p.stat().st_size > 0:
                return p
        except Exception:
            continue
    return None

def _get_cookie_header() -> Optional[str]:
    """Extracts critical cookies from cookies.txt for FFmpeg HTTP headers."""
    cookie_file = find_cookie_file()
    if cookie_file:
        try:
            cookies = []
            with open(cookie_file, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    parts = line.split('\t')
                    if len(parts) >= 7:
                        cookies.append(f"{parts[5]}={parts[6]}")
            if cookies:
                cookie_str = "; ".join(cookies)
                if len(cookie_str) > 4000:
                    critical = [
                        'SID', 'HSID', 'SSID', 'APISID', 'SAPISID',
                        '__Secure-1PSID', '__Secure-3PSID', '__Secure-1PAPISID', '__Secure-3PAPISID',
                        'LOGIN_INFO', 'PREF', 'VISITOR_INFO1_LIVE', '__Secure-BUCKET'
                    ]
                    filtered = [c for c in cookies if any(c.startswith(f"{k}=") for k in critical)]
                    cookie_str = "; ".join(filtered) if filtered else cookie_str[:4000]
                return cookie_str
        except Exception as e:
            logger.warning(f"Could not read cookies: {e}")
    return None

class YTDLPPipeAudio(discord.FFmpegPCMAudio):
    """Pipes audio directly from yt-dlp to FFmpeg stdin to eliminate 403 Forbidden errors."""
    def __init__(self, url: str, seek_seconds: float = 0, before_options: Optional[str] = None, options: Optional[str] = '-vn'):
        cmd = get_ytdlp_cmd() + [
            '--format', 'bestaudio/ba/b/best',
            '--no-playlist',
            '--quiet',
            '--no-warnings',
            '--remote-components', 'ejs:github',
            '--extractor-args', 'youtube:player_client=android,ios,mweb,web',
        ]
        cookie_file = find_cookie_file()
        if cookie_file:
            cmd.extend(['--cookies', str(cookie_file)])
        else:
            logger.warning("No cookies.txt found! Using mobile clients to bypass YouTube bot detection.")
        try:
            from yt_dlp.networking.impersonate import ImpersonateTarget
            cmd.extend(['--impersonate', 'chrome'])
        except Exception:
            pass
            
        if seek_seconds > 0:
            cmd.extend(['--download-sections', f'*{seek_seconds}-inf'])
            
        target = url if (url.startswith('http://') or url.startswith('https://')) else f"ytsearch1:{url}"
        cmd.extend(['-o', '-', target])
        
        self.ytdl_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL
        )
        super().__init__(self.ytdl_process.stdout, pipe=True, before_options=before_options, options=options)

    def cleanup(self):
        super().cleanup()
        if self.ytdl_process:
            try:
                self.ytdl_process.kill()
                self.ytdl_process.wait(timeout=1)
            except Exception:
                pass
            self.ytdl_process = None


class BufferedAudioSource(discord.AudioSource):
    """
    Wraps an AudioSource with a background worker thread and a thread-safe jitter buffer.
    Paces audio delivery and absorbs network delays/DASH fragment pauses, preventing 
    discord.py AudioPlayer from falling behind real-time (which causes sudden fast-forward catchup).
    """
    def __init__(self, original_source: discord.AudioSource, prebuffer_seconds: float = 2.0):
        self.original = original_source
        self.chunks_per_sec = 50  # 50 chunks of 3840 bytes = 1 sec of 48kHz 16-bit stereo PCM
        self.prebuffer_chunks = int(prebuffer_seconds * self.chunks_per_sec)
        
        # Buffer up to 10 seconds of decoded PCM audio (~1.9 MB in RAM)
        self.buffer = queue.Queue(maxsize=10 * self.chunks_per_sec)
        self.stopped = threading.Event()
        self.finished = threading.Event()
        self._in_underflow = False
        self._underflow_count = 0
        
        self.reader_thread = threading.Thread(target=self._reader_worker, daemon=True)
        self.reader_thread.start()
        logger.debug(f"BufferedAudioSource worker thread started (target pre-buffer: {self.prebuffer_chunks} chunks)")

    def _reader_worker(self):
        while not self.stopped.is_set():
            try:
                data = self.original.read()
                if not data:
                    self.finished.set()
                    break
                while not self.stopped.is_set():
                    try:
                        self.buffer.put(data, timeout=0.1)
                        break
                    except queue.Full:
                        continue
            except Exception as e:
                logger.error(f"Error in buffered reader: {e}")
                self.finished.set()
                break

    def read(self) -> bytes:
        if self.stopped.is_set():
            return b''
        try:
            chunk = self.buffer.get(timeout=0.05 if not self.finished.is_set() else 0.01)
            if self._in_underflow:
                logger.debug(f"Audio buffer recovered after {self._underflow_count} silence frames")
                self._in_underflow = False
                self._underflow_count = 0
            return chunk
        except queue.Empty:
            if self.finished.is_set():
                return b''
            # Underflow fallback: send silence frame instead of blocking to preserve audio clock timing
            if not self._in_underflow:
                self._in_underflow = True
                self._underflow_count = 1
                logger.debug("Audio buffer waiting for stream data (injecting silence frame)")
            else:
                self._underflow_count += 1
            return b'\x00' * 3840

    def cleanup(self):
        self.stopped.set()
        if hasattr(self.original, 'cleanup'):
            self.original.cleanup()


class PlayerState(Enum):
    """The current playback state of a GuildPlayer."""
    IDLE = auto()
    PLAYING = auto()
    PAUSED = auto()
    STOPPED = auto()
    ERROR = auto()

class GuildPlayer:
    """Central audio player for a specific Discord guild."""
    
    def __init__(self, bot: discord.Client, guild_id: int):
        self.bot = bot
        self.guild_id = guild_id
        self.queue = PlaybackQueue()
        self.voice_manager = VoiceManager(bot)
        self.volume: float = 1.0
        self.history: collections.deque = collections.deque(maxlen=100)
        self.state: PlayerState = PlayerState.IDLE
        self._play_lock = asyncio.Lock()
        self._play_generation: int = 0  # Monotonic counter to ignore stale callbacks

    @property
    def guild_str(self) -> str:
        """Returns human-readable guild name and ID for logging."""
        guild = self.bot.get_guild(self.guild_id)
        if guild and guild.name:
            return f"'{guild.name}' (ID: {self.guild_id})"
        return f"guild {self.guild_id}"
        
    async def _extract_youtube_url(self, url_or_query: str) -> Dict[str, Any]:
        """Uses yt-dlp (and YouTube Data API when available) to resolve media metadata rapidly."""
        logger.info(f"Resolving YouTube media: '{url_or_query}' in {self.guild_str}")

        # 1. Instant resolution via official YouTube Data API if configured (< 200ms)
        if getattr(self.bot, 'youtube_service', None) and getattr(self.bot.youtube_service, 'enabled', False):
            yt_id_match = re.search(r'(?:v=|\/|youtu\.be\/)([0-9A-Za-z_-]{11})', url_or_query)
            if yt_id_match:
                video_id = yt_id_match.group(1)
                try:
                    video = await self.bot.youtube_service.get_video(video_id)
                    if video:
                        info = {
                            'title': video.title,
                            'uploader': video.channel_title,
                            'duration': video.duration_seconds,
                            'webpage_url': f"https://www.youtube.com/watch?v={video.id}",
                            'thumbnail': video.thumbnail_url,
                            'id': video.id,
                        }
                        logger.info(f"Resolved YouTube via Data API: '{info.get('title')}' (Duration: {info.get('duration')}s)")
                        return info
                except Exception as e:
                    logger.debug(f"YouTube Data API resolution skipped ({e}), falling back to yt-dlp...")

        # 2. Fast yt-dlp extraction
        cookie_file = find_cookie_file()
        is_verbose = bool(getattr(getattr(self.bot, 'config', None), 'log_ytdlp_verbose', False))

        ydl_options = {
            'format': 'bestaudio/ba/b/best',
            'noplaylist': True,
            'skip_download': True,
            'extract_flat': 'in_playlist',
            'quiet': not is_verbose,
            'verbose': is_verbose,
            'no_warnings': not is_verbose,
            'default_search': 'ytsearch',
            'source_address': '0.0.0.0',
            'remote_components': ['ejs:github'],
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'ios', 'mweb', 'web']
                }
            }
        }

        if cookie_file:
            ydl_options['cookiefile'] = str(cookie_file)

        try:
            from yt_dlp.networking.impersonate import ImpersonateTarget
            ydl_options['impersonate'] = ImpersonateTarget.from_str('chrome')
        except Exception:
            pass
        
        target = url_or_query if (url_or_query.startswith('http://') or url_or_query.startswith('https://')) else f"ytsearch1:{url_or_query}"

        def extract():
            opts = dict(ydl_options)
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(target, download=False)
                    if info and 'entries' in info:
                        info = info['entries'][0]
                    return info
            except Exception as e:
                # If extraction failed and we used cookies, the cookies may be expired or flagged by YouTube.
                # Automatically retry without cookies using the android/ios clients.
                if 'cookiefile' in opts:
                    logger.warning(f"YouTube extraction with cookies failed ({e}). Retrying without cookies using mobile client...")
                    opts.pop('cookiefile', None)
                    opts['extractor_args'] = {
                        'youtube': {
                            'player_client': ['android', 'ios', 'mweb']
                        }
                    }
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        info = ydl.extract_info(target, download=False)
                        if info and 'entries' in info:
                            info = info['entries'][0]
                        return info
                raise

        info = await asyncio.to_thread(extract)
        if info:
            logger.info(f"Resolved YouTube: '{info.get('title')}' (Duration: {info.get('duration')}s)")
        return info

    async def play_track(self, track: AudioTrack, seek_seconds: float = 0):
        """Plays a specific audio track in the guild's voice channel."""
        async with self._play_lock:
            # Increment generation so any in-flight callback from a previous
            # track will see a stale generation and bail out.
            self._play_generation += 1
            current_gen = self._play_generation

            guild = self.bot.get_guild(self.guild_id)
            if not guild:
                self.state = PlayerState.ERROR
                return
                
            vc = guild.voice_client
            if not vc or not vc.is_connected():
                self.state = PlayerState.ERROR
                return

            if vc.is_playing() or vc.is_paused():
                vc.stop()

            try:
                ffmpeg_options = '-vn'
                before_options = ''
                
                if seek_seconds > 0:
                    before_options += f'-ss {seek_seconds} '

                if track.source_type == SourceType.LOCAL_FILE:
                    source_uri = track.source_uri
                    audio_source = discord.FFmpegPCMAudio(
                        source_uri, 
                        before_options=before_options.strip() or None, 
                        options=ffmpeg_options
                    )
                elif track.source_type == SourceType.YOUTUBE:
                    # Pipe yt-dlp into FFmpeg with fast probing and wrap in jitter buffer
                    # to eliminate network stutter, buffer starvation, and fast-forward catchup
                    pipe_before = f"-probesize 32k -analyzeduration 0 {before_options}".strip() or None
                    raw_source = YTDLPPipeAudio(
                        track.source_uri,
                        seek_seconds=seek_seconds,
                        before_options=pipe_before,
                        options=ffmpeg_options
                    )
                    audio_source = BufferedAudioSource(raw_source, prebuffer_seconds=2.0)
                else:
                    raise ValueError(f"Unknown source type: {track.source_type}")
                
                volume_transformer = discord.PCMVolumeTransformer(audio_source, volume=self.volume)

                # Create a generation-scoped callback.  When play_track() is
                # called again (skip, previous, seek, etc.) the generation
                # increments and this closure's captured `current_gen` will no
                # longer match → the callback returns immediately instead of
                # cascading through _advance_queue.
                def after_callback(error, *, _gen=current_gen):
                    if _gen != self._play_generation:
                        logger.debug(f"Ignoring stale playback callback (gen {_gen} vs current {self._play_generation})")
                        return
                    self._playback_finished(error)

                vc.play(volume_transformer, after=after_callback)
                self.state = PlayerState.PLAYING
                logger.info(f"Now playing: '{track.title}' [{track.source_type.name}] in {self.guild_str}")

                # Update bot presence to show currently playing track
                pm = getattr(self.bot, 'presence_manager', None)
                if pm:
                    await pm.set_playing(track.title, track.artist, track.playlist_name)
                
            except Exception as e:
                logger.error(f"Error playing track {track.title}: {e}")
                self.state = PlayerState.ERROR
                asyncio.run_coroutine_threadsafe(self._advance_queue(), self.bot.loop)

    def _playback_finished(self, error: Optional[Exception]):
        """Callback invoked by discord.py when playback finishes naturally."""
        if error:
            logger.error(f"Playback error: {error}")
            
        if self.state in (PlayerState.STOPPED, PlayerState.IDLE):
            return
            
        asyncio.run_coroutine_threadsafe(self._advance_queue(), self.bot.loop)

    async def _advance_queue(self):
        """Advances the queue and plays the next track."""
        current = await self.queue.current()
        if current:
            self.history.append(current)
            
        next_track = await self.queue.advance()
        if next_track:
            logger.info(f"Advancing to next track: '{next_track.title}' in {self.guild_str}")
            await self.play_track(next_track)
        else:
            logger.info(f"Queue reached end, entering IDLE state in {self.guild_str}")
            self.state = PlayerState.IDLE
            # Revert bot presence to idle status
            pm = getattr(self.bot, 'presence_manager', None)
            if pm:
                await pm.set_idle()

    async def play(self, track: AudioTrack):
        """Adds a track to the queue and starts playing if idle."""
        await self.queue.add(track)
        if self.state in (PlayerState.IDLE, PlayerState.STOPPED, PlayerState.ERROR):
            next_track = await self.queue.current()
            if next_track:
                await self.play_track(next_track)

    async def pause(self):
        """Pauses the current playback."""
        guild = self.bot.get_guild(self.guild_id)
        if guild and guild.voice_client and guild.voice_client.is_playing():
            guild.voice_client.pause()
            self.state = PlayerState.PAUSED
            logger.info(f"Playback paused in {self.guild_str}")
            pm = getattr(self.bot, 'presence_manager', None)
            if pm:
                await pm.set_paused()

    async def resume(self):
        """Resumes the paused playback."""
        guild = self.bot.get_guild(self.guild_id)
        if guild and guild.voice_client and guild.voice_client.is_paused():
            guild.voice_client.resume()
            self.state = PlayerState.PLAYING
            logger.info(f"Playback resumed in {self.guild_str}")
            # Restore playing presence with current track
            current = await self.queue.current()
            pm = getattr(self.bot, 'presence_manager', None)
            if pm and current:
                await pm.set_playing(current.title, current.artist, current.playlist_name)

    async def stop(self):
        """Stops playback and clears the queue."""
        self.state = PlayerState.STOPPED
        guild = self.bot.get_guild(self.guild_id)
        if guild and guild.voice_client:
            guild.voice_client.stop()
        await self.queue.clear()
        logger.info(f"Playback stopped and queue cleared in {self.guild_str}")
        pm = getattr(self.bot, 'presence_manager', None)
        if pm:
            await pm.set_idle()

    async def skip(self):
        """Skips the currently playing track."""
        guild = self.bot.get_guild(self.guild_id)
        logger.info(f"Skip requested in {self.guild_str}")
        if guild and guild.voice_client:
            if guild.voice_client.is_playing() or guild.voice_client.is_paused():
                guild.voice_client.stop() # triggers _playback_finished
            else:
                await self._advance_queue()

    async def previous(self):
        """Plays the previous track in the queue."""
        prev_track = await self.queue.go_back()
        if prev_track:
            logger.info(f"Returning to previous track: '{prev_track.title}' in {self.guild_str}")
            await self.play_track(prev_track)

    async def seek(self, seconds: float):
        """Seeks to a specific position in the current track."""
        current = await self.queue.current()
        if current:
            logger.info(f"Seeking to {seconds}s in track '{current.title}' ({self.guild_str})")
            await self.play_track(current, seek_seconds=seconds)

    async def set_volume(self, vol: float):
        """Sets the volume of the player."""
        self.volume = max(0.0, min(2.0, vol))
        guild = self.bot.get_guild(self.guild_id)
        if guild and guild.voice_client and guild.voice_client.source:
            if isinstance(guild.voice_client.source, discord.PCMVolumeTransformer):
                guild.voice_client.source.volume = self.volume
        logger.info(f"Volume changed to {int(self.volume * 100)}% in {self.guild_str}")

    async def set_loop(self, mode: LoopMode):
        """Sets the loop mode."""
        self.queue.loop_mode = mode
        logger.info(f"Loop mode changed to {mode.name} in {self.guild_str}")

    async def play_youtube(self, query: str, requester_id: int, requester_name: str) -> AudioTrack:
        """Searches or extracts a YouTube video and adds it to the queue."""
        info = await self._extract_youtube_url(query)
        
        track = AudioTrack(
            title=info.get('title', 'Unknown Title'),
            artist=info.get('uploader'),
            duration=float(info.get('duration', 0)) if info.get('duration') else None,
            source_type=SourceType.YOUTUBE,
            source_uri=info.get('webpage_url', query),
            stream_url=info.get('url'),
            requester_id=requester_id,
            requester_name=requester_name,
            thumbnail_url=info.get('thumbnail')
        )
        
        await self.play(track)
        return track

    async def play_youtube_playlist(self, url: str, requester_id: int, requester_name: str) -> List[AudioTrack]:
        """Extracts a YouTube playlist and adds its tracks to the queue."""
        logger.info(f"Extracting YouTube playlist: '{url}' in {self.guild_str}")
        cookie_file = find_cookie_file()
        is_verbose = bool(getattr(getattr(self.bot, 'config', None), 'log_ytdlp_verbose', False))

        ydl_options = {
            'extract_flat': True,
            'quiet': not is_verbose,
            'verbose': is_verbose,
            'no_warnings': not is_verbose,
            'remote_components': ['ejs:github'],
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'ios', 'mweb', 'web']
                }
            }
        }

        if cookie_file:
            ydl_options['cookiefile'] = str(cookie_file)

        try:
            from yt_dlp.networking.impersonate import ImpersonateTarget
            ydl_options['impersonate'] = ImpersonateTarget.from_str('chrome')
        except Exception:
            pass
        
        def extract():
            opts = dict(ydl_options)
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    return ydl.extract_info(url, download=False)
            except Exception as e:
                if 'cookiefile' in opts:
                    logger.warning(f"YouTube playlist extraction with cookies failed ({e}). Retrying without cookies using mobile client...")
                    opts.pop('cookiefile', None)
                    opts['extractor_args'] = {
                        'youtube': {
                            'player_client': ['android', 'ios', 'mweb']
                        }
                    }
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        return ydl.extract_info(url, download=False)
                raise

        info = await asyncio.to_thread(extract)
        tracks = []
        
        if info and 'entries' in info:
            playlist_title = info.get('title')
            for entry in info['entries']:
                if entry:
                    track = AudioTrack(
                        title=entry.get('title', 'Unknown Title'),
                        artist=entry.get('uploader'),
                        duration=float(entry.get('duration', 0)) if entry.get('duration') else None,
                        source_type=SourceType.YOUTUBE,
                        source_uri=entry.get('url', entry.get('webpage_url', '')),
                        requester_id=requester_id,
                        requester_name=requester_name,
                        playlist_name=playlist_title
                    )
                    tracks.append(track)
                    
            await self.queue.add_many(tracks)
            
            if self.state in (PlayerState.IDLE, PlayerState.STOPPED, PlayerState.ERROR):
                current = await self.queue.current()
                if current:
                    await self.play_track(current)

        logger.info(f"Loaded {len(tracks)} tracks from playlist '{info.get('title') if info else url}' into queue ({self.guild_str})")
        return tracks

    async def destroy(self):
        """Cleans up player resources and disconnects."""
        await self.stop()
        guild = self.bot.get_guild(self.guild_id)
        if guild:
            await self.voice_manager.disconnect(guild)
        pm = getattr(self.bot, 'presence_manager', None)
        if pm:
            await pm.set_idle()
