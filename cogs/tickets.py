"""Tickets Cog: Channel-based support ticket system with persistent views."""

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from embeds import base_embed, success_embed, error_embed, info_embed, BRAND_COLOR, SUCCESS, ERROR

logger = logging.getLogger("skillx.tickets")

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CONFIG_FILE = DATA_DIR / "ticket_config.json"


# ---------------------------------------------------------------------------
# Persistent Views
# ---------------------------------------------------------------------------

class TicketCloseView(discord.ui.View):
    """Persistent view with a close-ticket button."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Close Ticket",
        emoji="🔒",
        style=discord.ButtonStyle.danger,
        custom_id="skillx_close_ticket",
    )
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Confirmation prompt
        confirm_view = _ConfirmCloseView(interaction.user.id)
        await interaction.response.send_message(
            embed=info_embed("Close Ticket", "Are you sure you want to close this ticket?"),
            view=confirm_view,
            ephemeral=True,
        )
        await confirm_view.wait()

        if not confirm_view.confirmed:
            return

        channel = interaction.channel
        guild = interaction.guild
        if channel is None or guild is None:
            return

        # Try to find the ticket opener from the channel topic
        opener_id = _parse_opener_from_topic(channel)

        # Generate transcript — last 100 messages
        transcript_lines: list[str] = []
        transcript_lines.append(f"Transcript for #{channel.name} in {guild.name}")
        transcript_lines.append(f"Closed by: {interaction.user} at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
        transcript_lines.append("-" * 60)

        messages: list[discord.Message] = []
        try:
            async for msg in channel.history(limit=100, oldest_first=True):
                messages.append(msg)
        except discord.Forbidden:
            pass

        for msg in messages:
            ts = msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
            content = msg.content or "[embed/attachment]"
            transcript_lines.append(f"[{ts}] {msg.author}: {content}")

        transcript_text = "\n".join(transcript_lines)

        # DM transcript to the opener
        if opener_id:
            try:
                opener = await guild.fetch_member(opener_id)
                file = discord.File(
                    fp=__import__("io").BytesIO(transcript_text.encode()),
                    filename=f"transcript-{channel.name}.txt",
                )
                await opener.send(
                    embed=info_embed(
                        "Ticket Closed",
                        f"Your ticket **#{channel.name}** in **{guild.name}** has been closed.\nTranscript attached below.",
                    ),
                    file=file,
                )
            except (discord.Forbidden, discord.HTTPException, discord.NotFound):
                logger.warning("Could not DM transcript to user %s", opener_id)

        # Notify the channel and delete after delay
        await channel.send(
            embed=base_embed(
                "🔒 Ticket Closing",
                "This channel will be deleted in **5 seconds**...",
                color=ERROR,
            )
        )
        await asyncio.sleep(5)
        try:
            await channel.delete(reason="Ticket closed")
        except discord.HTTPException as exc:
            logger.error("Failed to delete ticket channel: %s", exc)


class _ConfirmCloseView(discord.ui.View):
    """Ephemeral confirmation for ticket closure."""

    def __init__(self, author_id: int):
        super().__init__(timeout=30)
        self.author_id = author_id
        self.confirmed = False

    @discord.ui.button(label="Confirm Close", style=discord.ButtonStyle.danger, emoji="✅")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                embed=error_embed("Denied", "Only the person who clicked close can confirm."),
                ephemeral=True,
            )
            return
        self.confirmed = True
        await interaction.response.edit_message(
            embed=success_embed("Confirmed", "Closing ticket..."),
            view=None,
        )
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            return
        await interaction.response.edit_message(
            embed=info_embed("Cancelled", "Ticket will remain open."),
            view=None,
        )
        self.stop()


class TicketPanelView(discord.ui.View):
    """Persistent panel view with an Open Ticket button."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Open Ticket",
        emoji="🎫",
        style=discord.ButtonStyle.primary,
        custom_id="skillx_open_ticket",
    )
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        if guild is None:
            return

        config = _load_config()
        guild_key = str(guild.id)
        guild_cfg = config.get(guild_key, {})

        category_id = guild_cfg.get("category_id")
        category: Optional[discord.CategoryChannel] = None
        if category_id:
            category = guild.get_channel(category_id)

        # Increment ticket counter
        count = guild_cfg.get("ticket_count", 0) + 1
        guild_cfg["ticket_count"] = count
        config[guild_key] = guild_cfg
        _save_config(config)

        user = interaction.user
        clean_name = user.name.lower().replace(" ", "-")[:20]
        channel_name = f"ticket-{clean_name}-{count}"

        # Build overwrites: deny @everyone, allow opener + bot
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                attach_files=True,
                embed_links=True,
                read_message_history=True,
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                manage_channels=True,
                manage_messages=True,
                read_message_history=True,
            ),
        }

        # Also allow members with admin/manage_guild
        for role in guild.roles:
            if role.permissions.administrator or role.permissions.manage_guild:
                if role != guild.default_role:
                    overwrites[role] = discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        read_message_history=True,
                    )

        try:
            ticket_channel = await guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                topic=f"Ticket opened by {user} (ID: {user.id})",
                reason=f"Support ticket #{count} opened by {user}",
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=error_embed("Error", "I don't have permission to create channels."),
                ephemeral=True,
            )
            return
        except discord.HTTPException as exc:
            await interaction.response.send_message(
                embed=error_embed("Error", f"Failed to create ticket channel: {exc}"),
                ephemeral=True,
            )
            return

        # Send welcome message in the new ticket channel
        welcome_embed = base_embed(
            title="🎫 Support Ticket",
            description=(
                f"Welcome {user.mention}!\n\n"
                "Thank you for opening a ticket. Please describe your issue below "
                "and a staff member will assist you shortly.\n\n"
                "**Guidelines:**\n"
                "• Be as detailed as possible\n"
                "• Include screenshots if relevant\n"
                "• A staff member will respond soon\n\n"
                "Click the 🔒 button below when your issue is resolved."
            ),
            color=BRAND_COLOR,
            user=user,
        )
        welcome_embed.set_thumbnail(url=user.display_avatar.url)

        await ticket_channel.send(embed=welcome_embed, view=TicketCloseView())

        # Acknowledge to the user
        await interaction.response.send_message(
            embed=success_embed("Ticket Created", f"Your ticket has been opened: {ticket_channel.mention}"),
            ephemeral=True,
        )


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _load_config() -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_config(config: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(config, indent=2), encoding="utf-8")


