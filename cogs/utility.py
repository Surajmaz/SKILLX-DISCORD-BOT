"""Utility Cog: Server info, latency diagnostics, user inspection, and bot statistics."""

import sys
import time
from datetime import datetime, timezone
from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands

from config import BOT_NAME, VERSION
from embeds import BRAND_COLOR, base_embed, info_embed


class Utility(commands.Cog, name="Utility"):
    """Helpful diagnostic and lookup tools for members and administrators."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.start_time = datetime.now(timezone.utc)

    # ---------------------------------------------------------
    # PING / DIAGNOSTICS
    # ---------------------------------------------------------

    def _build_ping_embed(self, ws_latency_ms: int, roundtrip_ms: Optional[int] = None) -> discord.Embed:
        if ws_latency_ms < 100:
            status = "🟢 Optimal"
            color = 0x2ECC71
        elif ws_latency_ms < 200:
            status = "🟡 Moderate"
            color = 0xF1C40F
        else:
            status = "🔴 Degraded"
            color = 0xE74C3C

        embed = base_embed(
            title="🏓 Network Latency",
            color=color,
            footer_text=f"Status: {status} • SkillX Diagnostics",
        )
        embed.add_field(name="Gateway (WebSocket)", value=f"`{ws_latency_ms} ms`", inline=True)
        if roundtrip_ms is not None:
            embed.add_field(name="REST API Roundtrip", value=f"`{roundtrip_ms} ms`", inline=True)

        return embed

    @app_commands.command(name="ping", description="Check Gateway and Discord API response latency")
    async def ping_slash(self, interaction: discord.Interaction):
        t1 = time.perf_counter()
        await interaction.response.defer()
        t2 = time.perf_counter()

        ws_ms = round(self.bot.latency * 1000)
        api_ms = round((t2 - t1) * 1000)

        embed = self._build_ping_embed(ws_ms, api_ms)
        await interaction.followup.send(embed=embed)

    @commands.command(name="ping", aliases=["latency"], help="Check Gateway and Discord API response latency.")
    async def ping_prefix(self, ctx: commands.Context):
        t1 = time.perf_counter()
        msg = await ctx.reply(embed=base_embed("🏓 Pinging...", color=BRAND_COLOR), mention_author=False)
        t2 = time.perf_counter()

        ws_ms = round(self.bot.latency * 1000)
        api_ms = round((t2 - t1) * 1000)

        embed = self._build_ping_embed(ws_ms, api_ms)
        await msg.edit(embed=embed)

    # ---------------------------------------------------------
    # SERVER INFO
    # ---------------------------------------------------------

    def _build_serverinfo_embed(self, guild: discord.Guild, user: discord.User) -> discord.Embed:
        created_ts = int(guild.created_at.timestamp())
        text_channels = len(guild.text_channels)
        voice_channels = len(guild.voice_channels)
        roles_count = len(guild.roles) - 1  # exclude @everyone

        # Human vs bot breakdown if available
        humans = sum(1 for m in guild.members if not m.bot) if guild.members else "N/A"
        bots = sum(1 for m in guild.members if m.bot) if guild.members else "N/A"

        embed = base_embed(
            title=f"📊 Server Overview: {guild.name}",
            color=BRAND_COLOR,
            user=user,
            footer_text=f"Server ID: {guild.id}",
        )
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        embed.add_field(name="👑 Owner", value=f"{guild.owner.mention if guild.owner else 'Unknown'}", inline=True)
        embed.add_field(name="📅 Created", value=f"<t:{created_ts}:D> (<t:{created_ts}:R>)", inline=True)
        embed.add_field(name="🛡️ Verification", value=str(guild.verification_level).capitalize(), inline=True)

        embed.add_field(
            name=f"👥 Members ({guild.member_count})",
            value=f"Humans: `{humans}` • Bots: `{bots}`",
            inline=True,
        )
        embed.add_field(
            name="💬 Channels",
            value=f"Text: `{text_channels}` • Voice: `{voice_channels}`",
            inline=True,
        )
        embed.add_field(
            name="💎 Boost Tier",
            value=f"Level {guild.premium_tier} ({guild.premium_subscription_count} boosts)",
            inline=True,
        )
        embed.add_field(name="🏷️ Roles", value=f"`{roles_count}` roles", inline=True)

        return embed

    @app_commands.command(name="serverinfo", description="Display comprehensive information about this server")
    @app_commands.guild_only()
    async def serverinfo_slash(self, interaction: discord.Interaction):
        embed = self._build_serverinfo_embed(interaction.guild, interaction.user)
        await interaction.response.send_message(embed=embed)

    @commands.command(name="serverinfo", aliases=["server", "si"], help="Display server statistics.")
    @commands.guild_only()
    async def serverinfo_prefix(self, ctx: commands.Context):
        embed = self._build_serverinfo_embed(ctx.guild, ctx.author)
        await ctx.reply(embed=embed, mention_author=False)

    # ---------------------------------------------------------
    # USER INFO
    # ---------------------------------------------------------

    def _build_userinfo_embed(self, member: discord.Member, requester: discord.User) -> discord.Embed:
        created_ts = int(member.created_at.timestamp())
        joined_ts = int(member.joined_at.timestamp()) if member.joined_at else None

        # Format top roles (excluding @everyone)
        roles = [r.mention for r in reversed(member.roles) if not r.is_default()]
        roles_display = ", ".join(roles[:8]) if roles else "None"
        if len(roles) > 8:
            roles_display += f" (+{len(roles) - 8} more)"

        embed = base_embed(
            title=f"👤 Member: {member.display_name}",
            color=member.accent_color.value if member.accent_color else BRAND_COLOR,
            user=requester,
            footer_text=f"User ID: {member.id}",
        )
        avatar_url = member.display_avatar.url if member.display_avatar else None
        if avatar_url:
            embed.set_thumbnail(url=avatar_url)

        embed.add_field(name="Username", value=f"`{member.name}`", inline=True)
        embed.add_field(name="Bot Account?", value="Yes 🤖" if member.bot else "No 👤", inline=True)
        embed.add_field(name="Top Role", value=member.top_role.mention, inline=True)

        embed.add_field(name="📅 Account Created", value=f"<t:{created_ts}:D> (<t:{created_ts}:R>)", inline=True)
        if joined_ts:
            embed.add_field(name="📥 Server Joined", value=f"<t:{joined_ts}:D> (<t:{joined_ts}:R>)", inline=True)

        embed.add_field(name=f"🏷️ Roles ({len(roles)})", value=roles_display, inline=False)
        return embed

    @app_commands.command(name="userinfo", description="Lookup information about a server member")
    @app_commands.describe(member="Member to lookup (defaults to yourself)")
    @app_commands.guild_only()
    async def userinfo_slash(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        target = member or interaction.user
        embed = self._build_userinfo_embed(target, interaction.user)
        await interaction.response.send_message(embed=embed)

    @commands.command(name="userinfo", aliases=["whois", "ui"], help="Lookup member information.")
    @commands.guild_only()
    async def userinfo_prefix(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        target = member or ctx.author
        embed = self._build_userinfo_embed(target, ctx.author)
        await ctx.reply(embed=embed, mention_author=False)

    # ---------------------------------------------------------
    # BOT INFO / STATS
    # ---------------------------------------------------------

    @app_commands.command(name="botinfo", description="Display bot system status, uptime, and versions")
    async def botinfo_slash(self, interaction: discord.Interaction):
        uptime_delta = datetime.now(timezone.utc) - self.start_time
        days, rem = divmod(int(uptime_delta.total_seconds()), 86400)
        hours, rem = divmod(rem, 3600)
        mins, secs = divmod(rem, 60)
        uptime_str = f"{days}d {hours}h {mins}m {secs}s"

        py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

        embed = base_embed(
            title=f"🤖 {BOT_NAME} System Status",
            color=BRAND_COLOR,
            user=interaction.user,
            footer_text=f"Version {VERSION} • Built with discord.py",
        )
        embed.add_field(name="⏱️ Uptime", value=f"`{uptime_str}`", inline=True)
        embed.add_field(name="🌐 Servers", value=f"`{len(self.bot.guilds)}`", inline=True)
        embed.add_field(name="🏓 Gateway Latency", value=f"`{round(self.bot.latency * 1000)} ms`", inline=True)
        embed.add_field(name="🐍 Python", value=f"`v{py_version}`", inline=True)
        embed.add_field(name="📦 discord.py", value=f"`v{discord.__version__}`", inline=True)
        embed.add_field(name="🧩 Active Cogs", value=f"`{len(self.bot.cogs)}` loaded", inline=True)

        await interaction.response.send_message(embed=embed)

    # ---------------------------------------------------------
    # HELP REFERENCE
    # ---------------------------------------------------------

    @app_commands.command(name="help", description="Display interactive command manual")
    async def help_slash(self, interaction: discord.Interaction):
        embed = base_embed(
            title="📖 SkillX Command Directory",
            description=(
                "⚡ **Prefix-less & Slash System**\n"
                "• **Slash Commands:** Type `/` to select from all available commands.\n"
                "• **Conversational AI:** Mention `@SkillX <prompt>` or reply to any bot message.\n"
                "• **Direct Words:** Standard commands like `ping`, `help`, and `serverinfo` work directly without prefixes."
            ),
            color=BRAND_COLOR,
            user=interaction.user,
            footer_text="SkillX Bot Manual • All commands rate-limited",
        )
        embed.add_field(
            name="🤖 Artificial Intelligence",
            value="`/chat` • `/persona` • `/code` • `/summarize` • `/forget`\n*Conversational Gemini 3.x, code reviews, and chat recaps*",
            inline=False,
        )
        embed.add_field(
            name="🛡️ Moderation & AutoMod",
            value="`/kick` • `/ban` • `/timeout` • `/purge` • `/warn` • `/warnings` • `/clearwarns` • `/lock` • `/unlock` • `/slowmode`\n*Server safety suite with anti-spam, invite filters, and infractions*",
            inline=False,
        )
        embed.add_field(
            name="🎉 Community & Engagement",
            value="`/poll` • `/giveaway` • `/remind` • `/avatar`\n*Interactive button polls with live bars, automated giveaways, and timers*",
            inline=False,
        )
        embed.add_field(
            name="🎮 Fun & Mini-Games",
            value="`/trivia` • `/8ball` • `/coinflip` • `/dice` • `/rps` • `/joke` • `/fact` • `/rate` • `/ship` • `/roast` • `/compliment` • `/mock` • `/reverse`\n*Interactive button trivia, dice, roasts, jokes, and games*",
            inline=False,
        )
        embed.add_field(
            name="📈 Leveling & XP",
            value="`/rank` • `/leaderboard` • `/setxp` • `/resetxp`\n*XP progression, visual rank cards, and competitive leaderboards*",
            inline=False,
        )
        embed.add_field(
            name="🎫 Support Tickets",
            value="`/ticket-setup` • `/ticket-add` • `/ticket-remove`\n*Channel-based private ticket system with transcript exports*",
            inline=False,
        )
        embed.add_field(
            name="👋 Welcome & AutoRole",
            value="`/setwelcome` • `/setgoodbye` • `/testwelcome` • `/autorole`\n*Automated join greetings, farewell embeds, and role assignment*",
            inline=False,
        )
        embed.add_field(
            name="📋 Server Audit Logs",
            value="`/setlogchannel` • `/clearlogchannel`\n*Automatic channel logging for deletes, edits, joins, bans, and voice activity*",
            inline=False,
        )
        embed.add_field(
            name="🔧 Utilities & System",
            value="`/ping` • `/serverinfo` • `/userinfo` • `/botinfo` • `/help`\n*Diagnostics, latency graphs, and profile inspection*",
            inline=False,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Utility(bot))
