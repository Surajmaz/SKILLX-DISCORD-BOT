"""Utility Cog: Server info, latency diagnostics, user inspection, and bot statistics."""

import sys
import time
from datetime import datetime, timezone
from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands

from config import BOT_NAME, VERSION
from embeds import BRAND_COLOR, base_embed, info_embed, error_embed
from ui import HelpMenuView, LanguageSelectView, build_help_embed


class Utility(commands.Cog, name="Utility"):
    """Helpful diagnostic and lookup tools for members and administrators."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.start_time = datetime.now(timezone.utc)
        self.ctx_menu = app_commands.ContextMenu(
            name="Translate with Gemini",
            callback=self.translate_message_context,
        )
        if hasattr(self.bot, "tree"):
            self.bot.tree.add_command(self.ctx_menu)

    def cog_unload(self):
        if hasattr(self.bot, "tree"):
            try:
                self.bot.tree.remove_command(self.ctx_menu.name, type=self.ctx_menu.type)
            except Exception:
                pass

    # ---------------------------------------------------------
    # PING / DIAGNOSTICS
    # ---------------------------------------------------------

    def _build_ping_embed(
        self,
        ws_latency_ms: int,
        roundtrip_ms: Optional[int] = None,
        ai_latency_ms: Optional[int] = None,
        ai_model: Optional[str] = None,
    ) -> discord.Embed:
        # Realistic geographic routing thresholds (Discord gateways are located in US-East/US-West)
        if ws_latency_ms < 150:
            status = "🟢 Optimal (Regional Route)"
            color = 0x2ECC71
        elif ws_latency_ms < 380:
            status = "🟢 Healthy (Cross-Continental)"
            color = 0x2ECC71
        elif ws_latency_ms < 600:
            status = "🟡 Moderate Latency"
            color = 0xF1C40F
        else:
            status = "🔴 High Latency"
            color = 0xE74C3C

        embed = base_embed(
            title="🏓 Network & System Latency",
            color=color,
            footer_text=f"Health: {status} • SkillX Diagnostics",
        )
        embed.add_field(name="🌐 Gateway (WebSocket)", value=f"`{ws_latency_ms} ms`", inline=True)
        if roundtrip_ms is not None:
            embed.add_field(name="⚡ REST API Roundtrip", value=f"`{roundtrip_ms} ms`", inline=True)
        if ai_latency_ms is not None:
            tag = f" ({ai_model})" if ai_model else ""
            embed.add_field(name="🤖 Gemini AI Latency", value=f"`{ai_latency_ms} ms`{tag}", inline=True)

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

    @app_commands.command(name="aiping", description="Benchmark Google Gemini AI generation latency")
    async def aiping_slash(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        ai_cog = self.bot.get_cog("AI Chat")
        if not ai_cog or not hasattr(ai_cog, "gemini"):
            await interaction.followup.send(embed=error_embed("AI Offline", "AI subsystem is not loaded."))
            return

        ok, elapsed_ms, model = await ai_cog.gemini.ping_ai()
        if not ok:
            await interaction.followup.send(embed=error_embed("AI Ping Failed", "All Gemini models are momentarily busy."))
            return

        embed = base_embed(
            title="⚡ Gemini AI Latency Benchmark",
            color=0x2ECC71 if elapsed_ms < 3000 else 0xF1C40F,
            footer_text="SkillX AI Diagnostics",
        )
        embed.add_field(name="⏱️ Generation Latency", value=f"`{elapsed_ms} ms`", inline=True)
        embed.add_field(name="🤖 Active Model", value=f"`{model}`", inline=True)
        embed.add_field(name="🌐 Gateway Status", value=f"`{round(self.bot.latency * 1000)} ms`", inline=True)
        await interaction.followup.send(embed=embed)

    @commands.command(name="aiping", aliases=["aipi"], help="Benchmark Gemini AI response generation latency.")
    async def aiping_prefix(self, ctx: commands.Context):
        ai_cog = self.bot.get_cog("AI Chat")
        if not ai_cog or not hasattr(ai_cog, "gemini"):
            await ctx.reply(embed=error_embed("AI Offline", "AI subsystem is not loaded."), mention_author=False)
            return

        async with ctx.typing():
            ok, elapsed_ms, model = await ai_cog.gemini.ping_ai()

        if not ok:
            await ctx.reply(embed=error_embed("AI Ping Failed", "All Gemini models busy."), mention_author=False)
            return

        embed = base_embed(
            title="⚡ Gemini AI Latency Benchmark",
            color=0x2ECC71 if elapsed_ms < 3000 else 0xF1C40F,
            footer_text="SkillX AI Diagnostics",
        )
        embed.add_field(name="⏱️ Generation Latency", value=f"`{elapsed_ms} ms`", inline=True)
        embed.add_field(name="🤖 Active Model", value=f"`{model}`", inline=True)
        embed.add_field(name="🌐 Gateway Status", value=f"`{round(self.bot.latency * 1000)} ms`", inline=True)
        await ctx.reply(embed=embed, mention_author=False)

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

    @app_commands.command(
        name="help",
        description="Display interactive command manual with multi-language AI translation",
    )
    @app_commands.describe(category="Jump directly to a specific feature category")
    @app_commands.choices(category=[
        app_commands.Choice(name="Overview (All Features)", value="overview"),
        app_commands.Choice(name="🤖 Artificial Intelligence", value="ai"),
        app_commands.Choice(name="🛡️ Moderation & AutoMod", value="moderation"),
        app_commands.Choice(name="🎉 Community & Engagement", value="community"),
        app_commands.Choice(name="🎮 Fun & Mini-Games", value="fun"),
        app_commands.Choice(name="📈 Leveling & XP", value="leveling"),
        app_commands.Choice(name="🎫 Support Tickets", value="tickets"),
        app_commands.Choice(name="👋 Welcome & AutoRole", value="welcome"),
        app_commands.Choice(name="📋 Server Audit Logs", value="logs"),
        app_commands.Choice(name="⚡ Utilities & Diagnostics", value="utility"),
    ])
    async def help_slash(
        self,
        interaction: discord.Interaction,
        category: Optional[app_commands.Choice[str]] = None,
    ):
        cat_key = category.value if category else "overview"
        embed = build_help_embed(cat_key, interaction.user)
        view = HelpMenuView(self.bot, interaction.user.id, current_embed=embed)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @commands.command(
        name="help",
        aliases=["commands", "manual", "features"],
        help="Display interactive command manual with multi-language AI translation.",
    )
    async def help_prefix(self, ctx: commands.Context, category: Optional[str] = "overview"):
        embed = build_help_embed(category or "overview", ctx.author)
        view = HelpMenuView(self.bot, ctx.author.id, current_embed=embed)
        await ctx.reply(embed=embed, view=view, mention_author=False)

    # ---------------------------------------------------------
    # MULTI-LANGUAGE TRANSLATION
    # ---------------------------------------------------------

    @app_commands.command(
        name="translate",
        description="Translate any text into 25+ languages using Gemini AI",
    )
    @app_commands.describe(
        text="The text or feature description to translate",
        target_language="Target language (e.g. Spanish, French, Japanese, Hindi, German, Russian)",
        private="Keep the translation visible only to you (ephemeral)",
    )
    async def translate_slash(
        self,
        interaction: discord.Interaction,
        text: str,
        target_language: str,
        private: bool = True,
    ):
        await interaction.response.defer(ephemeral=private)
        ai_cog = self.bot.get_cog("AI Chat") if hasattr(self.bot, "get_cog") else None
        if ai_cog and hasattr(ai_cog, "gemini"):
            client = ai_cog.gemini
        else:
            from config import GEMINI_API_KEY
            from gemini_client import GeminiClient
            client = GeminiClient(GEMINI_API_KEY)

        translated, model = await client.translate_text(text, target_language)
        if not translated:
            await interaction.followup.send(
                content="❌ Translation failed. Gemini AI service may be momentarily busy.",
                ephemeral=private,
            )
            return

        embed = base_embed(
            title=f"🌐 Translated to {target_language.strip().title()}",
            description=translated,
            color=0x6C5CE7,
            user=interaction.user,
            footer_text=f"SkillX Translation Engine • Gemini ({model})",
        )
        embed.add_field(name="Original", value=text[:1024], inline=False)
        await interaction.followup.send(embed=embed, ephemeral=private)

    async def translate_message_context(self, interaction: discord.Interaction, message: discord.Message):
        content = message.clean_content or (message.embeds[0].description if message.embeds else "")
        if not content:
            await interaction.response.send_message("❌ Message contains no translatable text.", ephemeral=True)
            return

        msg_embed = discord.Embed(
            title="📝 Message Content",
            description=content[:2000],
            color=0x6C5CE7,
        )
        msg_embed.set_author(name=f"Message by {message.author.display_name}", icon_url=message.author.display_avatar.url)
        view = LanguageSelectView(msg_embed, self.bot, interaction.user.id)

        prompt_embed = discord.Embed(
            title="🌐 Translate Message with Gemini AI",
            description=(
                f"**Original message from {message.author.mention}:**\n> {content[:250]}...\n\n"
                "Select a target language from the dropdown menu below:"
            ),
            color=0x6C5CE7,
        )
        prompt_embed.set_footer(text="Translated via Google Gemini AI")
        await interaction.response.send_message(embed=prompt_embed, view=view, ephemeral=True)

    # ---------------------------------------------------------
    # STRESS TEST & AUTO-HEALING
    # ---------------------------------------------------------

    @app_commands.command(
        name="stresstest",
        description="Run a multi-subsystem stress test and automatic remediation benchmark (Admin)",
    )
    @app_commands.describe(
        intensity="Workload intensity level",
        auto_heal="Automatically execute self-healing and optimization post-test",
    )
    @app_commands.choices(intensity=[
        app_commands.Choice(name="Low (Quick Health Check)", value="low"),
        app_commands.Choice(name="Medium (Standard Load)", value="medium"),
        app_commands.Choice(name="High (Heavy Concurrency)", value="high"),
    ])
    @app_commands.default_permissions(administrator=True)
    async def stresstest_slash(
        self,
        interaction: discord.Interaction,
        intensity: Optional[app_commands.Choice[str]] = None,
        auto_heal: Optional[bool] = True,
    ):
        await interaction.response.defer(thinking=True)
        from stress_test import SystemStressTester

        level = intensity.value if intensity else "medium"
        tester = SystemStressTester(self.bot)
        report = await tester.run_full_stress_test(intensity=level, auto_heal=bool(auto_heal))

        embed = base_embed(
            title="⚡ SkillX Supreme Stress Test Report",
            description=(
                f"**System Resilience Score:** `{report['resilience_score']}/100` • **Grade:** `{report['grade']}`\n"
                f"**Benchmark Intensity:** `{report['intensity']}` • **Duration:** `{report['duration_seconds']}s`"
            ),
            color=0x2ECC71 if report["resilience_score"] >= 85 else 0xF1C40F,
            user=interaction.user,
            footer_text="SkillX Self-Healing Diagnostics Core",
        )

        sub = report["subsystems"]
        loop_s = sub["event_loop"]
        embed.add_field(
            name="⏱️ Event Loop Responsiveness",
            value=f"• Jitter: `{loop_s['avg_jitter_ms']}ms` (P95: `{loop_s['p95_jitter_ms']}ms`)\n• Status: **{loop_s['status']}**",
            inline=True,
        )

        io_s = sub["database_io"]
        embed.add_field(
            name="💾 Storage & File I/O",
            value=f"• Throughput: `{io_s['iops']} ops/sec`\n• Avg Op: `{io_s['avg_op_latency_ms']}ms` ({io_s['status']})",
            inline=True,
        )

        ai_s = sub["ai_fleet"]
        embed.add_field(
            name="🤖 AI Model Fleet",
            value=f"• Healthy: `{ai_s['healthy_models']}/{ai_s['total_models']}` Models\n• Status: **{ai_s['status']}**",
            inline=True,
        )

        if report.get("remediation"):
            rem = report["remediation"]
            actions_str = "\n".join(f"✓ {a}" for a in rem["actions_taken"][:4])
            embed.add_field(
                name="🛠️ Automatic Solution & Self-Healing",
                value=f"**Remediation Status: {rem['status']}** ({rem['duration_ms']}ms)\n{actions_str}\n• Freed RAM: `{rem['freed_memory_mb']} MB`",
                inline=False,
            )

        await interaction.followup.send(embed=embed)

    @commands.command(
        name="stresstest",
        aliases=["stress", "sysbenchmark"],
        help="Run multi-subsystem stress test and auto-remediation (Admin only).",
    )
    @commands.has_permissions(administrator=True)
    async def stresstest_prefix(self, ctx: commands.Context, intensity: str = "medium"):
        async with ctx.typing():
            from stress_test import SystemStressTester

            tester = SystemStressTester(self.bot)
            report = await tester.run_full_stress_test(intensity=intensity, auto_heal=True)

        embed = base_embed(
            title="⚡ SkillX Supreme Stress Test Report",
            description=(
                f"**Resilience Score:** `{report['resilience_score']}/100` ({report['grade']})\n"
                f"**Intensity:** `{report['intensity']}` • **Elapsed:** `{report['duration_seconds']}s`"
            ),
            color=0x2ECC71 if report["resilience_score"] >= 85 else 0xF1C40F,
            user=ctx.author,
            footer_text="SkillX Self-Healing Diagnostics Core",
        )

        sub = report["subsystems"]
        embed.add_field(
            name="⏱️ Event Loop",
            value=f"`{sub['event_loop']['avg_jitter_ms']}ms` jitter ({sub['event_loop']['status']})",
            inline=True,
        )
        embed.add_field(
            name="💾 Storage I/O",
            value=f"`{sub['database_io']['iops']} IOPS` ({sub['database_io']['status']})",
            inline=True,
        )
        embed.add_field(
            name="🤖 AI Fleet",
            value=f"`{sub['ai_fleet']['healthy_models']}/{sub['ai_fleet']['total_models']}` online",
            inline=True,
        )

        if report.get("remediation"):
            rem = report["remediation"]
            embed.add_field(
                name="🛠️ Automated Remediation",
                value=f"Memory Freed: `{rem['freed_memory_mb']} MB` • Pruned Cache: `{rem['pruned_cache_items']}` items",
                inline=False,
            )

        await ctx.reply(embed=embed, mention_author=False)

    @app_commands.command(
        name="autoheal",
        description="Execute automatic self-healing, garbage collection, and cache optimization (Admin)",
    )
    @app_commands.default_permissions(administrator=True)
    async def autoheal_slash(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        from stress_test import AutoHealingEngine

        rep = await AutoHealingEngine.run_remediation(self.bot)
        embed = base_embed(
            title="🛠️ SkillX System Auto-Healing Completed",
            description=f"Automated self-healing pass executed in **{rep['duration_ms']}ms** with status **{rep['status']}**.",
            color=0x2ECC71,
            user=interaction.user,
            footer_text="SkillX Self-Healing Core",
        )
        for act in rep["actions_taken"]:
            embed.add_field(name="✓ Action Executed", value=act, inline=False)
        embed.add_field(name="🧹 Memory Reclaimed", value=f"`{rep['freed_memory_mb']} MB`", inline=True)
        embed.add_field(name="⚡ Event Loop Lag", value=f"`{rep['event_loop_lag_ms']} ms`", inline=True)
        await interaction.followup.send(embed=embed)

    @commands.command(
        name="autoheal",
        aliases=["remediate", "optimize"],
        help="Run instant system auto-healing and memory reclamation (Admin only).",
    )
    @commands.has_permissions(administrator=True)
    async def autoheal_prefix(self, ctx: commands.Context):
        async with ctx.typing():
            from stress_test import AutoHealingEngine

            rep = await AutoHealingEngine.run_remediation(self.bot)

        embed = base_embed(
            title="🛠️ SkillX System Auto-Healing Completed",
            description=f"Self-healing pass executed in **{rep['duration_ms']}ms**.",
            color=0x2ECC71,
            user=ctx.author,
            footer_text="SkillX Self-Healing Core",
        )
        embed.add_field(name="🧹 Memory Freed", value=f"`{rep['freed_memory_mb']} MB`", inline=True)
        embed.add_field(name="⚡ Event Loop Lag", value=f"`{rep['event_loop_lag_ms']} ms`", inline=True)
        embed.add_field(name="🎯 Pruned Cache", value=f"`{rep['pruned_cache_items']}` items", inline=True)
        await ctx.reply(embed=embed, mention_author=False)


async def setup(bot: commands.Bot):
    await bot.add_cog(Utility(bot))
