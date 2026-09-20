"""
General Discord commands: about, help, ping.
"""

import time
import logging
from typing import Optional

import discord
from discord.ext import commands
from discord import app_commands

from bot import __version__

logger = logging.getLogger(__name__)


class GeneralCog(commands.Cog):
    """General informational and utility bot commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.start_time = time.time()

    @app_commands.command(name="about", description="Show bot information, version, and uptime")
    async def about(self, interaction: discord.Interaction):
        """Show information about the bot."""
        uptime_seconds = int(time.time() - self.start_time)
        hours, remainder = divmod(uptime_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime_str = f"{hours}h {minutes}m {seconds}s"

        embed = discord.Embed(
            title="🎵 Discord Music Bot",
            description="A production-grade, self-hosted Discord music bot supporting local playlists and YouTube streaming.",
            color=discord.Color.blurple()
        )
        embed.add_field(name="Version", value=f"v{__version__}", inline=True)
        embed.add_field(name="Uptime", value=uptime_str, inline=True)
        embed.add_field(name="Servers Connected", value=str(len(self.bot.guilds)), inline=True)
        embed.set_footer(text=f"Requested by {interaction.user.display_name}")

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="help", description="Show an overview of available commands")
    async def help(self, interaction: discord.Interaction):
        """Show the help overview embed."""
        embed = discord.Embed(
            title="📖 Discord Music Bot - Command Overview",
            description="Use slash commands (`/`) to interact with the bot.",
            color=discord.Color.blue()
        )

        playback = (
            "`/play <query or url>` - Play a track or YouTube URL\n"
            "`/pause` & `/resume` - Pause/resume playback (DJ)\n"
            "`/skip` & `/previous` - Skip track or go back (DJ)\n"
            "`/stop` - Stop audio & clear queue (DJ)\n"
            "`/volume [0-200]` - View or change playback volume (DJ)\n"
            "`/seek <seconds>` - Jump to position in track (DJ)\n"
            "`/nowplaying` - Display currently playing track\n"
            "`/next` - Display the upcoming track\n"
            "`/history` - View recently played tracks"
        )
        queue = (
            "`/queue show [page]` - Display upcoming queue\n"
            "`/queue clear` - Clear queue (DJ)\n"
            "`/queue shuffle` - Randomize upcoming tracks (DJ)\n"
            "`/queue remove <index>` - Remove track from queue (DJ)\n"
            "`/queue move <from> <to>` - Reorder queue items (DJ)"
        )
        playlist = (
            "`/playlist list` - List available local playlists\n"
            "`/playlist play <name>` - Load & play a playlist\n"
            "`/playlist reload` - Rescan playlist folder from disk"
        )
        youtube = (
            "`/youtube search <query>` - Search YouTube metadata\n"
            "`/youtube video <url>` - Inspect video metadata\n"
            "`/youtube playlist <url>` - Inspect playlist metadata"
        )

        embed.add_field(name="🎧 Playback", value=playback, inline=False)
        embed.add_field(name="📋 Queue Management", value=queue, inline=False)
        embed.add_field(name="📁 Local Playlists", value=playlist, inline=False)
        embed.add_field(name="🔍 YouTube Integration", value=youtube, inline=False)

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="ping", description="Show bot latency")
    async def ping(self, interaction: discord.Interaction):
        """Show bot WebSocket heartbeat latency."""
        latency = round(self.bot.latency * 1000)
        embed = discord.Embed(
            title="🏓 Pong!",
            description=f"Latency: **{latency}ms**",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed)

    # =========================================================
    # Prefix Commands (!about, !help, !ping)
    # =========================================================

    @commands.command(name="about")
    async def about_prefix(self, ctx: commands.Context):
        """Show information about the bot (!about)."""
        uptime_seconds = int(time.time() - self.start_time)
        hours, remainder = divmod(uptime_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime_str = f"{hours}h {minutes}m {seconds}s"

        embed = discord.Embed(
            title="🎵 Discord Music Bot",
            description="A production-grade, self-hosted Discord music bot supporting local playlists and YouTube streaming.",
            color=discord.Color.blurple()
        )
        embed.add_field(name="Version", value=f"v{__version__}", inline=True)
        embed.add_field(name="Uptime", value=uptime_str, inline=True)
        embed.add_field(name="Servers Connected", value=str(len(self.bot.guilds)), inline=True)
        embed.set_footer(text=f"Requested by {ctx.author.display_name}")

        await ctx.send(embed=embed)

    @commands.command(name="help")
    async def help_prefix(self, ctx: commands.Context):
        """Show the help overview embed (!help)."""
        prefix = getattr(getattr(self.bot, 'config', None), 'command_prefix', '!')
        embed = discord.Embed(
            title="📖 Discord Music Bot - Command Overview",
            description=f"You can use slash commands (`/play`) or prefix commands (`{prefix}play`).",
            color=discord.Color.blue()
        )

        playback = (
            f"`{prefix}play <query or url>` - Play a track or YouTube URL\n"
            f"`{prefix}pause` & `{prefix}resume` - Pause/resume playback (DJ)\n"
            f"`{prefix}skip` & `{prefix}previous` - Skip track or go back (DJ)\n"
            f"`{prefix}stop` - Stop audio & clear queue (DJ)\n"
            f"`{prefix}volume [0-200]` - View or change playback volume (DJ)\n"
            f"`{prefix}seek <seconds>` - Jump to position in track (DJ)\n"
            f"`{prefix}nowplaying` (`{prefix}np`) - Display currently playing track\n"
            f"`{prefix}next` - Display the upcoming track\n"
            f"`{prefix}history` - View recently played tracks"
        )
        queue = (
            f"`{prefix}queue [page]` - Display upcoming queue\n"
            f"`{prefix}clear` - Clear queue (DJ)\n"
            f"`{prefix}shuffle` - Randomize upcoming tracks (DJ)\n"
            f"`{prefix}remove <index>` - Remove track from queue (DJ)\n"
            f"`{prefix}move <from> <to>` - Reorder queue items (DJ)"
        )
        playlist = (
            f"`{prefix}playlist list` - List available local playlists\n"
            f"`{prefix}playlist play <name>` - Load & play a playlist\n"
            f"`{prefix}playlist reload` - Rescan playlist folder from disk"
        )
        youtube = (
            "`/youtube search <query>` - Search YouTube metadata\n"
            "`/youtube video <url>` - Inspect video metadata\n"
            "`/youtube playlist <url>` - Inspect playlist metadata"
        )

        embed.add_field(name="🎧 Playback", value=playback, inline=False)
        embed.add_field(name="📋 Queue Management", value=queue, inline=False)
        embed.add_field(name="📁 Local Playlists", value=playlist, inline=False)
        embed.add_field(name="🔍 YouTube Integration", value=youtube, inline=False)

        await ctx.send(embed=embed)

    @commands.command(name="ping")
    async def ping_prefix(self, ctx: commands.Context):
        """Show bot WebSocket heartbeat latency (!ping)."""
        latency = round(self.bot.latency * 1000)
        embed = discord.Embed(
            title="🏓 Pong!",
            description=f"Latency: **{latency}ms**",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """Error handler for this cog."""
        logger.error(f"Error in general command: {error}")
        embed = discord.Embed(
            title="Error",
            description=f"An error occurred: {str(error)}",
            color=discord.Color.red()
        )
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(GeneralCog(bot))

