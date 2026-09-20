import logging
from typing import Optional

import discord

logger = logging.getLogger(__name__)

class VoiceManager:
    """Manages voice channel connections for the bot."""
    
    def __init__(self, bot: discord.Client):
        self.bot = bot

    async def connect(self, member: discord.Member) -> discord.VoiceClient:
        """Connects to the voice channel of the given member."""
        if not member.voice or not member.voice.channel:
            raise ValueError("Member is not connected to a voice channel.")
        
        channel = member.voice.channel
        guild = member.guild
        voice_client: Optional[discord.VoiceClient] = guild.voice_client

        if voice_client is not None:
            if voice_client.channel.id != channel.id:
                logger.info(f"Moving voice channel from '{voice_client.channel.name}' to '{channel.name}' in guild '{guild.name}' (ID: {guild.id})")
                await voice_client.move_to(channel)
        else:
            logger.info(f"Connecting to voice channel '{channel.name}' in guild '{guild.name}' (ID: {guild.id})")
            voice_client = await channel.connect(self_deaf=True)
            
        return voice_client

    async def disconnect(self, guild: discord.Guild):
        """Disconnects from the voice channel in the specified guild."""
        voice_client: Optional[discord.VoiceClient] = guild.voice_client
        if voice_client is not None and voice_client.is_connected():
            ch_name = voice_client.channel.name if voice_client.channel else "unknown"
            logger.info(f"Disconnecting from voice channel '{ch_name}' in guild '{guild.name}' (ID: {guild.id})")
            await voice_client.disconnect(force=True)

    async def ensure_connected(self, interaction: discord.Interaction) -> Optional[discord.VoiceClient]:
        """Ensures the bot is connected to the same voice channel as the interacting user."""
        if not interaction.user or not isinstance(interaction.user, discord.Member) or not interaction.user.voice:
            await interaction.response.send_message("You must be in a voice channel to use this command.", ephemeral=True)
            return None
            
        try:
            vc = await self.connect(interaction.user)
            return vc
        except discord.Forbidden:
            logger.warning(f"Permission denied joining voice channel for user {interaction.user} in guild {interaction.guild}")
            await interaction.response.send_message("I don't have permission to join your voice channel.", ephemeral=True)
            return None
        except Exception as e:
            logger.error(f"Error connecting to voice: {e}", exc_info=True)
            await interaction.response.send_message(f"Failed to connect to voice channel: {e}", ephemeral=True)
            return None
