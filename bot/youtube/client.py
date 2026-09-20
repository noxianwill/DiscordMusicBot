"""
Client for communicating with the YouTube Data API.
"""

import asyncio
import logging
import re
from typing import Optional, Any
from datetime import datetime

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials

from .models import YouTubeVideo, YouTubePlaylistInfo, YouTubeSearchResult

logger = logging.getLogger(__name__)


class YouTubeClient:
    """Client for making requests to the YouTube Data API."""

    def __init__(self, credentials: Credentials):
        """
        Initialize the YouTube client.

        Args:
            credentials: Authenticated Google Credentials.
        """
        self.credentials = credentials
        # Build the service object. We use asyncio.to_thread in methods where API calls are made.
        self.service = build('youtube', 'v3', credentials=self.credentials, cache_discovery=False)
        self._cache: dict[str, dict[str, Any]] = {}
        self._cache_ttl = 3600  # 1 hour cache

    def _parse_duration(self, iso_duration: str) -> int:
        """
        Parse ISO 8601 duration string (e.g. PT3M45S) into seconds.
        """
        pattern = re.compile(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?')
        match = pattern.match(iso_duration)
        if not match:
            return 0
        
        hours = int(match.group(1)) if match.group(1) else 0
        minutes = int(match.group(2)) if match.group(2) else 0
        seconds = int(match.group(3)) if match.group(3) else 0
        
        return hours * 3600 + minutes * 60 + seconds

    def _clean_cache(self) -> None:
        """Remove expired entries from the cache."""
        now = datetime.now().timestamp()
        expired_keys = [k for k, v in self._cache.items() if now > v['expires_at']]
        for k in expired_keys:
            del self._cache[k]

    def _get_from_cache(self, key: str) -> Optional[Any]:
        self._clean_cache()
        entry = self._cache.get(key)
        return entry['data'] if entry else None

    def _set_in_cache(self, key: str, data: Any) -> None:
        self._cache[key] = {
            'data': data,
            'expires_at': datetime.now().timestamp() + self._cache_ttl
        }

    async def search(self, query: str, max_results: int = 5) -> list[YouTubeSearchResult]:
        """
        Search for YouTube videos.

        Args:
            query: The search term.
            max_results: Maximum number of results to return.

        Returns:
            List of YouTubeSearchResult objects.
        """
        cache_key = f"search:{query}:{max_results}"
        cached = self._get_from_cache(cache_key)
        if cached is not None:
            return cached

        def _do_search():
            request = self.service.search().list(
                part="snippet",
                q=query,
                type="video",
                maxResults=max_results
            )
            return request.execute()

        try:
            response = await asyncio.to_thread(_do_search)
            results = []
            for item in response.get('items', []):
                snippet = item['snippet']
                video_id = item['id']['videoId']
                results.append(YouTubeSearchResult(
                    video_id=video_id,
                    title=snippet['title'],
                    channel_title=snippet['channelTitle'],
                    url=f"https://www.youtube.com/watch?v={video_id}",
                    thumbnail_url=snippet['thumbnails']['high']['url']
                ))
            
            self._set_in_cache(cache_key, results)
            return results
        except HttpError as e:
            logger.error(f"YouTube API search error: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error in YouTube search: {e}")
            return []

    async def get_video(self, video_id: str) -> Optional[YouTubeVideo]:
        """
        Get metadata for a specific YouTube video.

        Args:
            video_id: The YouTube video ID.

        Returns:
            YouTubeVideo object or None if not found/error.
        """
        cache_key = f"video:{video_id}"
        cached = self._get_from_cache(cache_key)
        if cached is not None:
            return cached

        def _do_get_video():
            request = self.service.videos().list(
                part="snippet,contentDetails,statistics",
                id=video_id
            )
            return request.execute()

        try:
            response = await asyncio.to_thread(_do_get_video)
            items = response.get('items', [])
            if not items:
                return None
            
            item = items[0]
            snippet = item['snippet']
            content_details = item['contentDetails']
            statistics = item.get('statistics', {})
            
            video = YouTubeVideo(
                video_id=video_id,
                title=snippet['title'],
                channel_title=snippet['channelTitle'],
                duration_seconds=self._parse_duration(content_details['duration']),
                url=f"https://www.youtube.com/watch?v={video_id}",
                thumbnail_url=snippet['thumbnails'].get('high', {}).get('url', ''),
                view_count=int(statistics['viewCount']) if 'viewCount' in statistics else None,
                published_at=snippet['publishedAt']
            )
            self._set_in_cache(cache_key, video)
            return video
        except HttpError as e:
            logger.error(f"YouTube API get_video error: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in get_video: {e}")
            return None

    async def get_playlist_info(self, playlist_id: str) -> Optional[YouTubePlaylistInfo]:
        """
        Get metadata for a YouTube playlist.

        Args:
            playlist_id: The YouTube playlist ID.

        Returns:
            YouTubePlaylistInfo object or None if not found/error.
        """
        cache_key = f"playlist_info:{playlist_id}"
        cached = self._get_from_cache(cache_key)
        if cached is not None:
            return cached

        def _do_get_playlist():
            request = self.service.playlists().list(
                part="snippet,contentDetails",
                id=playlist_id
            )
            return request.execute()

        try:
            response = await asyncio.to_thread(_do_get_playlist)
            items = response.get('items', [])
            if not items:
                return None
            
            item = items[0]
            snippet = item['snippet']
            content_details = item['contentDetails']
            
            info = YouTubePlaylistInfo(
                playlist_id=playlist_id,
                title=snippet['title'],
                channel_title=snippet['channelTitle'],
                item_count=int(content_details['itemCount']),
                url=f"https://www.youtube.com/playlist?list={playlist_id}",
                thumbnail_url=snippet['thumbnails'].get('high', {}).get('url', '')
            )
            self._set_in_cache(cache_key, info)
            return info
        except HttpError as e:
            logger.error(f"YouTube API get_playlist_info error: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in get_playlist_info: {e}")
            return None

    async def get_playlist_items(self, playlist_id: str, limit: int = 50) -> list[YouTubeVideo]:
        """
        Get items from a YouTube playlist.

        Args:
            playlist_id: The YouTube playlist ID.
            limit: Maximum number of items to fetch.

        Returns:
            List of YouTubeVideo objects representing the playlist tracks.
        """
        cache_key = f"playlist_items:{playlist_id}:{limit}"
        cached = self._get_from_cache(cache_key)
        if cached is not None:
            return cached

        def _do_get_playlist_items():
            # Get playlist items (video IDs)
            request = self.service.playlistItems().list(
                part="contentDetails",
                playlistId=playlist_id,
                maxResults=min(limit, 50)
            )
            return request.execute()

        try:
            response = await asyncio.to_thread(_do_get_playlist_items)
            video_ids = [item['contentDetails']['videoId'] for item in response.get('items', [])]
            
            if not video_ids:
                return []
                
            # Now fetch the video details for these IDs
            def _do_get_videos():
                request = self.service.videos().list(
                    part="snippet,contentDetails,statistics",
                    id=",".join(video_ids)
                )
                return request.execute()
                
            video_response = await asyncio.to_thread(_do_get_videos)
            
            results = []
            for item in video_response.get('items', []):
                snippet = item['snippet']
                content_details = item['contentDetails']
                statistics = item.get('statistics', {})
                v_id = item['id']
                
                results.append(YouTubeVideo(
                    video_id=v_id,
                    title=snippet['title'],
                    channel_title=snippet['channelTitle'],
                    duration_seconds=self._parse_duration(content_details['duration']),
                    url=f"https://www.youtube.com/watch?v={v_id}",
                    thumbnail_url=snippet['thumbnails'].get('high', {}).get('url', ''),
                    view_count=int(statistics['viewCount']) if 'viewCount' in statistics else None,
                    published_at=snippet['publishedAt']
                ))
                
            self._set_in_cache(cache_key, results)
            return results
        except HttpError as e:
            logger.error(f"YouTube API get_playlist_items error: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error in get_playlist_items: {e}")
            return []
