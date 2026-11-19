"""Server Logs Cog: Audit logging system that logs server events to a designated channel."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from embeds import (
    BRAND_COLOR,
    AI_COLOR,
    SUCCESS,
    ERROR,
    WARNING,
    INFO,
    base_embed,
    success_embed,
    error_embed,
    info_embed,
    warning_embed,
)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
LOG_CHANNELS_FILE = DATA_DIR / "log_channels.json"

# Embed colours for different event types
COLOR_DELETE = 0xE74C3C   # Red
COLOR_EDIT = 0xF1C40F     # Yellow
COLOR_JOIN = 0x2ECC71     # Green
COLOR_LEAVE = 0xE74C3C    # Red
COLOR_BAN = 0x992D22      # Dark Red
COLOR_UNBAN = 0x2ECC71    # Green
COLOR_VOICE = 0x3498DB    # Blue
COLOR_ROLE = 0x9B59B6     # Purple


class ServerLogs(commands.Cog, name="Server Logs"):
    """Audit logging system that logs server events to a designated channel."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.log_channels: dict[str, int] = {}  # guild_id (str) -> channel_id
        self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if LOG_CHANNELS_FILE.exists():
            try:
                with open(LOG_CHANNELS_FILE, "r", encoding="utf-8") as f:
                    self.log_channels = json.load(f)
            except (json.JSONDecodeError, OSError):
                self.log_channels = {}
        else:
            self.log_channels = {}

    def _save(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG_CHANNELS_FILE, "w", encoding="utf-8") as f:
            json.dump(self.log_channels, f, indent=2)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_log_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        """Retrieve the configured log channel for a guild."""
        channel_id = self.log_channels.get(str(guild.id))
        if channel_id is None:
            return None
        channel = guild.get_channel(channel_id)
        if isinstance(channel, discord.TextChannel):
            return channel
        return None

    async def _send_log(self, guild: discord.Guild, embed: discord.Embed) -> None:
        """Send an embed to the guild's log channel, if configured."""
        channel = self._get_log_channel(guild)
        if channel is None:
            return
        try:
            await channel.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException):
            pass

    # ------------------------------------------------------------------
    # /setlogchannel
    # ------------------------------------------------------------------

    @app_commands.command(name="setlogchannel", description="Set the channel for server audit logs")
    @app_commands.describe(channel="The text channel to send logs to")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def setlogchannel_slash(self, interaction: discord.Interaction, channel: discord.TextChannel):
        self.log_channels[str(interaction.guild.id)] = channel.id
        self._save()
        await interaction.response.send_message(
            embed=success_embed(
                "Log Channel Set",
                f"Server logs will now be sent to {channel.mention}.",
            )
        )

    @commands.command(name="setlogchannel", help="Set the logging channel. Example: !setlogchannel #logs")
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def setlogchannel_prefix(self, ctx: commands.Context, channel: discord.TextChannel):
        self.log_channels[str(ctx.guild.id)] = channel.id
        self._save()
        await ctx.reply(
            embed=success_embed(
                "Log Channel Set",
                f"Server logs will now be sent to {channel.mention}.",
            ),
            mention_author=False,
        )

    # ------------------------------------------------------------------
    # /clearlogchannel
    # ------------------------------------------------------------------

    @app_commands.command(name="clearlogchannel", description="Remove the server logging channel")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def clearlogchannel_slash(self, interaction: discord.Interaction):
        guild_key = str(interaction.guild.id)
        if guild_key in self.log_channels:
            del self.log_channels[guild_key]
            self._save()
            await interaction.response.send_message(
                embed=success_embed("Log Channel Cleared", "Server logging has been disabled.")
            )
        else:
            await interaction.response.send_message(
                embed=warning_embed("No Log Channel", "No logging channel was configured for this server."),
                ephemeral=True,
            )

    @commands.command(name="clearlogchannel", help="Remove the server logging channel.")
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def clearlogchannel_prefix(self, ctx: commands.Context):
        guild_key = str(ctx.guild.id)
        if guild_key in self.log_channels:
            del self.log_channels[guild_key]
            self._save()
            await ctx.reply(
                embed=success_embed("Log Channel Cleared", "Server logging has been disabled."),
                mention_author=False,
            )
        else:
            await ctx.reply(
                embed=warning_embed("No Log Channel", "No logging channel was configured."),
                mention_author=False,
            )

    # ------------------------------------------------------------------
    # Event Listeners
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        if not message.guild or message.author.bot:
            return

        embed = base_embed(
            title="🗑️ Message Deleted",
            color=COLOR_DELETE,
            user=message.author,
            footer_text=f"Author ID: {message.author.id} • SkillX Logs",
        )
        embed.add_field(name="Author", value=message.author.mention, inline=True)
        embed.add_field(name="Channel", value=f"{message.channel.mention}", inline=True)
        content = message.content or "*No text content*"
        if len(content) > 1024:
            content = content[:1021] + "..."
        embed.add_field(name="Content", value=content, inline=False)

        if message.attachments:
            att_names = ", ".join(a.filename for a in message.attachments[:5])
            embed.add_field(name="Attachments", value=att_names, inline=False)

        await self._send_log(message.guild, embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        if not before.guild or before.author.bot:
            return
        if before.content == after.content:
            return

        embed = base_embed(
            title="✏️ Message Edited",
            color=COLOR_EDIT,
            user=before.author,
            footer_text=f"Author ID: {before.author.id} • SkillX Logs",
        )
        embed.add_field(name="Author", value=before.author.mention, inline=True)
        embed.add_field(name="Channel", value=before.channel.mention, inline=True)
        embed.add_field(
            name="Jump to Message",
            value=f"[Click here]({after.jump_url})",
            inline=True,
        )

        old_content = before.content or "*Empty*"
        new_content = after.content or "*Empty*"
        if len(old_content) > 1024:
            old_content = old_content[:1021] + "..."
        if len(new_content) > 1024:
            new_content = new_content[:1021] + "..."

        embed.add_field(name="Before", value=old_content, inline=False)
        embed.add_field(name="After", value=new_content, inline=False)

        await self._send_log(before.guild, embed)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        created_at = member.created_at
        now = datetime.now(timezone.utc)
        age = now - created_at
        days = age.days

        if days < 1:
            age_str = "Less than a day"
        elif days < 30:
            age_str = f"{days} day{'s' if days != 1 else ''}"
        elif days < 365:
            months = days // 30
            age_str = f"{months} month{'s' if months != 1 else ''}"
        else:
            years = days // 365
            age_str = f"{years} year{'s' if years != 1 else ''}"

        embed = base_embed(
            title="📥 Member Joined",
            description=f"{member.mention} has joined the server!",
            color=COLOR_JOIN,
            user=member,
            footer_text=f"Member ID: {member.id} • Members: {member.guild.member_count} • SkillX Logs",
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Username", value=str(member), inline=True)
        embed.add_field(name="Account Created", value=f"<t:{int(created_at.timestamp())}:R>", inline=True)
        embed.add_field(name="Account Age", value=age_str, inline=True)

        # Flag new accounts
        if days < 7:
            embed.add_field(
                name="⚠️ New Account Warning",
                value="This account is less than 7 days old.",
                inline=False,
            )

        await self._send_log(member.guild, embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        roles = [r.mention for r in member.roles if r != member.guild.default_role]
        roles_str = ", ".join(roles[:20]) if roles else "No special roles"

        embed = base_embed(
            title="📤 Member Left",
            description=f"**{member.display_name}** ({member}) has left the server.",
            color=COLOR_LEAVE,
            user=member,
            footer_text=f"Member ID: {member.id} • Members: {member.guild.member_count} • SkillX Logs",
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        joined = member.joined_at
        if joined:
            embed.add_field(name="Joined Server", value=f"<t:{int(joined.timestamp())}:R>", inline=True)
        embed.add_field(name="Roles", value=roles_str[:1024], inline=False)

        await self._send_log(member.guild, embed)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User) -> None:
        embed = base_embed(
            title="🔨 Member Banned",
            description=f"**{user}** has been banned from the server.",
            color=COLOR_BAN,
            user=user,
            footer_text=f"User ID: {user.id} • SkillX Logs",
        )
        embed.set_thumbnail(url=user.display_avatar.url)

        # Try to get the ban reason from audit log
        try:
            async for entry in guild.audit_logs(action=discord.AuditLogAction.ban, limit=5):
                if entry.target and entry.target.id == user.id:
                    if entry.user:
                        embed.add_field(name="Banned by", value=entry.user.mention, inline=True)
                    embed.add_field(name="Reason", value=entry.reason or "No reason provided", inline=True)
                    break
        except (discord.Forbidden, discord.HTTPException):
            pass

        await self._send_log(guild, embed)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User) -> None:
        embed = base_embed(
            title="✅ Member Unbanned",
            description=f"**{user}** has been unbanned from the server.",
            color=COLOR_UNBAN,
            user=user,
            footer_text=f"User ID: {user.id} • SkillX Logs",
        )
        embed.set_thumbnail(url=user.display_avatar.url)

        try:
            async for entry in guild.audit_logs(action=discord.AuditLogAction.unban, limit=5):
                if entry.target and entry.target.id == user.id:
                    if entry.user:
                        embed.add_field(name="Unbanned by", value=entry.user.mention, inline=True)
                    break
        except (discord.Forbidden, discord.HTTPException):
            pass

        await self._send_log(guild, embed)

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        if before.channel == after.channel:
            return  # No channel change (e.g. mute/deafen only)

        if before.channel is None and after.channel is not None:
            # Joined a voice channel
            embed = base_embed(
                title="🔊 Voice Channel Joined",
                description=f"{member.mention} joined **{after.channel.name}**",
                color=COLOR_VOICE,
                user=member,
                footer_text=f"Member ID: {member.id} • SkillX Logs",
            )
        elif before.channel is not None and after.channel is None:
            # Left a voice channel
            embed = base_embed(
                title="🔇 Voice Channel Left",
                description=f"{member.mention} left **{before.channel.name}**",
                color=COLOR_VOICE,
                user=member,
                footer_text=f"Member ID: {member.id} • SkillX Logs",
            )
        else:
            # Moved between voice channels
            embed = base_embed(
                title="🔀 Voice Channel Moved",
                description=(
                    f"{member.mention} moved from **{before.channel.name}** "
                    f"to **{after.channel.name}**"
                ),
                color=COLOR_VOICE,
                user=member,
                footer_text=f"Member ID: {member.id} • SkillX Logs",
            )

        await self._send_log(member.guild, embed)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        # Role changes
        added_roles = set(after.roles) - set(before.roles)
        removed_roles = set(before.roles) - set(after.roles)

        if added_roles or removed_roles:
            embed = base_embed(
                title="🛡️ Roles Updated",
                description=f"Roles changed for {after.mention}",
                color=COLOR_ROLE,
                user=after,
                footer_text=f"Member ID: {after.id} • SkillX Logs",
            )
            if added_roles:
                role_mentions = ", ".join(r.mention for r in added_roles)
                embed.add_field(name="➕ Roles Added", value=role_mentions[:1024], inline=False)
            if removed_roles:
                role_mentions = ", ".join(r.mention for r in removed_roles)
                embed.add_field(name="➖ Roles Removed", value=role_mentions[:1024], inline=False)

            await self._send_log(after.guild, embed)

        # Nickname changes
        if before.nick != after.nick:
            embed = base_embed(
                title="📝 Nickname Changed",
                description=f"Nickname updated for {after.mention}",
                color=COLOR_ROLE,
                user=after,
                footer_text=f"Member ID: {after.id} • SkillX Logs",
            )
            embed.add_field(name="Before", value=before.nick or "*No nickname*", inline=True)
            embed.add_field(name="After", value=after.nick or "*No nickname*", inline=True)

            await self._send_log(after.guild, embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(ServerLogs(bot))
