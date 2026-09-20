"""
Discord slash command cog for YouTube search and metadata inspection.
"""

import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from bot.youtube.models import YouTubeSearchResult, YouTubeVideo, YouTubePlaylistInfo, duration_display
from bot.discord.permissions import check_command_channel

logger = logging.getLogger(__name__)


def is_in_command_channel():
    """Predicate to check if command is in the designated channel."""
    async def predicate(interaction: discord.Interaction) -> bool:
        bot = interaction.client
        channel_id = getattr(bot.config, 'command_channel_id', None)
        return check_command_channel(interaction, channel_id)
    return app_commands.check(predicate)


class YouTubeCog(commands.GroupCog, group_name="youtube", group_description="YouTube commands"):
    """Cog for YouTube metadata search, video inspection, and playlist inspection."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @property
    def service(self):
        return getattr(self.bot, "youtube_service", None)

    async def _check_service(self, interaction: discord.Interaction) -> bool:
        """Verifies that the YouTube service is configured and active."""
        if not self.service or not self.service.enabled:
            embed = discord.Embed(
                title="YouTube API Disabled",
                description=(
                    "YouTube Data API metadata features are currently disabled.\n"
                    "Playback of YouTube URLs is still supported via `/play <url>`!"
                ),
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return False
        return True

    @app_commands.command(name="search", description="Search YouTube for videos (metadata only)")
    @app_commands.describe(query="The search term")
    @is_in_command_channel()
    async def search(self, interaction: discord.Interaction, query: str):
        """Search YouTube and display top results."""
        if not await self._check_service(interaction):
            return

        await interaction.response.defer()

        try:
            results = await self.service.search(query, max_results=5)
            if not results:
                return await interaction.followup.send("No results found.")

            embed = discord.Embed(
                title=f"🔍 YouTube Search: {query}",
                color=discord.Color.red()
            )

            for i, res in enumerate(results, 1):
                embed.add_field(
                    name=f"{i}. {res.title}",
                    value=f"📺 Channel: {res.channel_title}\n🔗 [Watch on YouTube]({res.url})",
                    inline=False
                )

            embed.set_footer(text="Use /play <url or search query> to play any track.")
            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.error(f"YouTube search error: {e}")
            await interaction.followup.send(f"An error occurred during search: {e}", ephemeral=True)

    @app_commands.command(name="video", description="Show detailed YouTube video metadata")
    @app_commands.describe(url="The YouTube video URL or ID")
    @is_in_command_channel()
    async def video(self, interaction: discord.Interaction, url: str):
        """Displays metadata for a specific YouTube video."""
        if not await self._check_service(interaction):
            return

        await interaction.response.defer()

        video_id = self.service.extract_video_id(url)
        if not video_id:
            return await interaction.followup.send("Could not parse YouTube video ID from the provided URL.")

        try:
            info: Optional[YouTubeVideo] = await self.service.get_video(video_id)
            if not info:
                return await interaction.followup.send("Could not retrieve video information.")

            dur_str = duration_display(info.duration_seconds)
            embed = discord.Embed(
                title=f"🎬 {info.title}",
                url=info.url,
                color=discord.Color.red()
            )
            embed.add_field(name="Channel", value=info.channel_title, inline=True)
            embed.add_field(name="Duration", value=dur_str, inline=True)
            if info.view_count is not None:
                embed.add_field(name="Views", value=f"{info.view_count:,}", inline=True)

            if info.thumbnail_url:
                embed.set_thumbnail(url=info.thumbnail_url)

            embed.set_footer(text="To play this track, use /play <url>")
            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.error(f"YouTube video error: {e}")
            await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)

    @app_commands.command(name="playlist", description="Show YouTube playlist information")
    @app_commands.describe(url="The YouTube playlist URL or ID")
    @is_in_command_channel()
    async def playlist(self, interaction: discord.Interaction, url: str):
        """Displays metadata and track overview for a YouTube playlist."""
        if not await self._check_service(interaction):
            return

        await interaction.response.defer()

        playlist_id = self.service.extract_playlist_id(url)
        if not playlist_id:
            return await interaction.followup.send("Could not parse YouTube playlist ID from the provided URL.")

        try:
            info: Optional[YouTubePlaylistInfo] = await self.service.get_playlist(playlist_id)
            if not info:
                return await interaction.followup.send("Could not retrieve playlist information.")

            embed = discord.Embed(
                title=f"📑 {info.title}",
                url=info.url,
                color=discord.Color.red()
            )
            embed.add_field(name="Channel", value=info.channel_title, inline=True)
            embed.add_field(name="Total Videos", value=str(info.item_count), inline=True)

            items = await self.service.get_playlist_items(playlist_id, max_results=5)
            if items:
                desc = "**First few items:**\n"
                for i, item in enumerate(items, 1):
                    desc += f"{i}. {item.title}\n"
                embed.description = desc

            if info.thumbnail_url:
                embed.set_thumbnail(url=info.thumbnail_url)

            embed.set_footer(text="To play this playlist, use /play <playlist_url>")
            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.error(f"YouTube playlist error: {e}")
            await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(YouTubeCog(bot))
