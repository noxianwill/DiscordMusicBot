"""
Discord slash and prefix command cog for queue operations.
"""

import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from bot.audio.player import GuildPlayer
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


class QueueCog(commands.Cog):
    """Cog for viewing and managing the playback queue."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def get_player(self, guild_id: int) -> GuildPlayer:
        """Retrieves or creates a GuildPlayer for the guild."""
        if guild_id not in self.bot._players:
            self.bot._players[guild_id] = GuildPlayer(self.bot, guild_id)
            self.bot._players[guild_id].volume = getattr(self.bot.config, 'default_volume', 75) / 100.0
        return self.bot._players[guild_id]

    async def _build_queue_embed(self, player: GuildPlayer, page: int = 1) -> tuple[Optional[discord.Embed], str]:
        """Constructs a safe, paginated embed for the queue ensuring values stay within Discord limits."""
        if player.queue.is_empty and not await player.queue.current():
            return None, "The queue is empty."

        tracks, current_page, total_pages = await player.queue.get_page(page, per_page=10)
        current_idx = player.queue.current_index

        embed = discord.Embed(title="🎶 Playback Queue", color=discord.Color.purple())

        current = await player.queue.current()
        if current and current_page == 1:
            curr_str = f"▶️ **{current.display_title()}** | {current.duration_str()} | Requested by {current.requester_name}"
            if len(curr_str) > 1000:
                curr_str = curr_str[:997] + "..."
            embed.add_field(
                name="Currently Playing",
                value=curr_str,
                inline=False
            )

        if tracks:
            desc = ""
            for i, track in enumerate(tracks):
                actual_idx = (current_page - 1) * 10 + i
                prefix = "▶️ " if actual_idx == current_idx else f"`{actual_idx + 1}.` "
                line = f"{prefix}**{track.display_title()}** | {track.duration_str()} | {track.requester_name}\n"
                if len(desc) + len(line) > 950:
                    desc += f"... and {len(tracks) - i} more\n"
                    break
                desc += line

            if desc:
                embed.add_field(name="Up Next", value=desc, inline=False)

        embed.set_footer(text=f"Page {current_page}/{max(1, total_pages)} | Total tracks: {len(player.queue)}")
        return embed, ""

    # =========================================================
    # Slash Commands (/queue ...)
    # =========================================================

    queue_group = app_commands.Group(name="queue", description="Queue management commands")

    @queue_group.command(name="show", description="Show the current playback queue")
    @is_in_command_channel()
    async def show_queue(self, interaction: discord.Interaction, page: int = 1):
        """Displays paginated list of upcoming tracks."""
        player = self.get_player(interaction.guild_id)
        embed, err = await self._build_queue_embed(player, page)
        if err:
            return await interaction.response.send_message(err, ephemeral=True)
        await interaction.response.send_message(embed=embed)

    @queue_group.command(name="clear", description="Clear the queue (DJ only)")
    @require_permission(PermissionLevel.DJ)
    @is_in_command_channel()
    async def clear_queue(self, interaction: discord.Interaction):
        """Clears all upcoming tracks."""
        player = self.get_player(interaction.guild_id)
        await player.queue.clear()
        await interaction.response.send_message("🗑️ Queue cleared.")

    @queue_group.command(name="shuffle", description="Shuffle the upcoming tracks in the queue")
    @require_permission(PermissionLevel.DJ)
    @is_in_command_channel()
    async def shuffle_queue(self, interaction: discord.Interaction):
        """Shuffles the remaining tracks."""
        player = self.get_player(interaction.guild_id)
        await player.queue.shuffle()
        await interaction.response.send_message("🔀 Queue shuffled.")

    @queue_group.command(name="remove", description="Remove a track by its position number")
    @require_permission(PermissionLevel.DJ)
    @is_in_command_channel()
    async def remove_track(self, interaction: discord.Interaction, index: int):
        """Removes a track at position index."""
        player = self.get_player(interaction.guild_id)
        removed = await player.queue.remove(index - 1)
        if removed:
            await interaction.response.send_message(f"❌ Removed **{removed.display_title()}** from the queue.")
        else:
            await interaction.response.send_message("Invalid track index.", ephemeral=True)

    @queue_group.command(name="move", description="Move a track from one position to another")
    @require_permission(PermissionLevel.DJ)
    @is_in_command_channel()
    async def move_track(self, interaction: discord.Interaction, from_pos: int, to_pos: int):
        """Moves a track from from_pos to to_pos."""
        player = self.get_player(interaction.guild_id)
        success = await player.queue.move(from_pos - 1, to_pos - 1)
        if success:
            await interaction.response.send_message(f"Moved track from position #{from_pos} to #{to_pos}.")
        else:
            await interaction.response.send_message("Invalid position numbers.", ephemeral=True)

    # =========================================================
    # Prefix Commands (!queue, !q, !clear, !shuffle)
    # =========================================================

    @commands.group(name="queue", aliases=["q"], invoke_without_command=True)
    @is_in_prefix_command_channel()
    async def queue_prefix(self, ctx: commands.Context, page: int = 1):
        """Displays current playback queue (e.g. !queue [page])."""
        player = self.get_player(ctx.guild.id)
        embed, err = await self._build_queue_embed(player, page)
        if err:
            return await ctx.send(err)
        await ctx.send(embed=embed)

    @queue_prefix.command(name="show")
    @is_in_prefix_command_channel()
    async def queue_show_prefix(self, ctx: commands.Context, page: int = 1):
        """Shows the queue (!queue show [page])."""
        player = self.get_player(ctx.guild.id)
        embed, err = await self._build_queue_embed(player, page)
        if err:
            return await ctx.send(err)
        await ctx.send(embed=embed)

    @commands.command(name="clear")
    @require_prefix_permission(PermissionLevel.DJ)
    @is_in_prefix_command_channel()
    async def clear_prefix(self, ctx: commands.Context):
        """Clears all upcoming tracks."""
        player = self.get_player(ctx.guild.id)
        await player.queue.clear()
        await ctx.send("🗑️ Queue cleared.")

    @commands.command(name="shuffle")
    @require_prefix_permission(PermissionLevel.DJ)
    @is_in_prefix_command_channel()
    async def shuffle_prefix(self, ctx: commands.Context):
        """Shuffles remaining tracks."""
        player = self.get_player(ctx.guild.id)
        await player.queue.shuffle()
        await ctx.send("🔀 Queue shuffled.")

    @commands.command(name="remove")
    @require_prefix_permission(PermissionLevel.DJ)
    @is_in_prefix_command_channel()
    async def remove_prefix(self, ctx: commands.Context, index: int):
        """Removes a track at position index (!remove <index>)."""
        player = self.get_player(ctx.guild.id)
        removed = await player.queue.remove(index - 1)
        if removed:
            await ctx.send(f"❌ Removed **{removed.display_title()}** from the queue.")
        else:
            await ctx.send("Invalid track index.")

    @commands.command(name="move")
    @require_prefix_permission(PermissionLevel.DJ)
    @is_in_prefix_command_channel()
    async def move_prefix(self, ctx: commands.Context, from_pos: int, to_pos: int):
        """Moves a track from one position to another (!move <from> <to>)."""
        player = self.get_player(ctx.guild.id)
        success = await player.queue.move(from_pos - 1, to_pos - 1)
        if success:
            await ctx.send(f"Moved track from position #{from_pos} to #{to_pos}.")
        else:
            await ctx.send("Invalid position numbers.")


async def setup(bot: commands.Bot):
    await bot.add_cog(QueueCog(bot))

