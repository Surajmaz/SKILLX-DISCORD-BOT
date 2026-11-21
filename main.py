"""SkillX Discord Bot: Production-ready bot entrypoint.

Subclasses commands.Bot with setup_hook, structured logging, rich help manual,
and centralized error handling for prefix and slash commands.
"""

import asyncio
import logging
import sys
from typing import Mapping, Optional
import discord
from discord import app_commands
from discord.ext import commands

from config import (
    BOT_NAME,
    COMMAND_PREFIXES,
    DASHBOARD_ENABLED,
    DASHBOARD_HOST,
    DASHBOARD_PASSWORD,
    DASHBOARD_PASSWORD_IS_GENERATED,
    DASHBOARD_PORT,
    DASHBOARD_SECRET_KEY,
    DISCORD_TOKEN,
    GUILD_ID,
    VERSION,
    validate_config,
)
from dashboard import start_dashboard
from embeds import BRAND_COLOR, error_embed, info_embed

# Configure structured terminal logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)-16s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("skillx.main")


class EmbedHelpCommand(commands.HelpCommand):
    """Custom aesthetic HelpCommand using Discord Embeds."""

    @property
    def clean_prefix(self) -> str:
        """Returns the clean invoking prefix or default fallback."""
        if self.context and hasattr(self.context, "clean_prefix"):
            p = self.context.clean_prefix
            return p if p else "/"
        return "/"

    async def send_bot_help(self, mapping: Mapping[Optional[commands.Cog], list[commands.Command]]):
        embed = discord.Embed(
            title="📖 SkillX Command Directory",
            description=(
                "⚡ **Prefix-less & Slash Command Suite**\n"
                "• **Slash Commands:** Type `/` to browse and execute commands.\n"
                "• **Conversational AI:** Simply mention `@SkillX <prompt>` or reply to any bot message!\n"
                "• **Direct Commands:** Type commands directly (e.g. `ping`, `help`, `serverinfo`)."
            ),
            color=BRAND_COLOR,
        )

        for cog, cmds in mapping.items():
            filtered = await self.filter_commands(cmds, sort=True)
            if not filtered:
                continue

            cog_name = getattr(cog, "qualified_name", "General")
            lines = [f"`/{c.name}` or `{c.name}` — {c.short_doc or c.name}" for c in filtered]
            embed.add_field(
                name=f"📌 {cog_name} ({len(filtered)})",
                value="\n".join(lines)[:1024],
                inline=False,
            )

        embed.set_footer(text="SkillX Bot Manual • All commands rate-limited • Click 🌐 to Translate")
        from ui import HelpMenuView
        author_id = self.context.author.id if hasattr(self, "context") and self.context else 0
        bot_instance = self.context.bot if hasattr(self, "context") and self.context else None
        view = HelpMenuView(bot_instance, author_id, current_embed=embed)
        await self.get_destination().send(embed=embed, view=view)

    async def send_command_help(self, command: commands.Command):
        embed = discord.Embed(
            title=f"📖 Command: /{command.qualified_name}",
            description=command.help or "No description provided.",
            color=BRAND_COLOR,
        )
        if command.aliases:
            embed.add_field(
                name="Aliases",
                value=", ".join(f"`{a}`" for a in command.aliases),
                inline=False,
            )

        sig = command.signature.strip()
        usage = f"`/{command.qualified_name} {sig}` or `{command.qualified_name} {sig}`".strip()
        embed.add_field(name="Usage Syntax", value=usage, inline=False)
        embed.set_footer(text="Parameters inside < > are required; [ ] are optional.")
        await self.get_destination().send(embed=embed)

    async def send_group_help(self, group: commands.Group):
        await self.send_command_help(group)

    async def send_cog_help(self, cog: commands.Cog):
        commands_list = await self.filter_commands(cog.get_commands(), sort=True)
        if not commands_list:
            await self.get_destination().send(embed=error_embed("Empty Cog", "No available commands found."))
            return

        embed = discord.Embed(
            title=f"📁 Category: {cog.qualified_name}",
            description=cog.description or "Category commands:",
            color=BRAND_COLOR,
        )
        lines = [f"`{self.clean_prefix}{c.name}` — {c.short_doc or c.name}" for c in commands_list]
        embed.add_field(name="Commands", value="\n".join(lines)[:1024], inline=False)
        await self.get_destination().send(embed=embed)

    async def send_error_message(self, error: str):
        await self.get_destination().send(embed=error_embed("Help Error", error))


