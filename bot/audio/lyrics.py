"""
Lyrics fetcher and synchronizer for Discord Music Bot.
Fetches plain and real-time synchronized (LRC) lyrics from LrcLib.
"""
import re
import logging
import urllib.parse
from typing import List, Dict, Any, Optional
import aiohttp

logger = logging.getLogger(__name__)

LRCLIB_GET_URL = "https://lrclib.net/api/get"
LRCLIB_SEARCH_URL = "https://lrclib.net/api/search"

def clean_song_title(title: str, artist: Optional[str] = None) -> tuple[str, Optional[str]]:
    """Removes common YouTube video noise like (Official Video), [Lyrics], etc."""
    if not title:
        return "", artist
    cleaned = title
    # Remove bracketed/parenthesized tags like (Official HD Video), [Remastered], (Lyrics), etc.
    cleaned = re.sub(
        r'[\(\[][^\)\]]*(?:official|video|audio|lyrics?|remaster|hd|4k|visualizer|clip|version)[^\)\]]*[\)\]]',
        '',
        cleaned,
        flags=re.IGNORECASE
    )
    cleaned = re.sub(r'\|.*$', '', cleaned)
    cleaned = cleaned.strip(' -|[]()')

    extracted_artist = artist
    if ' - ' in cleaned:
        parts = cleaned.split(' - ', 1)
        if artist and (artist.lower() in parts[0].lower() or parts[0].lower() in artist.lower()):
            extracted_artist = artist
            cleaned = parts[1].strip()
        elif not artist:
            extracted_artist = parts[0].strip()
            cleaned = parts[1].strip()
        else:
            cleaned = parts[1].strip()

    return cleaned.strip(' -|[]()'), extracted_artist


def parse_lrc(lrc_text: str) -> List[Dict[str, Any]]:
    """
    Parses standard LRC synced lyrics into timestamped lines.
    Returns: [{'time': float_seconds, 'text': str}, ...]
    """
    if not lrc_text:
        return []

    lines = []
    # Match [mm:ss.xx] or [mm:ss]
    pattern = re.compile(r'\[(\d{1,2}):(\d{2}(?:\.\d{1,3})?)\](.*)')

    for raw_line in lrc_text.splitlines():
        match = pattern.match(raw_line.strip())
        if match:
            minutes = float(match.group(1))
            seconds = float(match.group(2))
            total_sec = round(minutes * 60 + seconds, 2)
            
            # Clean inner word-sync tags like <00:18.89> if present
            text = re.sub(r'<\d{1,2}:\d{2}(?:\.\d{1,3})?>', '', match.group(3)).strip()
            if text:
                lines.append({
                    "time": total_sec,
                    "text": text
                })

    lines.sort(key=lambda x: x["time"])
    return lines


class LyricsService:
    """Retrieves synchronized and plain lyrics."""

    @staticmethod
    async def get_lyrics(title: str, artist: Optional[str] = None, duration: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """
        Attempts to fetch lyrics for the given song.
        Returns dict with title, artist, plainLyrics, syncedLyrics, and lines.
        """
        cleaned_title, effective_artist = clean_song_title(title, artist)
        target_title = cleaned_title or title
        params = {"track_name": target_title}
        if effective_artist:
            params["artist_name"] = effective_artist
        if duration:
            params["duration"] = int(duration)

        headers = {
            "User-Agent": "DiscordMusicBot-LyricsFetcher/1.0",
            "Accept": "application/json"
        }

        async with aiohttp.ClientSession(headers=headers) as session:
            # 1. Try exact match
            try:
                async with session.get(LRCLIB_GET_URL, params=params, timeout=aiohttp.ClientTimeout(total=5)) as res:
                    if res.status == 200:
                        data = await res.json()
                        return LyricsService._format_result(data, target_title, effective_artist)
            except Exception as e:
                logger.debug(f"LrcLib exact get failed: {e}")

            # 2. Try search fallback
            search_query = f"{target_title} {effective_artist or ''}".strip()
            try:
                async with session.get(LRCLIB_SEARCH_URL, params={"q": search_query}, timeout=aiohttp.ClientTimeout(total=5)) as res:
                    if res.status == 200:
                        results = await res.json()
                        if results and isinstance(results, list):
                            # Pick best match (prefer one with synced lyrics)
                            best = results[0]
                            for r in results:
                                if r.get("syncedLyrics"):
                                    best = r
                                    break
                            return LyricsService._format_result(best, target_title, effective_artist)
            except Exception as e:
                logger.debug(f"LrcLib search failed: {e}")

        return None

    @staticmethod
    def _format_result(data: Dict[str, Any], fallback_title: str, fallback_artist: Optional[str]) -> Dict[str, Any]:
        plain = (data.get("plainLyrics") or "").strip()
        synced_raw = data.get("syncedLyrics") or ""
        parsed_lines = parse_lrc(synced_raw)

        return {
            "id": data.get("id"),
            "title": data.get("trackName") or data.get("name") or fallback_title,
            "artist": data.get("artistName") or fallback_artist or "Unknown Artist",
            "plainLyrics": plain,
            "syncedLyrics": parsed_lines,
            "hasSynced": bool(parsed_lines),
            "instrumental": bool(data.get("instrumental", False))
        }