def _parse_opener_from_topic(channel: discord.TextChannel) -> Optional[int]:
    """Extract the opener user ID from the channel topic."""
    topic = channel.topic or ""
    # Topic format: "Ticket opened by User (ID: 123456)"
    if "ID: " in topic:
        try:
            id_str = topic.split("ID: ")[1].rstrip(")")
            return int(id_str)
        except (ValueError, IndexError):
            pass
    return None


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------

class Tickets(commands.Cog, name="Tickets"):
    """Channel-based support ticket system with persistent panels."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        """Register persistent views when the cog loads."""
        self.bot.add_view(TicketPanelView())
        self.bot.add_view(TicketCloseView())
        logger.info("Registered persistent ticket views")

    # ---------------------------------------------------------
    # TICKET-SETUP COMMAND
    # ---------------------------------------------------------

    async def _execute_ticket_setup(
        self,
        guild: discord.Guild,
        channel: discord.TextChannel,
        category: Optional[discord.CategoryChannel],
        send_reply,
    ):
        config = _load_config()
        guild_key = str(guild.id)

        guild_cfg = config.get(guild_key, {})
        guild_cfg["panel_channel_id"] = channel.id
        if category:
            guild_cfg["category_id"] = category.id
        guild_cfg.setdefault("ticket_count", 0)
        config[guild_key] = guild_cfg
        _save_config(config)

        # Send the ticket panel embed to the target channel
        panel_embed = base_embed(
            title="🎫 Support Tickets",
            description=(
                "Need help? Click the button below to open a support ticket!\n\n"
                "A private channel will be created where you can describe your issue "
                "and communicate with the staff team."
            ),
            color=BRAND_COLOR,
        )
        panel_embed.set_footer(text="SkillX Ticket System • Click to open")

        await channel.send(embed=panel_embed, view=TicketPanelView())

        await send_reply(
            embed=success_embed(
                "Ticket Panel Sent",
                f"Ticket panel has been sent to {channel.mention}."
                + (f"\nTicket category: **{category.name}**" if category else ""),
            )
        )

    @app_commands.command(name="ticket-setup", description="Set up the ticket panel in a channel")
    @app_commands.describe(
        channel="Channel to send the ticket panel to",
        category="Category to create ticket channels under",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def ticket_setup_slash(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        category: Optional[discord.CategoryChannel] = None,
    ):
        async def send_reply(embed):
            await interaction.response.send_message(embed=embed, ephemeral=True)

        await self._execute_ticket_setup(interaction.guild, channel, category, send_reply)

    @commands.command(name="ticket-setup", help="Set up the ticket panel. Usage: ticket-setup #channel [category-name]")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def ticket_setup_prefix(
        self,
        ctx: commands.Context,
        channel: discord.TextChannel,
        category: Optional[discord.CategoryChannel] = None,
    ):
        async def send_reply(embed):
            await ctx.reply(embed=embed, mention_author=False)

        await self._execute_ticket_setup(ctx.guild, channel, category, send_reply)

    # ---------------------------------------------------------
    # TICKET-ADD COMMAND
    # ---------------------------------------------------------

    async def _execute_ticket_add(
        self,
        channel: discord.TextChannel,
        user: discord.Member,
        send_reply,
    ):
        if not channel.name.startswith("ticket-"):
            await send_reply(embed=error_embed("Not a Ticket", "This command can only be used in a ticket channel."))
            return

        await channel.set_permissions(
            user,
            view_channel=True,
            send_messages=True,
            attach_files=True,
            read_message_history=True,
        )
        await send_reply(embed=success_embed("User Added", f"{user.mention} has been added to this ticket."))

    @app_commands.command(name="ticket-add", description="Add a user to the current ticket channel")
    @app_commands.describe(user="The user to add to this ticket")
    @app_commands.guild_only()
    async def ticket_add_slash(self, interaction: discord.Interaction, user: discord.Member):
        async def send_reply(embed):
            await interaction.response.send_message(embed=embed, ephemeral=True)

        await self._execute_ticket_add(interaction.channel, user, send_reply)

    @commands.command(name="ticket-add", help="Add a user to the current ticket. Usage: ticket-add @user")
    @commands.guild_only()
    async def ticket_add_prefix(self, ctx: commands.Context, user: discord.Member):
        async def send_reply(embed):
            await ctx.reply(embed=embed, mention_author=False)

        await self._execute_ticket_add(ctx.channel, user, send_reply)

    # ---------------------------------------------------------
    # TICKET-REMOVE COMMAND
    # ---------------------------------------------------------

    async def _execute_ticket_remove(
        self,
        channel: discord.TextChannel,
        user: discord.Member,
        send_reply,
    ):
        if not channel.name.startswith("ticket-"):
            await send_reply(embed=error_embed("Not a Ticket", "This command can only be used in a ticket channel."))
            return

        await channel.set_permissions(user, overwrite=None)
        await send_reply(embed=success_embed("User Removed", f"{user.mention} has been removed from this ticket."))

    @app_commands.command(name="ticket-remove", description="Remove a user from the current ticket channel")
    @app_commands.describe(user="The user to remove from this ticket")
    @app_commands.guild_only()
    async def ticket_remove_slash(self, interaction: discord.Interaction, user: discord.Member):
        async def send_reply(embed):
            await interaction.response.send_message(embed=embed, ephemeral=True)

        await self._execute_ticket_remove(interaction.channel, user, send_reply)

    @commands.command(name="ticket-remove", help="Remove a user from the current ticket. Usage: ticket-remove @user")
    @commands.guild_only()
    async def ticket_remove_prefix(self, ctx: commands.Context, user: discord.Member):
        async def send_reply(embed):
            await ctx.reply(embed=embed, mention_author=False)

        await self._execute_ticket_remove(ctx.channel, user, send_reply)


async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))
