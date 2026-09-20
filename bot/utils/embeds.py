"""
Embed factory for building standardized Discord UI embeds.
"""

import discord
from bot.audio.source import AudioTrack


class EmbedFactory:
    """Factory for creating consistent Discord Embeds."""

    @staticmethod
    def track_info(track: AudioTrack, title: str = "Track Info") -> discord.Embed:
        """Constructs an embed displaying track metadata."""
        embed = discord.Embed(
            title=title,
            description=f"**{track.display_title()}**",
            color=discord.Color.blue()
        )
        if track.artist:
            embed.add_field(name="Artist", value=track.artist, inline=True)
        if track.album:
            embed.add_field(name="Album", value=track.album, inline=True)
        embed.add_field(name="Duration", value=track.duration_str(), inline=True)
        embed.add_field(name="Requested By", value=track.requester_name or "Unknown", inline=True)
        if track.playlist_name:
            embed.add_field(name="Playlist", value=track.playlist_name, inline=True)
        if track.thumbnail_url:
            embed.set_thumbnail(url=track.thumbnail_url)
        return embed

    @staticmethod
    def now_playing(track: AudioTrack) -> discord.Embed:
        """Constructs a 'Now Playing' embed."""
        return EmbedFactory.track_info(track, title="▶️ Now Playing")

    @staticmethod
    def track_added(track: AudioTrack) -> discord.Embed:
        """Constructs an 'Added to Queue' embed."""
        return EmbedFactory.track_info(track, title="✅ Added to Queue")