class SkillXBot(commands.Bot):
    """Core SkillX Discord Bot application client."""

    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True

        super().__init__(
            command_prefix=commands.when_mentioned_or(*COMMAND_PREFIXES),
            intents=intents,
            help_command=EmbedHelpCommand(),
        )

        self.extensions_to_load = [
            "cogs.ai_chat",
            "cogs.moderation",
            "cogs.utility",
            "cogs.automod",
            "cogs.community",
            "cogs.fun",
            "cogs.leveling",
            "cogs.logging_cog",
            "cogs.tickets",
            "cogs.welcome",
        ]
        self.dashboard_runner = None

    async def setup_hook(self):
        """Asynchronous setup hook executed prior to login."""
        logger.info("Initializing SkillX Bot core subsystems...")

        # Load extension cogs
        for ext in self.extensions_to_load:
            try:
                await self.load_extension(ext)
                logger.info("  ✓ Loaded extension: %s", ext)
            except Exception as exc:
                logger.error("  ✗ Failed to load extension %s: %s", ext, exc, exc_info=True)

        # Sync application commands
        if GUILD_ID:
            test_guild = discord.Object(id=GUILD_ID)
            self.tree.copy_global_to(guild=test_guild)
            synced = await self.tree.sync(guild=test_guild)
            logger.info("Synced %d slash commands to Dev Guild ID %d", len(synced), GUILD_ID)
        else:
            synced = await self.tree.sync()
            logger.info("Synced %d slash commands globally to Discord", len(synced))

        # Launch Web Dashboard
        if DASHBOARD_ENABLED:
            try:
                self.dashboard_runner = await start_dashboard(
                    bot=self,
                    host=DASHBOARD_HOST,
                    port=DASHBOARD_PORT,
                    password=DASHBOARD_PASSWORD,
                    secret_key=DASHBOARD_SECRET_KEY,
                )
                if DASHBOARD_PASSWORD_IS_GENERATED:
                    logger.info("🔑 Auto-generated Dashboard Password: %s", DASHBOARD_PASSWORD)
                else:
                    logger.info("🔑 Dashboard using configured password from .env")
            except Exception as exc:
                logger.error("  ✗ Failed to start Web Dashboard: %s", exc, exc_info=True)

    async def close(self):
        """Graceful shutdown hook for cleaning up background services."""
        if self.dashboard_runner:
            logger.info("Closing web dashboard runner...")
            await self.dashboard_runner.cleanup()
        await super().close()

    async def on_ready(self):
        """Dispatched when the bot has connected to the gateway and caches are ready."""
        logger.info("==================================================")
        logger.info("  🚀 %s (v%s) is ONLINE", BOT_NAME, VERSION)
        logger.info("  User: %s (ID: %s)", self.user, self.user.id)
        logger.info("  Connected Guilds: %d", len(self.guilds))
        logger.info("  Default Prefixes: %s", ", ".join(COMMAND_PREFIXES))
        if DASHBOARD_ENABLED:
            logger.info("  🌐 Web Dashboard: http://localhost:%d", DASHBOARD_PORT)
        logger.info("==================================================")

        # Set engaging status presence
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.listening,
                name="/help | @SkillX",
            ),
            status=discord.Status.online,
        )

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        """Unified error interceptor for prefix-based commands."""
        # Ignore unhandled command not found
        if isinstance(error, commands.CommandNotFound):
            return

        if isinstance(error, commands.CommandOnCooldown):
            embed = error_embed(
                "Cooldown Active",
                f"Please wait **{error.retry_after:.1f}s** before reusing `{ctx.command.name}`.",
            )
        elif isinstance(error, commands.MissingPermissions):
            missing = [p.replace("_", " ").title() for p in error.missing_permissions]
            embed = error_embed("Permission Denied", f"You need: `{', '.join(missing)}`")
        elif isinstance(error, commands.BotMissingPermissions):
            missing = [p.replace("_", " ").title() for p in error.missing_permissions]
            embed = error_embed("Bot Permission Error", f"I require: `{', '.join(missing)}`")
        elif isinstance(error, commands.MissingRequiredArgument):
            usage = f"`{ctx.prefix}{ctx.command.qualified_name} {ctx.command.signature}`".strip()
            embed = error_embed(
                "Missing Argument",
                f"Missing required parameter `{error.param.name}`.\n**Usage:** {usage}",
            )
        elif isinstance(error, commands.BadArgument):
            embed = error_embed("Invalid Argument", str(error))
        elif isinstance(error, commands.NoPrivateMessage):
            embed = error_embed("Server Only", "This command can only be used in a server.")
        elif isinstance(error, commands.CheckFailure):
            embed = error_embed("Check Failure", "You do not satisfy the prerequisites for this command.")
        else:
            logger.error("Prefix command error in '%s': %s", ctx.command, error, exc_info=True)
            embed = error_embed("Unexpected Error", "An internal error occurred while executing this command.")

        try:
            await ctx.reply(embed=embed, delete_after=12, mention_author=False)
        except (discord.Forbidden, discord.HTTPException):
            pass


bot = SkillXBot()


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    """Unified error interceptor for slash / application commands."""
    if isinstance(error, app_commands.CommandOnCooldown):
        embed = error_embed(
            "Cooldown Active",
            f"You can reuse this command in **{error.retry_after:.1f}s**.",
        )
    elif isinstance(error, app_commands.MissingPermissions):
        missing = [p.replace("_", " ").title() for p in error.missing_permissions]
        embed = error_embed("Permission Denied", f"You require: `{', '.join(missing)}`")
    elif isinstance(error, app_commands.BotMissingPermissions):
        missing = [p.replace("_", " ").title() for p in error.missing_permissions]
        embed = error_embed("Bot Permission Error", f"I lack the permission: `{', '.join(missing)}`")
    elif isinstance(error, app_commands.NoPrivateMessage):
        embed = error_embed("Server Only", "This slash command only works inside a server.")
    else:
        logger.error("Slash command error: %s", error, exc_info=True)
        embed = error_embed("Command Error", "An unexpected error occurred while executing this slash command.")

    if interaction.response.is_done():
        await interaction.followup.send(embed=embed, ephemeral=True)
    else:
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def main():
    validate_config()
    async with bot:
        await bot.start(DISCORD_TOKEN)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot process interrupted by user. Shutting down cleanly.")
    except Exception as err:
        logger.critical("Fatal startup exception: %s", err, exc_info=True)
        sys.exit(1)
