import discord
from discord import app_commands
from enum import IntEnum
import logging
from typing import Any, Optional, Dict

logger = logging.getLogger(__name__)

class PermissionLevel(IntEnum):
    USER = 0
    DJ = 1
    ADMIN = 2

# Define required permissions for various commands
COMMAND_PERMISSIONS: Dict[str, PermissionLevel] = {
    "play": PermissionLevel.USER,
    "pause": PermissionLevel.DJ,
    "resume": PermissionLevel.DJ,
    "stop": PermissionLevel.DJ,
    "skip": PermissionLevel.DJ,
    "previous": PermissionLevel.DJ,
    "volume": PermissionLevel.DJ,
    "seek": PermissionLevel.DJ,
    "restart": PermissionLevel.DJ,
    "shuffle": PermissionLevel.DJ,
    "loop": PermissionLevel.DJ,
    "nowplaying": PermissionLevel.USER,
    "next": PermissionLevel.USER,
    "history": PermissionLevel.USER,
    "join": PermissionLevel.USER,
    "leave": PermissionLevel.DJ,
    "queue": PermissionLevel.USER,
    "playlist": PermissionLevel.USER,
    "youtube": PermissionLevel.USER,
    "about": PermissionLevel.USER,
    "help": PermissionLevel.USER,
    "ping": PermissionLevel.USER,
}

def get_user_permission(member: discord.Member, dj_role_name: str = "DJ") -> PermissionLevel:
    """Determine the permission level of a user based on roles/permissions."""
    if member.guild_permissions.administrator:
        return PermissionLevel.ADMIN
        
    for role in member.roles:
        if role.name.lower() == dj_role_name.lower():
            return PermissionLevel.DJ
            
    return PermissionLevel.USER

def require_permission(level: PermissionLevel):
    """Decorator for app_commands to require a specific permission level."""
    async def predicate(interaction: discord.Interaction) -> bool:
        if not isinstance(interaction.user, discord.Member):
            return False
            
        dj_role = getattr(interaction.client, "config", None)
        dj_role_name = dj_role.dj_role_name if dj_role else "DJ"
        
        user_level = get_user_permission(interaction.user, dj_role_name)
        if user_level >= level:
            return True
            
        # If they don't have permission, we raise an error which should be caught by error handler
        raise app_commands.MissingPermissions([f"Requires {level.name} level"])
        
    return app_commands.check(predicate)

def check_command_channel(interaction: discord.Interaction, channel_id: Optional[int]) -> bool:
    """Check if the command was used in the allowed channel."""
    if not channel_id:
        return True
    return interaction.channel_id == channel_id

def check_prefix_permission(ctx: Any, level: PermissionLevel) -> bool:
    """Check if the prefix command author has the required permission level."""
    if not isinstance(ctx.author, discord.Member):
        return False
    dj_role = getattr(ctx.bot, "config", None)
    dj_role_name = dj_role.dj_role_name if dj_role else "DJ"
    user_level = get_user_permission(ctx.author, dj_role_name)
    return user_level >= level

def check_prefix_channel(ctx: Any) -> bool:
    """Check if the prefix command was invoked in the designated command channel."""
    config = getattr(ctx.bot, "config", None)
    channel_id = getattr(config, "command_channel_id", None)
    if not channel_id:
        return True
    return ctx.channel.id == channel_id

def require_prefix_permission(level: PermissionLevel):
    """Decorator for prefix commands to require a specific permission level."""
    from discord.ext import commands
    async def predicate(ctx: commands.Context) -> bool:
        if check_prefix_permission(ctx, level):
            return True
        raise commands.CheckFailure(f"You need **{level.name}** permissions to use this command.")
    return commands.check(predicate)

def is_in_prefix_command_channel():
    """Decorator for prefix commands to check command channel."""
    from discord.ext import commands
    async def predicate(ctx: commands.Context) -> bool:
        return check_prefix_channel(ctx)
    return commands.check(predicate)

async def permission_error_handler(interaction: discord.Interaction, required_level: PermissionLevel):
    """Send an error embed when a user lacks permissions."""
    embed = discord.Embed(
        title="Permission Denied",
        description=f"You need **{required_level.name}** permissions to use this command.",
        color=discord.Color.red()
    )
    if interaction.response.is_done():
        await interaction.followup.send(embed=embed, ephemeral=True)
    else:
        await interaction.response.send_message(embed=embed, ephemeral=True)
