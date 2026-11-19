"""Welcome & Goodbye Cog: Automated member onboarding, custom greetings, autoroles, and farewells."""

import datetime
import json
import logging
from pathlib import Path
from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands

from embeds import BRAND_COLOR, SUCCESS, error_embed, info_embed, success_embed

logger = logging.getLogger("skillx.welcome")
WELCOME_CONFIG_FILE = Path(__file__).parent.parent / "data" / "welcome_config.json"


class Welcome(commands.Cog, name="Welcome"):
    """Automated greeting cards, goodbye notices, and automatic join role assignment."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config: dict[str, dict] = self._load_config()

    def _load_config(self) -> dict[str, dict]:
        if not WELCOME_CONFIG_FILE.exists():
            return {}
        try:
            return json.loads(WELCOME_CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Failed to load welcome config: %s. Starting fresh.", exc)
            return {}

    def _save_config(self) -> None:
        WELCOME_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        try:
            WELCOME_CONFIG_FILE.write_text(json.dumps(self.config, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.error("Failed to save welcome config: %s", exc)

    def _get_guild_config(self, guild_id: int) -> dict:
        gid = str(guild_id)
        if gid not in self.config:
            self.config[gid] = {
                "welcome_channel": None,
                "welcome_message": "Welcome to **{server}**, {user.mention}! We're thrilled to have you here 🎉",
                "goodbye_channel": None,
                "goodbye_message": "**{user}** has left **{server}**. We wish you all the best! 👋",
                "autorole_id": None,
            }
        return self.config[gid]

    def _format_message(self, template: str, member: discord.Member, guild: discord.Guild) -> str:
        text = template or ""
        text = text.replace("{user.mention}", member.mention)
        text = text.replace("{user}", member.display_name)
        text = text.replace("{server}", guild.name)
        text = text.replace("{member_count}", str(guild.member_count or 0))
        return text

    # ---------------------------------------------------------
    # WELCOME / GOODBYE LISTENERS
    # ---------------------------------------------------------

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild = member.guild
        cfg = self.config.get(str(guild.id))
        if not cfg:
            return

        # 1. Autorole assignment
        autorole_id = cfg.get("autorole_id")
        if autorole_id:
            role = guild.get_role(int(autorole_id))
            if role and guild.me.guild_permissions.manage_roles and guild.me.top_role > role:
                try:
                    await member.add_roles(role, reason="SkillX AutoRole on join")
                except Exception as exc:
                    logger.warning("Failed to apply autorole to %s: %s", member, exc)

        # 2. Welcome announcement
        ch_id = cfg.get("welcome_channel")
        if not ch_id:
            return

        channel = guild.get_channel(int(ch_id))
        if not channel or not isinstance(channel, discord.TextChannel):
            return

        if not channel.permissions_for(guild.me).send_messages:
            return

        template = cfg.get("welcome_message") or "Welcome to **{server}**, {user.mention}!"
        msg_content = self._format_message(template, member, guild)

        created_ts = int(member.created_at.timestamp())
        now = datetime.datetime.now(datetime.timezone.utc)
        age_days = (now - member.created_at).days
        account_age_str = f"{age_days} days ago (<t:{created_ts}:R>)"

        embed = discord.Embed(
            title=f"🎉 Welcome to {guild.name}!",
            description=msg_content,
            color=0x57F287,
            timestamp=now,
        )
        if member.display_avatar:
            embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="📅 Account Created", value=account_age_str, inline=True)
        embed.add_field(name="👥 Member Number", value=f"#{guild.member_count}", inline=True)
        embed.set_footer(text=f"User ID: {member.id} • SkillX Community")

        try:
            await channel.send(content=member.mention, embed=embed)
        except Exception as exc:
            logger.error("Failed to send welcome message: %s", exc)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        guild = member.guild
        cfg = self.config.get(str(guild.id))
        if not cfg:
            return

        ch_id = cfg.get("goodbye_channel")
        if not ch_id:
            return

        channel = guild.get_channel(int(ch_id))
        if not channel or not isinstance(channel, discord.TextChannel):
            return

        if not channel.permissions_for(guild.me).send_messages:
            return

        template = cfg.get("goodbye_message") or "**{user}** has left the server. Farewell!"
        msg_content = self._format_message(template, member, guild)

        roles = [r.name for r in member.roles if not r.is_default()]
        roles_str = ", ".join(roles[:8]) if roles else "None"
        if len(roles) > 8:
            roles_str += f" (+{len(roles)-8} more)"

        now = datetime.datetime.now(datetime.timezone.utc)
        stay_time = "Unknown"
        if member.joined_at:
            stay_days = (now - member.joined_at).days
            stay_time = f"{stay_days} days"

        embed = discord.Embed(
            title="👋 Goodbye!",
            description=msg_content,
            color=0xED4245,
            timestamp=now,
        )
        if member.display_avatar:
            embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="⏱️ Time in Server", value=stay_time, inline=True)
        embed.add_field(name="🏷️ Previous Roles", value=roles_str, inline=True)
        embed.set_footer(text=f"User ID: {member.id} • SkillX Community")

        try:
            await channel.send(embed=embed)
        except Exception as exc:
            logger.error("Failed to send goodbye message: %s", exc)

    # ---------------------------------------------------------
    # WELCOME CONFIG COMMANDS
    # ---------------------------------------------------------

    @app_commands.command(name="setwelcome", description="Configure channel and message for member greetings")
    @app_commands.describe(
        channel="Channel where welcome cards are delivered",
        message="Optional custom text ({user}, {user.mention}, {server}, {member_count})",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setwelcome_slash(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        message: Optional[str] = None,
    ):
        cfg = self._get_guild_config(interaction.guild_id)
        cfg["welcome_channel"] = channel.id
        if message:
            cfg["welcome_message"] = message
        self._save_config()

        embed = success_embed(
            "Welcome Channel Set",
            f"Welcome messages will now be posted in {channel.mention}.\n"
            f"**Message Template:**\n`{cfg['welcome_message']}`",
        )
        await interaction.response.send_message(embed=embed)

    @commands.command(name="setwelcome", help="Set welcome channel. Example: !setwelcome #general Welcome {user.mention}!")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def setwelcome_prefix(
        self, ctx: commands.Context, channel: discord.TextChannel, *, message: Optional[str] = None
    ):
        cfg = self._get_guild_config(ctx.guild.id)
        cfg["welcome_channel"] = channel.id
        if message:
            cfg["welcome_message"] = message
        self._save_config()

        embed = success_embed(
            "Welcome Channel Set",
            f"Welcome messages will now be posted in {channel.mention}.\n"
            f"**Template:** `{cfg['welcome_message']}`",
        )
        await ctx.reply(embed=embed, mention_author=False)

    @app_commands.command(name="clearwelcome", description="Disable welcome messages in this server")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def clearwelcome_slash(self, interaction: discord.Interaction):
        cfg = self._get_guild_config(interaction.guild_id)
        cfg["welcome_channel"] = None
        self._save_config()
        await interaction.response.send_message(embed=success_embed("Welcome Disabled", "Welcome greeting messages have been deactivated."))

    @commands.command(name="clearwelcome", help="Disable welcome messages.")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def clearwelcome_prefix(self, ctx: commands.Context):
        cfg = self._get_guild_config(ctx.guild.id)
        cfg["welcome_channel"] = None
        self._save_config()
        await ctx.reply(embed=success_embed("Welcome Disabled", "Welcome greeting messages have been deactivated."), mention_author=False)

    # ---------------------------------------------------------
    # GOODBYE CONFIG COMMANDS
    # ---------------------------------------------------------

    @app_commands.command(name="setgoodbye", description="Configure channel and message for member farewells")
    @app_commands.describe(
        channel="Channel where farewell cards are delivered",
        message="Optional custom text ({user}, {server}, {member_count})",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setgoodbye_slash(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        message: Optional[str] = None,
    ):
        cfg = self._get_guild_config(interaction.guild_id)
        cfg["goodbye_channel"] = channel.id
        if message:
            cfg["goodbye_message"] = message
        self._save_config()

        embed = success_embed(
            "Goodbye Channel Set",
            f"Farewell messages will now be posted in {channel.mention}.\n"
            f"**Message Template:**\n`{cfg['goodbye_message']}`",
        )
        await interaction.response.send_message(embed=embed)

    @commands.command(name="setgoodbye", help="Set goodbye channel. Example: !setgoodbye #logs Farewell {user}!")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def setgoodbye_prefix(
        self, ctx: commands.Context, channel: discord.TextChannel, *, message: Optional[str] = None
    ):
        cfg = self._get_guild_config(ctx.guild.id)
        cfg["goodbye_channel"] = channel.id
        if message:
            cfg["goodbye_message"] = message
        self._save_config()

        embed = success_embed(
            "Goodbye Channel Set",
            f"Farewell messages will now be posted in {channel.mention}.\n"
            f"**Template:** `{cfg['goodbye_message']}`",
        )
        await ctx.reply(embed=embed, mention_author=False)

    @app_commands.command(name="cleargoodbye", description="Disable goodbye messages in this server")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def cleargoodbye_slash(self, interaction: discord.Interaction):
        cfg = self._get_guild_config(interaction.guild_id)
        cfg["goodbye_channel"] = None
        self._save_config()
        await interaction.response.send_message(embed=success_embed("Goodbye Disabled", "Goodbye farewell messages have been deactivated."))

    @commands.command(name="cleargoodbye", help="Disable goodbye messages.")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def cleargoodbye_prefix(self, ctx: commands.Context):
        cfg = self._get_guild_config(ctx.guild.id)
        cfg["goodbye_channel"] = None
        self._save_config()
        await ctx.reply(embed=success_embed("Goodbye Disabled", "Goodbye farewell messages have been deactivated."), mention_author=False)

    # ---------------------------------------------------------
    # TEST PREVIEWS
    # ---------------------------------------------------------

    @app_commands.command(name="testwelcome", description="Simulate a welcome card preview for yourself")
    @app_commands.guild_only()
    async def testwelcome_slash(self, interaction: discord.Interaction):
        cfg = self._get_guild_config(interaction.guild_id)
        template = cfg.get("welcome_message") or "Welcome to **{server}**, {user.mention}!"
        msg = self._format_message(template, interaction.user, interaction.guild)

        created_ts = int(interaction.user.created_at.timestamp())
        now = datetime.datetime.now(datetime.timezone.utc)
        age_days = (now - interaction.user.created_at).days

        embed = discord.Embed(
            title=f"🎉 [TEST PREVIEW] Welcome to {interaction.guild.name}!",
            description=msg,
            color=0x57F287,
            timestamp=now,
        )
        if interaction.user.display_avatar:
            embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.add_field(name="📅 Account Created", value=f"{age_days} days ago (<t:{created_ts}:R>)", inline=True)
        embed.add_field(name="👥 Member Number", value=f"#{interaction.guild.member_count}", inline=True)
        embed.set_footer(text=f"User ID: {interaction.user.id} • SkillX Community")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @commands.command(name="testwelcome", help="Preview welcome card format.")
    @commands.guild_only()
    async def testwelcome_prefix(self, ctx: commands.Context):
        cfg = self._get_guild_config(ctx.guild.id)
        template = cfg.get("welcome_message") or "Welcome to **{server}**, {user.mention}!"
        msg = self._format_message(template, ctx.author, ctx.guild)

        created_ts = int(ctx.author.created_at.timestamp())
        now = datetime.datetime.now(datetime.timezone.utc)
        age_days = (now - ctx.author.created_at).days

        embed = discord.Embed(
            title=f"🎉 [TEST PREVIEW] Welcome to {ctx.guild.name}!",
            description=msg,
            color=0x57F287,
            timestamp=now,
        )
        if ctx.author.display_avatar:
            embed.set_thumbnail(url=ctx.author.display_avatar.url)
        embed.add_field(name="📅 Account Created", value=f"{age_days} days ago (<t:{created_ts}:R>)", inline=True)
        embed.add_field(name="👥 Member Number", value=f"#{ctx.guild.member_count}", inline=True)
        embed.set_footer(text=f"User ID: {ctx.author.id} • SkillX Community")

        await ctx.reply(embed=embed, mention_author=False)

    # ---------------------------------------------------------
    # AUTOROLE CONFIG
    # ---------------------------------------------------------

    @app_commands.command(name="autorole", description="Automatically grant a role to newly joined members")
    @app_commands.describe(role="The role to assign automatically")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_roles=True)
    @app_commands.checks.has_permissions(manage_roles=True)
    async def autorole_slash(self, interaction: discord.Interaction, role: discord.Role):
        if role >= interaction.guild.me.top_role:
            await interaction.response.send_message(
                embed=error_embed("Role Hierarchy Error", f"The role {role.mention} is higher than or equal to my highest role."),
                ephemeral=True,
            )
            return

        cfg = self._get_guild_config(interaction.guild_id)
        cfg["autorole_id"] = role.id
        self._save_config()

        await interaction.response.send_message(
            embed=success_embed("AutoRole Configured", f"New members will automatically receive {role.mention} upon joining.")
        )

    @commands.command(name="autorole", help="Set autorole. Example: !autorole @Member")
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def autorole_prefix(self, ctx: commands.Context, role: discord.Role):
        if role >= ctx.guild.me.top_role:
            await ctx.reply(
                embed=error_embed("Role Hierarchy Error", f"The role {role.mention} is above my role."),
                delete_after=10,
            )
            return

        cfg = self._get_guild_config(ctx.guild.id)
        cfg["autorole_id"] = role.id
        self._save_config()

        await ctx.reply(
            embed=success_embed("AutoRole Configured", f"New members will receive {role.mention}."),
            mention_author=False,
        )

    @app_commands.command(name="clearautorole", description="Disable automatic join role assignment")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_roles=True)
    @app_commands.checks.has_permissions(manage_roles=True)
    async def clearautorole_slash(self, interaction: discord.Interaction):
        cfg = self._get_guild_config(interaction.guild_id)
        cfg["autorole_id"] = None
        self._save_config()
        await interaction.response.send_message(embed=success_embed("AutoRole Removed", "AutoRole has been disabled."))

    @commands.command(name="clearautorole", help="Disable autorole.")
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def clearautorole_prefix(self, ctx: commands.Context):
        cfg = self._get_guild_config(ctx.guild.id)
        cfg["autorole_id"] = None
        self._save_config()
        await ctx.reply(embed=success_embed("AutoRole Removed", "AutoRole has been disabled."), mention_author=False)


async def setup(bot: commands.Bot):
    await bot.add_cog(Welcome(bot))
