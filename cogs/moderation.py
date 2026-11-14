"""Moderation Cog: Administrative server protection with confirmation dialogues and audit embeds."""

import datetime
import logging
from typing import Optional, Union
import discord
from discord import app_commands
from discord.ext import commands

from embeds import error_embed, moderation_embed, success_embed, warning_embed
from ui import ConfirmView

logger = logging.getLogger("skillx.moderation")


class Moderation(commands.Cog, name="Moderation"):
    """Robust administrative moderation tools for Discord server communities."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _validate_hierarchy(
        self, moderator: discord.Member, target: discord.Member
    ) -> Optional[discord.Embed]:
        """
        Validates permission hierarchy between moderator, target, and the bot.
        Returns an error embed if the action is invalid, or None if permitted.
        """
        guild = moderator.guild
        me = guild.me

        if target.id == moderator.id:
            return error_embed("Invalid Target", "You cannot moderate yourself.")

        if target.id == guild.owner_id:
            return error_embed("Hierarchy Protection", "The server owner cannot be moderated.")

        if target.id == self.bot.user.id:
            return error_embed("Invalid Target", "I cannot moderate myself.")

        # Moderator hierarchy check (guild owner bypasses role check)
        if moderator.id != guild.owner_id and target.top_role >= moderator.top_role:
            return error_embed(
                "Hierarchy Protection",
                f"{target.mention} holds a role equal to or higher than your highest role.",
            )

        # Bot's own hierarchy check
        if me.top_role <= target.top_role:
            return error_embed(
                "Bot Hierarchy Error",
                f"My highest role (`{me.top_role.name}`) is lower than or equal to {target.mention}'s highest role.",
            )

        return None

    # ---------------------------------------------------------
    # KICK COMMAND
    # ---------------------------------------------------------

    async def _execute_kick(
        self,
        moderator: discord.Member,
        member: discord.Member,
        reason: str,
        send_confirm,
        edit_message,
        send_error,
    ):
        hierarchy_error = self._validate_hierarchy(moderator, member)
        if hierarchy_error:
            await send_error(hierarchy_error)
            return

        view = ConfirmView(moderator.id)
        confirm_embed = warning_embed(
            "Confirm Kick",
            f"Are you sure you want to kick **{member.display_name}** ({member.mention})?\n"
            f"**Reason:** {reason}",
        )
        await send_confirm(confirm_embed, view)
        await view.wait()

        if view.value is not True:
            await edit_message(
                embed=error_embed("Cancelled", f"Kick operation for {member.mention} was cancelled or timed out.")
            )
            return

        # Notify target via DM if possible
        try:
            await member.send(
                f"You were kicked from **{moderator.guild.name}**.\n**Reason:** {reason}"
            )
        except (discord.Forbidden, discord.HTTPException):
            pass

        try:
            await member.kick(reason=f"By {moderator} ({moderator.id}): {reason}")
            await edit_message(embed=moderation_embed("Kick", member, moderator, reason))
        except discord.Forbidden:
            await edit_message(embed=error_embed("Permission Denied", "Missing required Discord permission to kick."))
        except discord.HTTPException as exc:
            await edit_message(embed=error_embed("Kick Failed", str(exc)))

    @app_commands.command(name="kick", description="Kick a member from the server")
    @app_commands.describe(member="The member to kick", reason="Reason for the kick")
    @app_commands.guild_only()
    @app_commands.default_permissions(kick_members=True)
    @app_commands.checks.has_permissions(kick_members=True)
    @app_commands.checks.bot_has_permissions(kick_members=True)
    async def kick_slash(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: Optional[str] = "No reason provided",
    ):
        async def send_confirm(embed, view):
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            view.message = await interaction.original_response()

        async def edit_message(embed):
            await interaction.edit_original_response(embed=embed, view=None)

        async def send_error(embed):
            await interaction.response.send_message(embed=embed, ephemeral=True)

        await self._execute_kick(
            interaction.user, member, reason, send_confirm, edit_message, send_error
        )

    @commands.command(name="kick", help="Kick a member. Example: !kick @user Spamming")
    @commands.guild_only()
    @commands.has_permissions(kick_members=True)
    @commands.bot_has_permissions(kick_members=True)
    async def kick_prefix(
        self,
        ctx: commands.Context,
        member: discord.Member,
        *,
        reason: str = "No reason provided",
    ):
        holder = {}

        async def send_confirm(embed, view):
            msg = await ctx.reply(embed=embed, view=view, mention_author=False)
            view.message = msg
            holder["msg"] = msg

        async def edit_message(embed):
            if "msg" in holder:
                await holder["msg"].edit(embed=embed, view=None)

        async def send_error(embed):
            await ctx.reply(embed=embed, delete_after=10, mention_author=False)

        await self._execute_kick(
            ctx.author, member, reason, send_confirm, edit_message, send_error
        )

    # ---------------------------------------------------------
    # BAN COMMAND
    # ---------------------------------------------------------

    async def _execute_ban(
        self,
        moderator: discord.Member,
        member: discord.Member,
        reason: str,
        delete_days: int,
        send_confirm,
        edit_message,
        send_error,
    ):
        hierarchy_error = self._validate_hierarchy(moderator, member)
        if hierarchy_error:
            await send_error(hierarchy_error)
            return

        delete_days = max(0, min(7, delete_days))
        view = ConfirmView(moderator.id)
        confirm_embed = warning_embed(
            "Confirm Ban",
            f"Are you sure you want to ban **{member.display_name}** ({member.mention})?\n"
            f"**Reason:** {reason}\n"
            f"**Message Purge:** {delete_days} day(s)",
        )
        await send_confirm(confirm_embed, view)
        await view.wait()

        if view.value is not True:
            await edit_message(
                embed=error_embed("Cancelled", f"Ban operation for {member.mention} was cancelled or timed out.")
            )
            return

        # Direct message attempt before ban
        try:
            await member.send(
                f"You were banned from **{moderator.guild.name}**.\n**Reason:** {reason}"
            )
        except (discord.Forbidden, discord.HTTPException):
            pass

        try:
            await member.ban(
                reason=f"By {moderator} ({moderator.id}): {reason}",
                delete_message_days=delete_days,
            )
            await edit_message(
                embed=moderation_embed(
                    "Ban",
                    member,
                    moderator,
                    reason,
                    extra_fields={"Purged Messages": f"{delete_days} days"},
                )
            )
        except discord.Forbidden:
            await edit_message(embed=error_embed("Permission Denied", "Missing bot permissions to ban."))
        except discord.HTTPException as exc:
            await edit_message(embed=error_embed("Ban Failed", str(exc)))

    @app_commands.command(name="ban", description="Ban a member from the server")
    @app_commands.describe(
        member="The member to ban",
        reason="Reason for the ban",
        delete_days="Number of days of message history to delete (0–7)",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(ban_members=True)
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.checks.bot_has_permissions(ban_members=True)
    async def ban_slash(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: Optional[str] = "No reason provided",
        delete_days: Optional[int] = 0,
    ):
        async def send_confirm(embed, view):
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            view.message = await interaction.original_response()

        async def edit_message(embed):
            await interaction.edit_original_response(embed=embed, view=None)

        async def send_error(embed):
            await interaction.response.send_message(embed=embed, ephemeral=True)

        await self._execute_ban(
            interaction.user,
            member,
            reason,
            delete_days or 0,
            send_confirm,
            edit_message,
            send_error,
        )

    @commands.command(name="ban", help="Ban a member. Example: !ban @user Raiding")
    @commands.guild_only()
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def ban_prefix(
        self,
        ctx: commands.Context,
        member: discord.Member,
        *,
        reason: str = "No reason provided",
    ):
        holder = {}

        async def send_confirm(embed, view):
            msg = await ctx.reply(embed=embed, view=view, mention_author=False)
            view.message = msg
            holder["msg"] = msg

        async def edit_message(embed):
            if "msg" in holder:
                await holder["msg"].edit(embed=embed, view=None)

        async def send_error(embed):
            await ctx.reply(embed=embed, delete_after=10, mention_author=False)

        await self._execute_ban(
            ctx.author, member, reason, 0, send_confirm, edit_message, send_error
        )

    # ---------------------------------------------------------
    # TIMEOUT COMMAND
    # ---------------------------------------------------------

    @app_commands.command(name="timeout", description="Temporarily mute/timeout a member")
    @app_commands.describe(
        member="The member to timeout",
        minutes="Duration in minutes (1 to 40320 = 28 days)",
        reason="Reason for the timeout",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.checks.bot_has_permissions(moderate_members=True)
    async def timeout_slash(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        minutes: int,
        reason: Optional[str] = "No reason provided",
    ):
        hierarchy_error = self._validate_hierarchy(interaction.user, member)
        if hierarchy_error:
            await interaction.response.send_message(embed=hierarchy_error, ephemeral=True)
            return

        if not 1 <= minutes <= 40320:
            await interaction.response.send_message(
                embed=error_embed("Invalid Duration", "Timeout duration must be between 1 minute and 28 days (40,320 mins)."),
                ephemeral=True,
            )
            return

        duration = datetime.timedelta(minutes=minutes)
        try:
            await member.timeout(duration, reason=f"By {interaction.user}: {reason}")
            embed = moderation_embed(
                "Timeout",
                member,
                interaction.user,
                reason,
                extra_fields={"Duration": f"{minutes} minute(s)"},
            )
            await interaction.response.send_message(embed=embed)
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=error_embed("Permission Denied", "I lack the permission to timeout this member."),
                ephemeral=True,
            )
        except discord.HTTPException as exc:
            await interaction.response.send_message(
                embed=error_embed("Timeout Failed", str(exc)), ephemeral=True
            )

    @commands.command(name="timeout", aliases=["mute"], help="Timeout a member. Example: !timeout @user 10 Spam")
    @commands.guild_only()
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    async def timeout_prefix(
        self,
        ctx: commands.Context,
        member: discord.Member,
        minutes: int,
        *,
        reason: str = "No reason provided",
    ):
        hierarchy_error = self._validate_hierarchy(ctx.author, member)
        if hierarchy_error:
            await ctx.reply(embed=hierarchy_error, delete_after=10, mention_author=False)
            return

        if not 1 <= minutes <= 40320:
            await ctx.reply(
                embed=error_embed("Invalid Duration", "Timeout duration must be between 1 and 40,320 minutes."),
                delete_after=10,
                mention_author=False,
            )
            return

        duration = datetime.timedelta(minutes=minutes)
        try:
            await member.timeout(duration, reason=f"By {ctx.author}: {reason}")
            embed = moderation_embed(
                "Timeout",
                member,
                ctx.author,
                reason,
                extra_fields={"Duration": f"{minutes} minute(s)"},
            )
            await ctx.reply(embed=embed, mention_author=False)
        except discord.Forbidden:
            await ctx.reply(embed=error_embed("Permission Denied", "Missing bot permissions."), delete_after=10)
        except discord.HTTPException as exc:
            await ctx.reply(embed=error_embed("Timeout Failed", str(exc)), delete_after=10)

    # ---------------------------------------------------------
    # PURGE COMMAND
    # ---------------------------------------------------------

    async def _execute_purge(self, channel: discord.TextChannel, amount: int, respond):
        if not 1 <= amount <= 100:
            await respond(error_embed("Invalid Amount", "Please specify a number between 1 and 100."))
            return

        try:
            # Purge non-pinned messages
            deleted = await channel.purge(limit=amount, check=lambda m: not m.pinned)
            await respond(
                success_embed(
                    "Messages Purged",
                    f"Successfully deleted **{len(deleted)}** message(s) (preserved pinned messages).",
                ),
                delete_after=6,
            )
        except discord.Forbidden:
            await respond(error_embed("Permission Denied", "Missing permission to Manage Messages."))
        except discord.HTTPException as exc:
            # Typically happens if messages older than 14 days were encountered
            await respond(
                error_embed(
                    "Purge Failed",
                    "Discord cannot bulk-delete messages older than 14 days, or an API error occurred.",
                )
            )

    @app_commands.command(name="purge", description="Bulk delete recent messages in the channel")
    @app_commands.describe(amount="Number of messages to delete (1–100)")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.checks.bot_has_permissions(manage_messages=True)
    async def purge_slash(self, interaction: discord.Interaction, amount: int):
        await interaction.response.defer(ephemeral=True)

        async def respond(embed, delete_after=None):
            await interaction.followup.send(embed=embed, ephemeral=True)

        await self._execute_purge(interaction.channel, amount, respond)

    @commands.command(
        name="purge",
        aliases=["clear", "clean"],
        help="Bulk delete recent messages. Example: !purge 15",
    )
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def purge_prefix(self, ctx: commands.Context, amount: int):
        # Delete invoking command message first
        try:
            await ctx.message.delete()
        except (discord.Forbidden, discord.HTTPException):
            pass

        async def respond(embed, delete_after=None):
            await ctx.channel.send(embed=embed, delete_after=delete_after)

        await self._execute_purge(ctx.channel, amount, respond)


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
