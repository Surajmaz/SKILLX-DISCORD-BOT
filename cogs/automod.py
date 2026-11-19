"""AutoMod & Infraction Cog: Server security, link filters, mass-mention prevention, and warnings."""

import asyncio
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import re
import time
from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands

from embeds import base_embed, error_embed, moderation_embed, success_embed, warning_embed

logger = logging.getLogger("skillx.automod")
INFRACTIONS_FILE = Path(__file__).parent.parent / "data" / "infractions.json"


class AutoMod(commands.Cog, name="AutoMod"):
    """Automated security filters, channel locks, slowmode, and member infraction management."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.infractions: dict[str, list[dict]] = self._load_infractions()
        # Spam tracker: (guild_id, user_id) -> list of timestamps
        self.spam_tracker: dict[tuple[int, int], list[float]] = {}
        # Discord invite regex
        self.invite_regex = re.compile(
            r"(?:https?://)?(?:www\.)?(?:discord\.(?:gg|io|me|li)|discord(?:app)?\.com/invite)/[a-zA-Z0-9]+",
            re.IGNORECASE,
        )

    def _load_infractions(self) -> dict[str, list[dict]]:
        if not INFRACTIONS_FILE.exists():
            return {}
        try:
            return json.loads(INFRACTIONS_FILE.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Failed to load infractions: %s. Starting fresh.", exc)
            return {}

    def _save_infractions(self) -> None:
        INFRACTIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
        try:
            INFRACTIONS_FILE.write_text(json.dumps(self.infractions, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.error("Failed to persist infractions: %s", exc)

    def add_warning(self, guild_id: int, user_id: int, moderator_id: int, reason: str) -> int:
        key = f"{guild_id}_{user_id}"
        if key not in self.infractions:
            self.infractions[key] = []
        warning_entry = {
            "id": len(self.infractions[key]) + 1,
            "moderator_id": moderator_id,
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.infractions[key].append(warning_entry)
        self._save_infractions()
        return len(self.infractions[key])

    def get_warnings(self, guild_id: int, user_id: int) -> list[dict]:
        key = f"{guild_id}_{user_id}"
        return self.infractions.get(key, [])

    def clear_warnings(self, guild_id: int, user_id: int) -> int:
        key = f"{guild_id}_{user_id}"
        count = len(self.infractions.pop(key, []))
        if count > 0:
            self._save_infractions()
        return count

    # ---------------------------------------------------------
    # AUTOMOD LISTENER
    # ---------------------------------------------------------

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild or not isinstance(message.author, discord.Member):
            return

        # Exempt users with Manage Messages or Administrator
        perms = message.channel.permissions_for(message.author)
        if perms.manage_messages or perms.administrator:
            return

        now = time.monotonic()
        key = (message.guild.id, message.author.id)

        # 1. Anti-Spam (Flood Detection: >5 messages in 3 seconds)
        timestamps = [t for t in self.spam_tracker.get(key, []) if now - t < 3.0]
        timestamps.append(now)
        self.spam_tracker[key] = timestamps

        if len(timestamps) >= 5:
            try:
                await message.delete()
                await message.channel.send(
                    f"⚠️ {message.author.mention}, please slow down! Excessive message spamming detected.",
                    delete_after=5,
                )
            except (discord.Forbidden, discord.HTTPException):
                pass
            return

        # 2. Anti-Invite Link Filter
        if self.invite_regex.search(message.content):
            try:
                await message.delete()
                warn_embed = warning_embed(
                    "Invite Links Blocked",
                    f"{message.author.mention}, posting unauthorized Discord invite links is forbidden in this server.",
                )
                await message.channel.send(embed=warn_embed, delete_after=7)
                self.add_warning(message.guild.id, message.author.id, self.bot.user.id, "Automated: Discord Invite Link")
            except (discord.Forbidden, discord.HTTPException):
                pass
            return

        # 3. Mass Mention Filter (>5 mentions in a single message)
        if len(message.mentions) + len(message.role_mentions) > 5:
            try:
                await message.delete()
                await message.channel.send(
                    f"⚠️ {message.author.mention}, mass mention spam (>5 pings) is strictly prohibited.",
                    delete_after=7,
                )
                self.add_warning(message.guild.id, message.author.id, self.bot.user.id, "Automated: Mass Mention Spam")
            except (discord.Forbidden, discord.HTTPException):
                pass
            return

    # ---------------------------------------------------------
    # WARN COMMANDS
    # ---------------------------------------------------------

    @app_commands.command(name="warn", description="Issue a formal infraction warning to a member")
    @app_commands.describe(member="Member to warn", reason="Reason for the warning")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.checks.has_permissions(manage_messages=True)
    async def warn_slash(
        self, interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = "No reason provided"
    ):
        if member.bot or member.id == interaction.user.id:
            await interaction.response.send_message(
                embed=error_embed("Invalid Target", "You cannot warn bots or yourself."), ephemeral=True
            )
            return

        count = self.add_warning(interaction.guild_id, member.id, interaction.user.id, reason)
        embed = moderation_embed(
            "Warning Issued",
            member,
            interaction.user,
            reason,
            extra_fields={"Total Warnings": f"`{count}`"},
        )
        await interaction.response.send_message(embed=embed)

        try:
            await member.send(
                f"⚠️ You received a warning in **{interaction.guild.name}**.\n**Reason:** {reason}\n**Total Offenses:** {count}"
            )
        except (discord.Forbidden, discord.HTTPException):
            pass

    @commands.command(name="warn", help="Warn a member. Example: !warn @user Spamming")
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def warn_prefix(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
        if member.bot or member.id == ctx.author.id:
            await ctx.reply(embed=error_embed("Invalid Target", "Cannot warn bots or yourself."), delete_after=10)
            return

        count = self.add_warning(ctx.guild.id, member.id, ctx.author.id, reason)
        embed = moderation_embed(
            "Warning Issued",
            member,
            ctx.author,
            reason,
            extra_fields={"Total Warnings": f"`{count}`"},
        )
        await ctx.reply(embed=embed, mention_author=False)

    @app_commands.command(name="warnings", description="View all recorded infractions for a member")
    @app_commands.describe(member="Member whose history to inspect")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.checks.has_permissions(manage_messages=True)
    async def warnings_slash(self, interaction: discord.Interaction, member: discord.Member):
        warns = self.get_warnings(interaction.guild_id, member.id)
        if not warns:
            await interaction.response.send_message(
                embed=success_embed("Clean Record", f"No infractions on record for **{member.display_name}**."),
                ephemeral=True,
            )
            return

        embed = base_embed(
            title=f"📋 Infraction History: {member.display_name}",
            color=0xF1C40F,
            user=member,
            footer_text=f"Total Infractions: {len(warns)}",
        )
        for w in warns[-10:]:
            mod_mention = f"<@{w['moderator_id']}>"
            embed.add_field(
                name=f"Case #{w['id']}",
                value=f"**Reason:** {w['reason']}\n**Issued By:** {mod_mention}\n**Date:** <t:{int(datetime.fromisoformat(w['timestamp']).timestamp())}:d>",
                inline=False,
            )
        await interaction.response.send_message(embed=embed)

    @commands.command(name="warnings", aliases=["warns", "infractions"], help="View user warnings. Example: !warnings @user")
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def warnings_prefix(self, ctx: commands.Context, member: discord.Member):
        warns = self.get_warnings(ctx.guild.id, member.id)
        if not warns:
            await ctx.reply(
                embed=success_embed("Clean Record", f"No infractions found for **{member.display_name}**."),
                delete_after=10,
                mention_author=False,
            )
            return

        embed = base_embed(
            title=f"📋 Infraction History: {member.display_name}",
            color=0xF1C40F,
            user=member,
            footer_text=f"Total Infractions: {len(warns)}",
        )
        for w in warns[-10:]:
            mod_mention = f"<@{w['moderator_id']}>"
            embed.add_field(
                name=f"Case #{w['id']}",
                value=f"**Reason:** {w['reason']}\n**Issued By:** {mod_mention}\n**Date:** <t:{int(datetime.fromisoformat(w['timestamp']).timestamp())}:d>",
                inline=False,
            )
        await ctx.reply(embed=embed, mention_author=False)

    @app_commands.command(name="clearwarns", description="Clear all recorded warnings for a member")
    @app_commands.describe(member="Member whose warnings to wipe")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def clearwarns_slash(self, interaction: discord.Interaction, member: discord.Member):
        count = self.clear_warnings(interaction.guild_id, member.id)
        embed = success_embed(
            "Warnings Cleared",
            f"Successfully cleared **{count}** warning(s) for {member.mention}.",
        )
        await interaction.response.send_message(embed=embed)

    @commands.command(name="clearwarns", help="Clear warnings. Example: !clearwarns @user")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def clearwarns_prefix(self, ctx: commands.Context, member: discord.Member):
        count = self.clear_warnings(ctx.guild.id, member.id)
        embed = success_embed(
            "Warnings Cleared",
            f"Successfully cleared **{count}** warning(s) for {member.mention}.",
        )
        await ctx.reply(embed=embed, mention_author=False)

    # ---------------------------------------------------------
    # CHANNEL LOCK & SLOWMODE
    # ---------------------------------------------------------

    @app_commands.command(name="lock", description="Lockdown a channel to prevent member messages")
    @app_commands.describe(channel="Channel to lock (defaults to current)", reason="Reason for lockdown")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_channels=True)
    @app_commands.checks.has_permissions(manage_channels=True)
    async def lock_slash(
        self,
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel] = None,
        reason: Optional[str] = "Server Lockdown",
    ):
        target_ch = channel or interaction.channel
        default_role = interaction.guild.default_role
        try:
            await target_ch.set_permissions(default_role, send_messages=False, reason=reason)
            embed = error_embed(
                "🔒 Channel Locked",
                f"**{target_ch.mention}** has been locked down by {interaction.user.mention}.\n**Reason:** {reason}",
            )
            await interaction.response.send_message(embed=embed)
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=error_embed("Permission Denied", "Missing Manage Channels permission."), ephemeral=True
            )

    @commands.command(name="lock", help="Lock current channel. Example: !lock Raid in progress")
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    async def lock_prefix(self, ctx: commands.Context, *, reason: str = "Server Lockdown"):
        default_role = ctx.guild.default_role
        try:
            await ctx.channel.set_permissions(default_role, send_messages=False, reason=reason)
            embed = error_embed(
                "🔒 Channel Locked",
                f"**{ctx.channel.mention}** has been locked down by {ctx.author.mention}.\n**Reason:** {reason}",
            )
            await ctx.reply(embed=embed, mention_author=False)
        except discord.Forbidden:
            await ctx.reply(embed=error_embed("Permission Denied", "Missing bot permissions."), delete_after=10)

    @app_commands.command(name="unlock", description="Unlock a previously locked channel")
    @app_commands.describe(channel="Channel to unlock (defaults to current)")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_channels=True)
    @app_commands.checks.has_permissions(manage_channels=True)
    async def unlock_slash(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
        target_ch = channel or interaction.channel
        default_role = interaction.guild.default_role
        try:
            await target_ch.set_permissions(default_role, send_messages=None)
            embed = success_embed(
                "🔓 Channel Unlocked",
                f"**{target_ch.mention}** is now open for messages.",
            )
            await interaction.response.send_message(embed=embed)
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=error_embed("Permission Denied", "Missing Manage Channels permission."), ephemeral=True
            )

    @commands.command(name="unlock", help="Unlock channel. Example: !unlock")
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    async def unlock_prefix(self, ctx: commands.Context):
        default_role = ctx.guild.default_role
        try:
            await ctx.channel.set_permissions(default_role, send_messages=None)
            embed = success_embed(
                "🔓 Channel Unlocked",
                f"**{ctx.channel.mention}** is now open for messages.",
            )
            await ctx.reply(embed=embed, mention_author=False)
        except discord.Forbidden:
            await ctx.reply(embed=error_embed("Permission Denied", "Missing bot permissions."), delete_after=10)

    @app_commands.command(name="slowmode", description="Set channel slowmode message delay")
    @app_commands.describe(seconds="Slowmode duration in seconds (0 to 21600)")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_channels=True)
    @app_commands.checks.has_permissions(manage_channels=True)
    async def slowmode_slash(self, interaction: discord.Interaction, seconds: int):
        if not 0 <= seconds <= 21600:
            await interaction.response.send_message(
                embed=error_embed("Invalid Delay", "Slowmode delay must be between 0 and 21,600 seconds (6 hours)."),
                ephemeral=True,
            )
            return

        try:
            await interaction.channel.edit(slowmode_delay=seconds)
            status_text = "disabled" if seconds == 0 else f"set to **{seconds}s**"
            embed = success_embed("Slowmode Updated", f"Channel slowmode is now {status_text}.")
            await interaction.response.send_message(embed=embed)
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=error_embed("Permission Denied", "Missing Manage Channels permission."), ephemeral=True
            )

    @commands.command(name="slowmode", help="Set slowmode in seconds. Example: !slowmode 5")
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    async def slowmode_prefix(self, ctx: commands.Context, seconds: int):
        if not 0 <= seconds <= 21600:
            await ctx.reply(embed=error_embed("Invalid Delay", "Must be 0 to 21600 seconds."), delete_after=10)
            return

        try:
            await ctx.channel.edit(slowmode_delay=seconds)
            status_text = "disabled" if seconds == 0 else f"set to **{seconds}s**"
            embed = success_embed("Slowmode Updated", f"Channel slowmode is now {status_text}.")
            await ctx.reply(embed=embed, mention_author=False)
        except discord.Forbidden:
            await ctx.reply(embed=error_embed("Permission Denied", "Missing bot permissions."), delete_after=10)


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoMod(bot))
