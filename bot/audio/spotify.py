"""
Spotify metadata resolver for Discord Music Bot.
Resolves Spotify track, album, and playlist links into searchable metadata
without requiring Spotify API credentials or developer accounts.
"""
import re
import html
import json
import logging
import urllib.parse
from typing import List, Dict, Any, Optional
import aiohttp

logger = logging.getLogger(__name__)

SPOTIFY_URL_REGEX = re.compile(
    r'https?://(?:open\.)?spotify\.com/(?:intl-[a-z]{2}/)?(track|playlist|album)/([a-zA-Z0-9]+)',
    re.IGNORECASE
)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (compatible; Discordbot/2.0; +https://discordapp.com)',
    'Accept-Language': 'en-US,en;q=0.9',
}


def is_spotify_url(url: str) -> bool:
    """Checks whether a string is a Spotify URL."""
    if not url:
        return False
    return bool(SPOTIFY_URL_REGEX.search(url.strip()))


class SpotifyResolver:
    """Resolves Spotify URLs to titles and artists for YouTube matching."""

    @staticmethod
    async def resolve(url: str) -> List[Dict[str, str]]:
        """
        Resolves a Spotify URL.
        Returns a list of dicts: [{'title': str, 'artist': str, 'query': str}]
        """
        match = SPOTIFY_URL_REGEX.search(url.strip())
        if not match:
            return []

        entity_type, entity_id = match.group(1).lower(), match.group(2)
        logger.info(f"Resolving Spotify {entity_type}: {entity_id}")

        async with aiohttp.ClientSession(headers=HEADERS) as session:
            if entity_type == 'track':
                return await SpotifyResolver._resolve_track(session, entity_id)
            elif entity_type in ('playlist', 'album'):
                return await SpotifyResolver._resolve_collection(session, entity_type, entity_id)

        return []

    @staticmethod
    async def _resolve_track(session: aiohttp.ClientSession, track_id: str) -> List[Dict[str, str]]:
        """Resolves a single Spotify track using oEmbed + OpenGraph fallback."""
        oembed_url = f"https://open.spotify.com/oembed?url=https://open.spotify.com/track/{track_id}"
        title = ""
        artist = ""

        try:
            async with session.get(oembed_url, timeout=aiohttp.ClientTimeout(total=6)) as res:
                if res.status == 200:
                    data = await res.json()
                    title = data.get("title", "").strip()
        except Exception as e:
            logger.debug(f"Spotify oEmbed fetch failed: {e}")

        # Fallback / enrich with OpenGraph tags
        track_url = f"https://open.spotify.com/track/{track_id}"
        try:
            async with session.get(track_url, timeout=aiohttp.ClientTimeout(total=6)) as res:
                if res.status == 200:
                    html = await res.text()
                    if not title:
                        t_match = re.search(r'<meta property="og:title" content="([^"]+)"', html)
                        if t_match:
                            title = t_match.group(1).strip()
                    desc_match = re.search(r'<meta property="og:description" content="([^"]+)"', html)
                    if desc_match:
                        # og:description format is typically "Artist · Album · Song · Year" or "Artist, Song, Album"
                        raw_desc = desc_match.group(1)
                        # Split by middle dot or bullet or comma
                        parts = [p.strip() for p in re.split(r'[\xb7\u00b7\u2022·|]', raw_desc) if p.strip()]
                        if parts:
                            artist = parts[0]
        except Exception as e:
            logger.debug(f"Spotify OpenGraph fetch failed: {e}")

        if not title:
            return []

        query = f"{title} {artist}".strip()
        return [{"title": title, "artist": artist, "query": query}]

    @staticmethod
    async def _resolve_collection(session: aiohttp.ClientSession, entity_type: str, entity_id: str) -> List[Dict[str, str]]:
        """Resolves tracks from a Spotify playlist or album via public embed view."""
        embed_url = f"https://open.spotify.com/embed/{entity_type}/{entity_id}"
        tracks: List[Dict[str, str]] = []

        try:
            async with session.get(embed_url, timeout=aiohttp.ClientTimeout(total=8)) as res:
                if res.status == 200:
                    raw_html = await res.text()
                    pattern = re.compile(r'"title"\s*:\s*"([^"]+)"\s*,\s*"subtitle"\s*:\s*"([^"]+)"')
                    matches = pattern.findall(raw_html)
                    
                    seen = set()
                    for idx, (t, a) in enumerate(matches):
                        # Clean unicode and HTML escapes
                        t_clean = html.unescape(t.encode('utf-8').decode('unicode_escape', errors='ignore')).strip()
                        a_clean = html.unescape(a.encode('utf-8').decode('unicode_escape', errors='ignore')).strip()
                        
                        # First match is often the playlist metadata itself ("Today's Top Hits", "Spotify")
                        if idx == 0 and a_clean.lower() == 'spotify':
                            continue
                            
                        key = (t_clean.lower(), a_clean.lower())
                        if key in seen or not t_clean:
                            continue
                        seen.add(key)
                        
                        query = f"{t_clean} {a_clean}".strip()
                        tracks.append({
                            "title": t_clean,
                            "artist": a_clean,
                            "query": query
                        })
        except Exception as e:
            logger.error(f"Error resolving Spotify {entity_type}: {e}")

        return tracks
