"""
Dashboard command for DiscordMusicBot.
Provides /dashboard and !dashboard to return the Web UI URL.
"""

import re
import logging
import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger(__name__)


def get_dashboard_url(panel_url: str) -> str:
    """Converts a WebSocket agent PANEL_URL to the HTTP(S) Web UI dashboard URL."""
    url = panel_url.strip()
    if url.startswith("wss://"):
        url = "https://" + url[6:]
    elif url.startswith("ws://"):
        url = "http://" + url[5:]
    # Strip /agent or /agent/ from the end
    url = re.sub(r"/agent/?$", "", url)
    if not url.endswith("/"):
        url += "/"
    return url


class DashboardCog(commands.Cog):
    """Cog providing dashboard link commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _get_reply_message(self) -> str:
        cfg = getattr(self.bot, "config", None)
        panel_enabled = getattr(cfg, "panel_enabled", False)
        panel_url = getattr(cfg, "panel_url", "")

        if not panel_enabled or not panel_url:
            return "Web UI is not enabled."

        dashboard_url = get_dashboard_url(panel_url)
        return f"🌐 **Web UI Dashboard**: {dashboard_url}"

    @app_commands.command(name="dashboard", description="Get the link to the Web UI dashboard")
    async def dashboard_slash(self, interaction: discord.Interaction):
        """Slash command for dashboard link (ephemeral)."""
        msg = self._get_reply_message()
        await interaction.response.send_message(msg, ephemeral=True)

    @commands.command(name="dashboard")
    async def dashboard_prefix(self, ctx: commands.Context):
        """Prefix command for dashboard link."""
        msg = self._get_reply_message()
        try:
            await ctx.author.send(msg)
            if ctx.guild:
                await ctx.reply("I've sent the Web UI link to your DMs!", delete_after=10)
        except discord.Forbidden:
            await ctx.reply(msg)


async def setup(bot: commands.Bot):
    await bot.add_cog(DashboardCog(bot))

