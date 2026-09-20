"""
Discord slash command cog for local playlist management and playback.
"""

import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from bot.audio.player import GuildPlayer
from bot.audio.source import AudioTrack, SourceType
from bot.discord.permissions import (
    require_permission, PermissionLevel, check_command_channel,
    require_prefix_permission, is_in_prefix_command_channel
)

logger = logging.getLogger(__name__)


def is_in_command_channel():
    """Predicate to check if command is in the designated channel."""
    async def predicate(interaction: discord.Interaction) -> bool:
        bot = interaction.client
        channel_id = getattr(bot.config, 'command_channel_id', None)
        return check_command_channel(interaction, channel_id)
    return app_commands.check(predicate)


class PlaylistCog(commands.Cog):
    """Cog for managing and playing local filesystem playlists."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def get_player(self, guild_id: int) -> GuildPlayer:
        """Retrieves or creates a GuildPlayer for the guild."""
        if guild_id not in self.bot._players:
            self.bot._players[guild_id] = GuildPlayer(self.bot, guild_id)
            self.bot._players[guild_id].volume = getattr(self.bot.config, 'default_volume', 75) / 100.0
        return self.bot._players[guild_id]

    def _build_list_embed(self) -> tuple[Optional[discord.Embed], str]:
        """Constructs list of playlists embed."""
        if not self.bot.playlist_manager:
            return None, "Playlist manager not initialized."

        playlists = self.bot.playlist_manager.get_all()
        if not playlists:
            return None, "No playlists found in the playlists directory."

        embed = discord.Embed(title="📁 Available Playlists", color=discord.Color.green())
        for pl in playlists:
            duration = int(pl.total_duration)
            mins, secs = divmod(duration, 60)
            hours, mins = divmod(mins, 60)
            dur_str = f"{hours}:{mins:02d}:{secs:02d}" if hours else f"{mins}:{secs:02d}"
            embed.add_field(
                name=f"🎵 {pl.name}",
                value=f"Tracks: **{pl.track_count}** | Total Duration: `{dur_str}`",
                inline=False
            )
        return embed, ""

    def _build_view_embed(self, name: str, page: int = 1) -> tuple[Optional[discord.Embed], str]:
        """Constructs view playlist tracks embed."""
        if not self.bot.playlist_manager:
            return None, "Playlist manager not initialized."

        playlist = self.bot.playlist_manager.get_playlist(name)
        if not playlist:
            return None, f"Playlist **'{name}'** not found."

        tracks = playlist.tracks
        per_page = 10
        total_pages = max(1, (len(tracks) + per_page - 1) // per_page)
        page = max(1, min(page, total_pages))
        start = (page - 1) * per_page
        page_tracks = tracks[start:start + per_page]

        embed = discord.Embed(
            title=f"📁 Playlist: {playlist.name}",
            description=f"Total tracks: **{playlist.track_count}**",
            color=discord.Color.green()
        )

        desc = ""
        for i, ptr in enumerate(page_tracks, start + 1):
            dur = ptr.duration_str if hasattr(ptr, 'duration_str') else (
                f"{int(ptr.duration // 60)}:{int(ptr.duration % 60):02d}" if ptr.duration else "Unknown"
            )
            artist_str = f"{ptr.artist} - " if ptr.artist else ""
            line = f"`{i}.` **{artist_str}{ptr.title}** ({dur})\n"
            if len(desc) + len(line) > 950:
                desc += f"... and {len(page_tracks) - (i - start)} more\n"
                break
            desc += line

        if desc:
            embed.add_field(name=f"Tracks (Page {page}/{total_pages})", value=desc, inline=False)
        else:
            embed.description = "Playlist is empty."

        prefix = getattr(getattr(self.bot, 'config', None), 'command_prefix', '!')
        embed.set_footer(text=f"Use /playlist play {playlist.name} or {prefix}playlist play {playlist.name} to play.")
        return embed, ""

    # =========================================================
    # Slash Commands (/playlist ...)
    # =========================================================

    playlist_group = app_commands.Group(name="playlist", description="Local playlist commands")

    @playlist_group.command(name="list", description="List all available local playlists")
    @is_in_command_channel()
    async def list_playlists(self, interaction: discord.Interaction):
        """Displays all scanned playlists."""
        embed, err = self._build_list_embed()
        if err:
            return await interaction.response.send_message(err, ephemeral=True)
        await interaction.response.send_message(embed=embed)

    @playlist_group.command(name="view", description="View tracks in a specific playlist")
    @app_commands.describe(name="Playlist name", page="Page number")
    @is_in_command_channel()
    async def view_playlist(self, interaction: discord.Interaction, name: str, page: int = 1):
        """Shows paginated tracks of a given playlist."""
        embed, err = self._build_view_embed(name, page)
        if err:
            return await interaction.response.send_message(err, ephemeral=True)
        await interaction.response.send_message(embed=embed)

    @playlist_group.command(name="play", description="Play a local playlist")
    @app_commands.describe(name="Playlist name", shuffle="Shuffle before playing", clear_queue="Clear existing queue first")
    @is_in_command_channel()
    async def play_playlist(
        self,
        interaction: discord.Interaction,
        name: str,
        shuffle: bool = False,
        clear_queue: bool = False
    ):
        """Loads all tracks from the playlist and adds them to queue."""
        if not self.bot.playlist_manager:
            return await interaction.response.send_message("Playlist manager not initialized.", ephemeral=True)

        playlist = self.bot.playlist_manager.get_playlist(name)
        if not playlist:
            return await interaction.response.send_message(f"Playlist **'{name}'** not found.", ephemeral=True)

        # Connect to voice if needed
        if not interaction.guild.voice_client:
            if interaction.user.voice:
                await interaction.user.voice.channel.connect(self_deaf=True)
            else:
                return await interaction.response.send_message("You must be in a voice channel to play music.", ephemeral=True)

        await interaction.response.defer()
        player = self.get_player(interaction.guild_id)

        if clear_queue:
            await player.stop()

        tracks = []
        for ptr in playlist.tracks:
            track = AudioTrack(
                title=ptr.title,
                artist=ptr.artist,
                album=ptr.album,
                duration=ptr.duration,
                source_type=SourceType.LOCAL_FILE,
                source_uri=str(ptr.file_path),
                requester_id=interaction.user.id,
                requester_name=interaction.user.display_name,
                playlist_name=playlist.name
            )
            tracks.append(track)

        if not tracks:
            return await interaction.followup.send(f"Playlist **'{name}'** contains no playable audio files.")

        if shuffle:
            import random
            random.shuffle(tracks)

        added = await player.queue.add_many(tracks)
        logger.info(f"Enqueued {added} tracks from playlist '{playlist.name}' for guild {interaction.guild_id}")

        # Start playback if idle
        if not interaction.guild.voice_client.is_playing() and not interaction.guild.voice_client.is_paused():
            first_track = await player.queue.current()
            if first_track:
                await player.play_track(first_track)

        msg = f"🎶 Enqueued **{added}** tracks from playlist **'{playlist.name}'**."
        if shuffle:
            msg += " (Shuffled)"
        await interaction.followup.send(msg)

    @playlist_group.command(name="reload", description="Rescan playlists directory from disk")
    @require_permission(PermissionLevel.DJ)
    @is_in_command_channel()
    async def reload_playlists(self, interaction: discord.Interaction):
        """Rescans disk for added or removed playlist files."""
        if not self.bot.playlist_manager:
            return await interaction.response.send_message("Playlist manager not initialized.", ephemeral=True)

        await interaction.response.defer()
        await self.bot.playlist_manager.reload()
        count = len(self.bot.playlist_manager.get_all())
        await interaction.followup.send(f"🔄 Playlists reloaded from disk. **{count}** playlists available.")

    # =========================================================
    # Prefix Commands (!playlist, !pl)
    # =========================================================

    @commands.group(name="playlist", aliases=["pl"], invoke_without_command=True)
    @is_in_prefix_command_channel()
    async def playlist_prefix(self, ctx: commands.Context):
        """Lists available playlists (!playlist or !pl)."""
        embed, err = self._build_list_embed()
        if err:
            return await ctx.send(err)
        await ctx.send(embed=embed)

    @playlist_prefix.command(name="list")
    @is_in_prefix_command_channel()
    async def playlist_list_prefix(self, ctx: commands.Context):
        """Lists available playlists (!playlist list)."""
        embed, err = self._build_list_embed()
        if err:
            return await ctx.send(err)
        await ctx.send(embed=embed)

    @playlist_prefix.command(name="view", aliases=["show"])
    @is_in_prefix_command_channel()
    async def playlist_view_prefix(self, ctx: commands.Context, name: str, page: int = 1):
        """Views tracks in a playlist (!playlist view <name> [page])."""
        embed, err = self._build_view_embed(name, page)
        if err:
            return await ctx.send(err)
        await ctx.send(embed=embed)

    @playlist_prefix.command(name="play")
    @is_in_prefix_command_channel()
    async def playlist_play_prefix(self, ctx: commands.Context, name: str, shuffle_flag: Optional[str] = None):
        """Plays a playlist (!playlist play <name> [shuffle])."""
        if not self.bot.playlist_manager:
            return await ctx.send("Playlist manager not initialized.")

        playlist = self.bot.playlist_manager.get_playlist(name)
        if not playlist:
            return await ctx.send(f"Playlist **'{name}'** not found.")

        if not ctx.guild.voice_client:
            if ctx.author.voice:
                await ctx.author.voice.channel.connect(self_deaf=True)
            else:
                return await ctx.send("You must be in a voice channel to play music.")

        player = self.get_player(ctx.guild.id)
        tracks = []
        for ptr in playlist.tracks:
            track = AudioTrack(
                title=ptr.title,
                artist=ptr.artist,
                album=ptr.album,
                duration=ptr.duration,
                source_type=SourceType.LOCAL_FILE,
                source_uri=str(ptr.file_path),
                requester_id=ctx.author.id,
                requester_name=ctx.author.display_name,
                playlist_name=playlist.name
            )
            tracks.append(track)

        if not tracks:
            return await ctx.send(f"Playlist **'{name}'** contains no playable audio files.")

        shuffle = bool(shuffle_flag and shuffle_flag.lower() in ('shuffle', 'shuffled', 'true', '1', 'yes'))
        if shuffle:
            import random
            random.shuffle(tracks)

        added = await player.queue.add_many(tracks)
        logger.info(f"Enqueued {added} tracks from playlist '{playlist.name}' for guild {ctx.guild.id}")

        if not ctx.guild.voice_client.is_playing() and not ctx.guild.voice_client.is_paused():
            first_track = await player.queue.current()
            if first_track:
                await player.play_track(first_track)

        msg = f"🎶 Enqueued **{added}** tracks from playlist **'{playlist.name}'**."
        if shuffle:
            msg += " (Shuffled)"
        await ctx.send(msg)

    @playlist_prefix.command(name="reload")
    @require_prefix_permission(PermissionLevel.DJ)
    @is_in_prefix_command_channel()
    async def playlist_reload_prefix(self, ctx: commands.Context):
        """Rescans disk for added or removed playlist files (!playlist reload)."""
        if not self.bot.playlist_manager:
            return await ctx.send("Playlist manager not initialized.")

        await self.bot.playlist_manager.reload()
        count = len(self.bot.playlist_manager.get_all())
        await ctx.send(f"🔄 Playlists reloaded from disk. **{count}** playlists available.")


async def setup(bot: commands.Bot):
    await bot.add_cog(PlaylistCog(bot))

