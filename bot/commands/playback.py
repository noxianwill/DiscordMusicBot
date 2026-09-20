"""
Discord slash command cog for audio playback controls.
"""

import logging
from typing import Optional
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from bot.audio.player import GuildPlayer
from bot.audio.metadata import MetadataExtractor
from bot.audio.source import AudioTrack, SourceType
from bot.audio.queue import LoopMode
from bot.utils.embeds import EmbedFactory
from bot.discord.permissions import (
    require_permission, PermissionLevel, check_command_channel,
    require_prefix_permission, is_in_prefix_command_channel
)

logger = logging.getLogger(__name__)


def is_in_command_channel():
    """Predicate to check if command is invoked in designated channel."""
    async def predicate(interaction: discord.Interaction) -> bool:
        bot = interaction.client
        channel_id = getattr(bot.config, 'command_channel_id', None)
        return check_command_channel(interaction, channel_id)
    return app_commands.check(predicate)



class NowPlayingView(discord.ui.View):
    """Interactive view for playback controls on Now Playing embeds."""

    def __init__(self, player: GuildPlayer, interaction: discord.Interaction):
        super().__init__(timeout=180)
        self.player = player
        self.original_interaction = interaction

    @discord.ui.button(label="Play/Pause", style=discord.ButtonStyle.primary, emoji="⏯️")
    async def toggle_playback(self, interaction: discord.Interaction, button: discord.ui.Button):
        voice_client = interaction.guild.voice_client
        if not voice_client:
            return await interaction.response.send_message("Not connected to voice.", ephemeral=True)

        if voice_client.is_paused():
            await self.player.resume()
            await interaction.response.send_message("▶️ Resumed playback.", ephemeral=True)
        elif voice_client.is_playing():
            await self.player.pause()
            await interaction.response.send_message("⏸️ Paused playback.", ephemeral=True)
        else:
            await interaction.response.send_message("Nothing is playing.", ephemeral=True)

    @discord.ui.button(label="Skip", style=discord.ButtonStyle.secondary, emoji="⏭️")
    async def skip_track(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.player.skip()
        await interaction.response.send_message("⏭️ Skipped track.", ephemeral=True)

    @discord.ui.button(label="Stop", style=discord.ButtonStyle.danger, emoji="⏹️")
    async def stop_playback(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.player.stop()
        await interaction.response.send_message("⏹️ Playback stopped and queue cleared.", ephemeral=True)


class PlaybackCog(commands.Cog):
    """Cog handling all playback commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def get_player(self, guild_id: int) -> GuildPlayer:
        """Retrieves or creates a GuildPlayer instance."""
        if guild_id not in self.bot._players:
            self.bot._players[guild_id] = GuildPlayer(self.bot, guild_id)
            self.bot._players[guild_id].volume = getattr(self.bot.config, 'default_volume', 75) / 100.0
        return self.bot._players[guild_id]

    @app_commands.command(name="join", description="Connect the bot to your current voice channel")
    @is_in_command_channel()
    async def join_cmd(self, interaction: discord.Interaction):
        """Connects the bot to the caller's voice channel."""
        if not interaction.user.voice:
            return await interaction.response.send_message("You are not in a voice channel.", ephemeral=True)

        channel = interaction.user.voice.channel
        if not interaction.guild.voice_client:
            await channel.connect(self_deaf=True)
            await interaction.response.send_message(f"🔊 Joined {channel.mention}")
        else:
            await interaction.guild.voice_client.move_to(channel)
            await interaction.response.send_message(f"🔊 Moved to {channel.mention}")

    @app_commands.command(name="leave", description="Disconnect the bot from voice")
    @require_permission(PermissionLevel.DJ)
    @is_in_command_channel()
    async def leave_cmd(self, interaction: discord.Interaction):
        """Disconnects the bot and cleans up the player."""
        if interaction.guild.voice_client:
            player = self.get_player(interaction.guild_id)
            await player.destroy()
            if interaction.guild_id in self.bot._players:
                del self.bot._players[interaction.guild_id]
            if interaction.guild.voice_client:
                try:
                    await interaction.guild.voice_client.disconnect()
                except Exception:
                    pass
            await interaction.response.send_message("👋 Disconnected from voice channel.")
        else:
            await interaction.response.send_message("Not connected to a voice channel.", ephemeral=True)

    @app_commands.command(name="play", description="Play audio from a YouTube URL, search term, or local file")
    @app_commands.describe(query="URL, search query, or local file path")
    @is_in_command_channel()
    async def play_cmd(self, interaction: discord.Interaction, query: str):
        """Adds a track to the queue and begins playback."""
        await interaction.response.defer()

        # Connect to voice if not already connected
        if not interaction.guild.voice_client:
            if interaction.user.voice:
                await interaction.user.voice.channel.connect(self_deaf=True)
            else:
                return await interaction.followup.send("You must be in a voice channel to use /play.")

        player = self.get_player(interaction.guild_id)

        # Check if query is a local file
        local_path = Path(query)
        if local_path.exists() and local_path.is_file():
            track = await MetadataExtractor.extract(local_path)
            track.source_type = SourceType.LOCAL_FILE
            track.source_uri = str(local_path)
            track.requester_id = interaction.user.id
            track.requester_name = interaction.user.display_name
            await player.play(track)
            embed = EmbedFactory.track_added(track)
            return await interaction.followup.send(embed=embed)

        # YouTube playback via yt-dlp
        try:
            if "list=" in query and ("youtube.com" in query or "youtu.be" in query):
                tracks = await player.play_youtube_playlist(
                    query,
                    requester_id=interaction.user.id,
                    requester_name=interaction.user.display_name
                )
                return await interaction.followup.send(f"✅ Added **{len(tracks)}** tracks from YouTube playlist to queue.")
            else:
                track = await player.play_youtube(
                    query,
                    requester_id=interaction.user.id,
                    requester_name=interaction.user.display_name
                )
                embed = EmbedFactory.track_added(track)
                return await interaction.followup.send(embed=embed)
        except Exception as e:
            import re
            clean_err = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', str(e)).strip()
            logger.error(f"Error playing track: {clean_err}")
            return await interaction.followup.send(f"❌ Error playing track: {clean_err}")

    @app_commands.command(name="pause", description="Pause current playback")
    @require_permission(PermissionLevel.DJ)
    @is_in_command_channel()
    async def pause_cmd(self, interaction: discord.Interaction):
        """Pauses the current track."""
        player = self.get_player(interaction.guild_id)
        await player.pause()
        await interaction.response.send_message("⏸️ Playback paused.")

    @app_commands.command(name="resume", description="Resume paused playback")
    @require_permission(PermissionLevel.DJ)
    @is_in_command_channel()
    async def resume_cmd(self, interaction: discord.Interaction):
        """Resumes playback."""
        player = self.get_player(interaction.guild_id)
        await player.resume()
        await interaction.response.send_message("▶️ Playback resumed.")

    @app_commands.command(name="stop", description="Stop playback and clear the queue")
    @require_permission(PermissionLevel.DJ)
    @is_in_command_channel()
    async def stop_cmd(self, interaction: discord.Interaction):
        """Stops playback and clears the queue."""
        player = self.get_player(interaction.guild_id)
        await player.stop()
        await interaction.response.send_message("⏹️ Playback stopped and queue cleared.")

    @app_commands.command(name="skip", description="Skip to the next track")
    @require_permission(PermissionLevel.DJ)
    @is_in_command_channel()
    async def skip_cmd(self, interaction: discord.Interaction):
        """Skips the currently playing track."""
        player = self.get_player(interaction.guild_id)
        await player.skip()
        await interaction.response.send_message("⏭️ Skipped track.")

    @app_commands.command(name="previous", description="Play previous track")
    @require_permission(PermissionLevel.DJ)
    @is_in_command_channel()
    async def previous_cmd(self, interaction: discord.Interaction):
        """Plays the previous track in the queue."""
        player = self.get_player(interaction.guild_id)
        await player.previous()
        await interaction.response.send_message("⏮️ Returning to previous track.")

    @app_commands.command(name="seek", description="Seek to a position in seconds in the current track")
    @app_commands.describe(seconds="Timestamp in seconds to jump to")
    @require_permission(PermissionLevel.DJ)
    @is_in_command_channel()
    async def seek_cmd(self, interaction: discord.Interaction, seconds: float):
        """Seeks to a timestamp in seconds."""
        player = self.get_player(interaction.guild_id)
        await player.seek(seconds)
        mins, secs = divmod(int(seconds), 60)
        await interaction.response.send_message(f"⏩ Jumped to `{mins:02d}:{secs:02d}`.")

    @app_commands.command(name="restart", description="Restart current track from the beginning")
    @require_permission(PermissionLevel.DJ)
    @is_in_command_channel()
    async def restart_cmd(self, interaction: discord.Interaction):
        """Restarts the currently playing track."""
        player = self.get_player(interaction.guild_id)
        await player.seek(0)
        await interaction.response.send_message("🔄 Restarted current track from the beginning.")

    @app_commands.command(name="loop", description="Configure loop mode: off, track, or queue")
    @app_commands.describe(mode="Loop mode to apply")
    @app_commands.choices(mode=[
        app_commands.Choice(name="Off", value="off"),
        app_commands.Choice(name="Track", value="track"),
        app_commands.Choice(name="Queue", value="queue"),
    ])
    @require_permission(PermissionLevel.DJ)
    @is_in_command_channel()
    async def loop_cmd(self, interaction: discord.Interaction, mode: app_commands.Choice[str]):
        """Sets loop mode."""
        player = self.get_player(interaction.guild_id)
        loop_map = {
            "off": LoopMode.OFF,
            "track": LoopMode.TRACK,
            "queue": LoopMode.QUEUE,
        }
        selected_mode = loop_map[mode.value]
        await player.set_loop(selected_mode)
        await interaction.response.send_message(f"🔁 Loop mode set to **{mode.name}**.")

    @app_commands.command(name="nowplaying", description="Show currently playing track")
    @is_in_command_channel()
    async def nowplaying_cmd(self, interaction: discord.Interaction):
        """Displays currently playing track with interactive controls."""
        player = self.get_player(interaction.guild_id)
        track = await player.queue.current()
        if not track:
            return await interaction.response.send_message("Nothing is playing right now.", ephemeral=True)

        embed = EmbedFactory.now_playing(track)
        view = NowPlayingView(player, interaction)
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="history", description="Show recently played tracks")
    @is_in_command_channel()
    async def history_cmd(self, interaction: discord.Interaction):
        """Shows recent playback history."""
        player = self.get_player(interaction.guild_id)
        history = player.history
        if not history:
            return await interaction.response.send_message("Playback history is empty.", ephemeral=True)

        embed = discord.Embed(title="📜 Playback History", color=discord.Color.blue())
        desc = ""
        for i, track in enumerate(list(history)[-10:], 1):
            desc += f"`{i}.` {track.display_title()} ({track.duration_str()})\n"
        embed.description = desc
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="next", description="Show the next upcoming track")
    @is_in_command_channel()
    async def next_cmd(self, interaction: discord.Interaction):
        """Shows next upcoming track."""
        player = self.get_player(interaction.guild_id)
        upcoming = await player.queue.upcoming()
        if not upcoming:
            return await interaction.response.send_message("No upcoming tracks in queue.", ephemeral=True)

        embed = EmbedFactory.track_info(upcoming[0], title="⏭️ Next Track")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="volume", description="Set or view playback volume")
    @app_commands.describe(vol="Volume percentage (0 to 200)")
    @is_in_command_channel()
    async def volume_cmd(self, interaction: discord.Interaction, vol: Optional[int] = None):
        """Gets or sets volume."""
        player = self.get_player(interaction.guild_id)
        if vol is None:
            current = int(player.volume * 100)
            return await interaction.response.send_message(f"🔊 Current volume is **{current}%**.")

        vol = max(0, min(200, vol))
        await player.set_volume(vol / 100.0)
        await interaction.response.send_message(f"🔊 Volume set to **{vol}%**.")

    # ---------------------------------------------------------
    # Legacy / Prefix Commands (!play, !skip, etc.)
    # ---------------------------------------------------------

    @commands.command(name="join")
    @is_in_prefix_command_channel()
    async def join_prefix(self, ctx: commands.Context):
        """Connects the bot to the caller's voice channel."""
        if not ctx.author.voice:
            return await ctx.send("You are not in a voice channel.")
        channel = ctx.author.voice.channel
        if not ctx.guild.voice_client:
            await channel.connect(self_deaf=True)
            await ctx.send(f"🔊 Joined {channel.mention}")
        else:
            await ctx.guild.voice_client.move_to(channel)
            await ctx.send(f"🔊 Moved to {channel.mention}")

    @commands.command(name="leave", aliases=["disconnect", "dc"])
    @require_prefix_permission(PermissionLevel.DJ)
    @is_in_prefix_command_channel()
    async def leave_prefix(self, ctx: commands.Context):
        """Disconnects the bot and cleans up the player."""
        if ctx.guild.voice_client:
            player = self.get_player(ctx.guild.id)
            await player.destroy()
            if ctx.guild.id in self.bot._players:
                del self.bot._players[ctx.guild.id]
            if ctx.guild.voice_client:
                try:
                    await ctx.guild.voice_client.disconnect()
                except Exception:
                    pass
            await ctx.send("👋 Disconnected from voice channel.")
        else:
            await ctx.send("Not connected to a voice channel.")

    @commands.command(name="play", aliases=["p"])
    @is_in_prefix_command_channel()
    async def play_prefix(self, ctx: commands.Context, *, query: str):
        """Adds a track to the queue and begins playback."""
        if not ctx.guild.voice_client:
            if ctx.author.voice:
                await ctx.author.voice.channel.connect(self_deaf=True)
            else:
                return await ctx.send("You must be in a voice channel to use play.")

        player = self.get_player(ctx.guild.id)

        # Check local file
        local_path = Path(query)
        if local_path.exists() and local_path.is_file():
            track = await MetadataExtractor.extract(local_path)
            track.source_type = SourceType.LOCAL_FILE
            track.source_uri = str(local_path)
            track.requester_id = ctx.author.id
            track.requester_name = ctx.author.display_name
            await player.play(track)
            embed = EmbedFactory.track_added(track)
            return await ctx.send(embed=embed)

        # YouTube playback via yt-dlp / API
        try:
            if "list=" in query and ("youtube.com" in query or "youtu.be" in query):
                tracks = await player.play_youtube_playlist(
                    query,
                    requester_id=ctx.author.id,
                    requester_name=ctx.author.display_name
                )
                return await ctx.send(f"✅ Added **{len(tracks)}** tracks from YouTube playlist to queue.")
            else:
                track = await player.play_youtube(
                    query,
                    requester_id=ctx.author.id,
                    requester_name=ctx.author.display_name
                )
                embed = EmbedFactory.track_added(track)
                return await ctx.send(embed=embed)
        except Exception as e:
            import re
            clean_err = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', str(e)).strip()
            logger.error(f"Error playing track: {clean_err}")
            return await ctx.send(f"❌ Error playing track: {clean_err}")

    @commands.command(name="pause")
    @require_prefix_permission(PermissionLevel.DJ)
    @is_in_prefix_command_channel()
    async def pause_prefix(self, ctx: commands.Context):
        """Pauses the current track."""
        player = self.get_player(ctx.guild.id)
        await player.pause()
        await ctx.send("⏸️ Playback paused.")

    @commands.command(name="resume")
    @require_prefix_permission(PermissionLevel.DJ)
    @is_in_prefix_command_channel()
    async def resume_prefix(self, ctx: commands.Context):
        """Resumes playback."""
        player = self.get_player(ctx.guild.id)
        await player.resume()
        await ctx.send("▶️ Playback resumed.")

    @commands.command(name="stop")
    @require_prefix_permission(PermissionLevel.DJ)
    @is_in_prefix_command_channel()
    async def stop_prefix(self, ctx: commands.Context):
        """Stops playback and clears the queue."""
        player = self.get_player(ctx.guild.id)
        await player.stop()
        await ctx.send("⏹️ Playback stopped and queue cleared.")

    @commands.command(name="skip", aliases=["s"])
    @require_prefix_permission(PermissionLevel.DJ)
    @is_in_prefix_command_channel()
    async def skip_prefix(self, ctx: commands.Context):
        """Skips the currently playing track."""
        player = self.get_player(ctx.guild.id)
        await player.skip()
        await ctx.send("⏭️ Skipped track.")

    @commands.command(name="previous", aliases=["prev"])
    @require_prefix_permission(PermissionLevel.DJ)
    @is_in_prefix_command_channel()
    async def previous_prefix(self, ctx: commands.Context):
        """Plays the previous track in the queue."""
        player = self.get_player(ctx.guild.id)
        await player.previous()
        await ctx.send("⏮️ Returning to previous track.")

    @commands.command(name="seek")
    @require_prefix_permission(PermissionLevel.DJ)
    @is_in_prefix_command_channel()
    async def seek_prefix(self, ctx: commands.Context, seconds: float):
        """Seeks to a timestamp in seconds."""
        player = self.get_player(ctx.guild.id)
        await player.seek(seconds)
        mins, secs = divmod(int(seconds), 60)
        await ctx.send(f"⏩ Jumped to `{mins:02d}:{secs:02d}`.")

    @commands.command(name="restart")
    @require_prefix_permission(PermissionLevel.DJ)
    @is_in_prefix_command_channel()
    async def restart_prefix(self, ctx: commands.Context):
        """Restarts the currently playing track."""
        player = self.get_player(ctx.guild.id)
        await player.seek(0)
        await ctx.send("🔄 Restarted current track from the beginning.")

    @commands.command(name="loop")
    @require_prefix_permission(PermissionLevel.DJ)
    @is_in_prefix_command_channel()
    async def loop_prefix(self, ctx: commands.Context, mode: str = "off"):
        """Sets loop mode (off, track, queue)."""
        player = self.get_player(ctx.guild.id)
        loop_map = {
            "off": LoopMode.OFF,
            "track": LoopMode.TRACK,
            "queue": LoopMode.QUEUE,
        }
        selected_mode = loop_map.get(mode.lower(), LoopMode.OFF)
        await player.set_loop(selected_mode)
        await ctx.send(f"🔁 Loop mode set to **{selected_mode.name.capitalize()}**.")

    @commands.command(name="nowplaying", aliases=["np"])
    @is_in_prefix_command_channel()
    async def nowplaying_prefix(self, ctx: commands.Context):
        """Displays currently playing track."""
        player = self.get_player(ctx.guild.id)
        track = await player.queue.current()
        if not track:
            return await ctx.send("Nothing is playing right now.")
        embed = EmbedFactory.now_playing(track)
        await ctx.send(embed=embed)

    @commands.command(name="history")
    @is_in_prefix_command_channel()
    async def history_prefix(self, ctx: commands.Context):
        """Shows recent playback history."""
        player = self.get_player(ctx.guild.id)
        history = player.history
        if not history:
            return await ctx.send("Playback history is empty.")
        embed = discord.Embed(title="📜 Playback History", color=discord.Color.blue())
        desc = ""
        for i, track in enumerate(list(history)[-10:], 1):
            desc += f"`{i}.` {track.display_title()} ({track.duration_str()})\n"
        embed.description = desc
        await ctx.send(embed=embed)

    @commands.command(name="next")
    @is_in_prefix_command_channel()
    async def next_prefix(self, ctx: commands.Context):
        """Shows next upcoming track."""
        player = self.get_player(ctx.guild.id)
        upcoming = await player.queue.upcoming()
        if not upcoming:
            return await ctx.send("No upcoming tracks in queue.")
        embed = EmbedFactory.track_info(upcoming[0], title="⏭️ Next Track")
        await ctx.send(embed=embed)

    @commands.command(name="volume", aliases=["vol"])
    @require_prefix_permission(PermissionLevel.DJ)
    @is_in_prefix_command_channel()
    async def volume_prefix(self, ctx: commands.Context, vol: Optional[int] = None):
        """Gets or sets volume."""
        player = self.get_player(ctx.guild.id)
        if vol is None:
            current = int(player.volume * 100)
            return await ctx.send(f"🔊 Current volume is **{current}%**.")
        vol = max(0, min(200, vol))
        await player.set_volume(vol / 100.0)
        await ctx.send(f"🔊 Volume set to **{vol}%**.")


async def setup(bot: commands.Bot):
    await bot.add_cog(PlaybackCog(bot))

