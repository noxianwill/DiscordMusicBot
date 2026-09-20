import logging
import asyncio

import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger(__name__)


class EventsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._leave_tasks = {}

    async def cog_load(self):
        # Register global app command error handler on tree
        self.bot.tree.on_error = self.on_app_command_error

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info(f"Logged in as {self.bot.user} (ID: {self.bot.user.id})")
        logger.info(f"Connected to {len(self.bot.guilds)} guild(s).")
        # Set initial idle presence from config
        if self.bot.presence_manager:
            await self.bot.presence_manager.set_idle()

    @commands.Cog.listener()
    async def on_app_command_completion(self, interaction: discord.Interaction, command: app_commands.Command):
        """Logs execution of slash commands."""
        if getattr(self.bot.config, 'log_commands', True):
            guild_name = interaction.guild.name if interaction.guild else "DM"
            channel_name = getattr(interaction.channel, 'name', 'DirectMessage')
            user_str = f"{interaction.user} (ID: {interaction.user.id})"
            logger.info(f"Command '/{command.name}' executed by {user_str} in '{guild_name}' #{channel_name}")

    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """Global error handler for application (slash) commands."""
        cmd_name = interaction.command.name if interaction.command else "unknown"
        user_str = f"{interaction.user} (ID: {interaction.user.id})"
        guild_str = f"'{interaction.guild.name}' (ID: {interaction.guild.id})" if interaction.guild else "DM"

        # Log complete error with traceback
        logger.error(f"Error in command '/{cmd_name}' from {user_str} in {guild_str}: {error}", exc_info=error)

        # Inform the user with an appropriate message
        if isinstance(error, (app_commands.MissingPermissions, app_commands.CheckFailure)):
            msg = f"❌ Permission denied: {error}"
        else:
            msg = f"❌ An error occurred while executing `/{cmd_name}`."

        try:
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_command_completion(self, ctx: commands.Context):
        """Logs execution of prefix commands."""
        if getattr(self.bot.config, 'log_commands', True) and ctx.command:
            guild_name = ctx.guild.name if ctx.guild else "DM"
            channel_name = getattr(ctx.channel, 'name', 'DirectMessage')
            user_str = f"{ctx.author} (ID: {ctx.author.id})"
            logger.info(f"Prefix command '{ctx.prefix}{ctx.command.name}' executed by {user_str} in '{guild_name}' #{channel_name}")

    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        """Logs and handles errors in prefix commands."""
        if isinstance(error, commands.CommandNotFound):
            return

        cmd_name = ctx.command.name if ctx.command else "unknown"
        user_str = f"{ctx.author} (ID: {ctx.author.id})"
        guild_str = f"'{ctx.guild.name}' (ID: {ctx.guild.id})" if ctx.guild else "DM"
        logger.error(f"Error in prefix command '{ctx.prefix}{cmd_name}' by {user_str} in {guild_str}: {error}")

        if isinstance(error, (commands.CheckFailure, commands.MissingPermissions)):
            await ctx.send(f"❌ {error}")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"❌ Missing argument: `{error.param.name}`. Usage: `{ctx.prefix}{cmd_name} <{error.param.name}>`")
        else:
            await ctx.send(f"❌ An error occurred executing `{ctx.prefix}{cmd_name}`.")


    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if not self.bot.config.auto_leave:
            return

        if member.id == self.bot.user.id:
            # Bot disconnected manually or externally
            if before.channel and not after.channel:
                if member.guild.id in self.bot._players:
                    await self.bot._players[member.guild.id].destroy()
                    del self.bot._players[member.guild.id]
            return

        bot_voice_client = member.guild.voice_client
        if not bot_voice_client:
            return

        if bot_voice_client.channel:
            channel = bot_voice_client.channel
            non_bot_members = [m for m in channel.members if not m.bot]
            if not non_bot_members:
                if member.guild.id not in self._leave_tasks:
                    logger.info(f"Scheduling auto-leave for guild '{member.guild.name}' (ID: {member.guild.id}) in {self.bot.config.auto_leave_delay}s")
                    self._leave_tasks[member.guild.id] = self.bot.loop.create_task(
                        self.auto_leave_task(member.guild.id, bot_voice_client)
                    )
            else:
                if member.guild.id in self._leave_tasks:
                    logger.info(f"Cancelling auto-leave for guild '{member.guild.name}' (ID: {member.guild.id}) - user rejoined")
                    self._leave_tasks[member.guild.id].cancel()
                    del self._leave_tasks[member.guild.id]

    async def auto_leave_task(self, guild_id: int, voice_client: discord.VoiceClient):
        delay = self.bot.config.auto_leave_delay
        try:
            await asyncio.sleep(delay)
            if voice_client.is_connected():
                guild = self.bot.get_guild(guild_id)
                guild_name = guild.name if guild else str(guild_id)
                logger.info(f"Auto-leaving voice channel in guild '{guild_name}' (ID: {guild_id}) due to inactivity")
                if guild_id in self.bot._players:
                    await self.bot._players[guild_id].destroy()
                    del self.bot._players[guild_id]
                await voice_client.disconnect()
        except asyncio.CancelledError:
            pass
        finally:
            if guild_id in self._leave_tasks:
                del self._leave_tasks[guild_id]


async def setup(bot: commands.Bot):
    await bot.add_cog(EventsCog(bot))
