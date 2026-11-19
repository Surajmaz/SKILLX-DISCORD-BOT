"""AI Chat Cog: Harnesses Google Gemini with rate limiting, memory, and multi-page UI."""

import logging
import time
from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands

from config import GEMINI_API_KEY
from embeds import ai_response_embed, base_embed, error_embed, info_embed, success_embed
from gemini_client import GeminiClient
from security import ai_limiter, sanitize_input
from ui import PaginatedResponseView, split_response_into_pages

logger = logging.getLogger("skillx.ai_chat")

RATE_LIMIT_MESSAGES = {
    "user": "You have reached your personal AI request limit.",
    "guild": "This server has reached its collective AI limit.",
    "global": "The bot is experiencing high global AI traffic.",
}


class AIChat(commands.Cog, name="AI Chat"):
    """Gemini-powered natural language conversation with memory, personas, code review, and summarization."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.gemini = GeminiClient(GEMINI_API_KEY)
        # In-memory user conversation history: user_id -> list of role/parts messages
        self.memory: dict[int, list[dict]] = {}
        # User customized persona: user_id -> persona name
        self.user_personas: dict[int, str] = {}
        # Low-latency response cache: (normalized_prompt, persona) -> (response, model, timestamp)
        self.response_cache: dict[tuple[str, str], tuple[str, str, float]] = {}

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        """Cog-specific error boundary for application commands."""
        if isinstance(error, app_commands.CommandOnCooldown):
            embed = error_embed(
                "Cooldown Active",
                f"Please wait **{error.retry_after:.1f}s** before using this command again.",
            )
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            logger.error("Unhandled error in AI cog: %s", error, exc_info=True)

    # ---------------------------------------------------------
    # CHAT COMMANDS
    # ---------------------------------------------------------

    @app_commands.command(name="chat", description="Converse with the Gemini AI assistant")
    @app_commands.describe(prompt="What would you like to ask or talk about?")
    @app_commands.checks.cooldown(5, 60.0, key=lambda i: i.user.id)
    async def chat_slash(self, interaction: discord.Interaction, prompt: str):
        # Immediate deferral with native Discord thinking indicator
        await interaction.response.defer(thinking=True)

        # 1. Rate Limit Check
        allowed, reason, retry_after = ai_limiter.check(
            interaction.user.id, interaction.guild_id
        )
        if not allowed:
            msg = RATE_LIMIT_MESSAGES.get(reason, "Please slow down.")
            embed = error_embed(
                "Rate Limit Exceeded",
                f"{msg}\n⏳ Please try again in **{retry_after}s**.",
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # 2. Input Sanitization
        clean_prompt = sanitize_input(prompt)
        if not clean_prompt:
            embed = error_embed(
                "Invalid Prompt",
                "Your prompt was empty or contained only invalid characters.",
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # 3. Model Generation with Fast Cache
        t0 = time.perf_counter()
        history = self.memory.get(interaction.user.id, [])
        persona = self.user_personas.get(interaction.user.id, "default")

        cache_key = (clean_prompt.lower(), persona)
        if not history and cache_key in self.response_cache:
            c_text, c_model, c_time = self.response_cache[cache_key]
            if time.time() - c_time < 300:
                response_text, model_used = c_text, f"{c_model} (cached)"
            else:
                self.response_cache.pop(cache_key, None)
                response_text, model_used = None, ""
        else:
            response_text, model_used = None, ""

        if not response_text:
            response_text, model_used = await self.gemini.generate_with_fallback(
                clean_prompt, history, persona=persona
            )
            if response_text and not history:
                self.response_cache[cache_key] = (response_text, model_used, time.time())

        elapsed_ms = round((time.perf_counter() - t0) * 1000)

        if not response_text:
            if model_used == "auth_error":
                desc = "The Gemini API key is missing or invalid. Please alert a server administrator."
            else:
                desc = "All Gemini models are momentarily at capacity. Please try again in a minute."
            await interaction.followup.send(embed=error_embed("AI Service Unavailable", desc))
            return

        # 4. Response Dispatching & Pagination
        pages = split_response_into_pages(response_text)
        if len(pages) > 1:
            view = PaginatedResponseView(pages, interaction.user.id, clean_prompt, model_used, elapsed_ms=elapsed_ms)
            msg = await interaction.followup.send(embed=view.build_embed(), view=view)
            view.message = msg
        else:
            embed = ai_response_embed(clean_prompt, response_text, interaction.user, model_used, elapsed_ms=elapsed_ms)
            await interaction.followup.send(embed=embed)

        # 5. Save History (keep last 12 turns = 6 interactions)
        history.append({"role": "user", "parts": [{"text": clean_prompt}]})
        history.append({"role": "model", "parts": [{"text": response_text}]})
        self.memory[interaction.user.id] = history[-12:]

    @commands.command(
        name="chat",
        aliases=["c", "ask", "ai"],
        help="Converse with the Gemini AI assistant. Example: !chat Explain quantum computing",
    )
    @commands.cooldown(5, 60.0, commands.BucketType.user)
    async def chat_prefix(self, ctx: commands.Context, *, prompt: str):
        # 1. Rate Limit Check
        allowed, reason, retry_after = ai_limiter.check(
            ctx.author.id, ctx.guild.id if ctx.guild else None
        )
        if not allowed:
            msg = RATE_LIMIT_MESSAGES.get(reason, "Please slow down.")
            embed = error_embed(
                "Rate Limit Exceeded",
                f"{msg}\n⏳ Please try again in **{retry_after}s**.",
            )
            await ctx.reply(embed=embed, delete_after=15, mention_author=False)
            return

        # 2. Input Sanitization
        clean_prompt = sanitize_input(prompt)
        if not clean_prompt:
            embed = error_embed("Invalid Prompt", "Please provide a valid, non-empty prompt.")
            await ctx.reply(embed=embed, delete_after=10, mention_author=False)
            return

        # 3. Model Generation with Fast Cache
        t0 = time.perf_counter()
        history = self.memory.get(ctx.author.id, [])
        persona = self.user_personas.get(ctx.author.id, "default")

        cache_key = (clean_prompt.lower(), persona)
        if not history and cache_key in self.response_cache:
            c_text, c_model, c_time = self.response_cache[cache_key]
            if time.time() - c_time < 300:
                response_text, model_used = c_text, f"{c_model} (cached)"
            else:
                self.response_cache.pop(cache_key, None)
                response_text, model_used = None, ""
        else:
            response_text, model_used = None, ""

        if not response_text:
            async with ctx.typing():
                response_text, model_used = await self.gemini.generate_with_fallback(
                    clean_prompt, history, persona=persona
                )
                if response_text and not history:
                    self.response_cache[cache_key] = (response_text, model_used, time.time())

        elapsed_ms = round((time.perf_counter() - t0) * 1000)

        if not response_text:
            if model_used == "auth_error":
                desc = "The Gemini API key is missing or invalid. Please alert an administrator."
            else:
                desc = "All Gemini models are momentarily busy. Please try again shortly."
            await ctx.reply(
                embed=error_embed("AI Unavailable", desc),
                delete_after=15,
                mention_author=False,
            )
            return

        # 4. Response Dispatching & Pagination
        pages = split_response_into_pages(response_text)
        if len(pages) > 1:
            view = PaginatedResponseView(pages, ctx.author.id, clean_prompt, model_used, elapsed_ms=elapsed_ms)
            msg = await ctx.reply(embed=view.build_embed(), view=view, mention_author=False)
            view.message = msg
        else:
            embed = ai_response_embed(clean_prompt, response_text, ctx.author, model_used, elapsed_ms=elapsed_ms)
            await ctx.reply(embed=embed, mention_author=False)

        # 5. Save History
        history.append({"role": "user", "parts": [{"text": clean_prompt}]})
        history.append({"role": "model", "parts": [{"text": response_text}]})
        self.memory[ctx.author.id] = history[-12:]

    # ---------------------------------------------------------
    # PERSONA SWITCHER
    # ---------------------------------------------------------

    @app_commands.command(name="persona", description="Switch your AI assistant personality")
    @app_commands.describe(mode="The personality mode to converse with")
    @app_commands.choices(mode=[
        app_commands.Choice(name="Default (Helpful & Balanced)", value="default"),
        app_commands.Choice(name="Developer (Senior Systems Architect)", value="developer"),
        app_commands.Choice(name="Tutor (Patient Concept Educator)", value="tutor"),
        app_commands.Choice(name="Creative (Witty Writer & Storyteller)", value="creative"),
        app_commands.Choice(name="Concise (Brief & Direct)", value="concise"),
    ])
    async def persona_slash(self, interaction: discord.Interaction, mode: app_commands.Choice[str]):
        self.user_personas[interaction.user.id] = mode.value
        embed = success_embed(
            "Persona Updated",
            f"SkillX persona set to **{mode.name}**.\nAll subsequent messages will converse using this style."
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @commands.command(
        name="persona",
        help="Switch your AI personality (default, developer, tutor, creative, concise). Example: !persona developer",
    )
    async def persona_prefix(self, ctx: commands.Context, mode: str = "default"):
        mode_lower = mode.lower()
        valid = ["default", "developer", "tutor", "creative", "concise"]
        if mode_lower not in valid:
            await ctx.reply(
                embed=error_embed("Invalid Persona", f"Choose from: `{', '.join(valid)}`"),
                delete_after=10,
                mention_author=False,
            )
            return
        self.user_personas[ctx.author.id] = mode_lower
        embed = success_embed(
            "Persona Updated",
            f"SkillX persona set to **{mode_lower.capitalize()}**."
        )
        await ctx.reply(embed=embed, delete_after=10, mention_author=False)

    # ---------------------------------------------------------
    # CODE REVIEW COMMAND
    # ---------------------------------------------------------

    @app_commands.command(name="code", description="Review, debug, or optimize code with Gemini Senior Dev")
    @app_commands.describe(code="The code snippet to review", language="Programming language (e.g. python, js, rust)")
    @app_commands.checks.cooldown(3, 60.0, key=lambda i: i.user.id)
    async def code_slash(self, interaction: discord.Interaction, code: str, language: Optional[str] = "python"):
        await interaction.response.defer(thinking=True)
        response_text, model_used = await self.gemini.review_code(code, language or "python")
        if not response_text:
            await interaction.followup.send(embed=error_embed("Review Failed", "Gemini service is currently busy."))
            return

        pages = split_response_into_pages(response_text)
        if len(pages) > 1:
            view = PaginatedResponseView(pages, interaction.user.id, f"Code Review ({language})", model_used)
            msg = await interaction.followup.send(embed=view.build_embed(), view=view)
            view.message = msg
        else:
            embed = ai_response_embed(f"Code Review ({language})", response_text, interaction.user, model_used)
            await interaction.followup.send(embed=embed)

    @commands.command(name="code", help="Review and optimize code. Example: !code def add(a,b): return a+b")
    @commands.cooldown(3, 60.0, commands.BucketType.user)
    async def code_prefix(self, ctx: commands.Context, *, code: str):
        async with ctx.typing():
            response_text, model_used = await self.gemini.review_code(code)
        if not response_text:
            await ctx.reply(embed=error_embed("Review Failed", "Gemini models busy."), delete_after=10)
            return

        pages = split_response_into_pages(response_text)
        if len(pages) > 1:
            view = PaginatedResponseView(pages, ctx.author.id, "Code Review", model_used)
            msg = await ctx.reply(embed=view.build_embed(), view=view, mention_author=False)
            view.message = msg
        else:
            embed = ai_response_embed("Code Review", response_text, ctx.author, model_used)
            await ctx.reply(embed=embed, mention_author=False)

    # ---------------------------------------------------------
    # CHAT SUMMARIZER
    # ---------------------------------------------------------

    @app_commands.command(name="summarize", description="Summarize recent chat messages in this channel")
    @app_commands.describe(amount="Number of recent messages to analyze (5–50)")
    @app_commands.guild_only()
    @app_commands.checks.cooldown(2, 60.0, key=lambda i: i.user.id)
    async def summarize_slash(self, interaction: discord.Interaction, amount: Optional[int] = 25):
        await interaction.response.defer(thinking=True)
        limit = max(5, min(50, amount or 25))

        lines = []
        async for msg in interaction.channel.history(limit=limit):
            if not msg.author.bot and msg.content.strip():
                lines.append(f"{msg.author.display_name}: {msg.content.strip()}")
        lines.reverse()

        if not lines:
            await interaction.followup.send(
                embed=error_embed("No Content", "No user messages found in recent channel history to summarize."),
                ephemeral=True
            )
            return

        dialogue_text = "\n".join(lines[:limit])
        response_text, model_used = await self.gemini.summarize_text(dialogue_text)
        if not response_text:
            await interaction.followup.send(embed=error_embed("Summary Failed", "AI models busy. Please retry."))
            return

        embed = base_embed(
            title=f"📋 Channel Summary (Last {len(lines)} messages)",
            description=response_text[:4000],
            color=0x9B59B6,
            user=interaction.user,
            footer_text=f"Model: {model_used} • Channel #{interaction.channel.name}"
        )
        await interaction.followup.send(embed=embed)

    @commands.command(name="summarize", help="Summarize recent chat. Example: !summarize 20")
    @commands.guild_only()
    @commands.cooldown(2, 60.0, commands.BucketType.user)
    async def summarize_prefix(self, ctx: commands.Context, amount: int = 25):
        limit = max(5, min(50, amount))
        async with ctx.typing():
            lines = []
            async for msg in ctx.channel.history(limit=limit):
                if not msg.author.bot and msg.content.strip():
                    lines.append(f"{msg.author.display_name}: {msg.content.strip()}")
            lines.reverse()

            if not lines:
                await ctx.reply(embed=error_embed("No Content", "No messages found."), delete_after=10)
                return

            dialogue_text = "\n".join(lines[:limit])
            response_text, model_used = await self.gemini.summarize_text(dialogue_text)

        if not response_text:
            await ctx.reply(embed=error_embed("Summary Failed", "Models busy."), delete_after=10)
            return

        embed = base_embed(
            title=f"📋 Channel Summary (Last {len(lines)} messages)",
            description=response_text[:4000],
            color=0x9B59B6,
            user=ctx.author,
            footer_text=f"Model: {model_used} • Channel #{ctx.channel.name}"
        )
        await ctx.reply(embed=embed, mention_author=False)

    # ---------------------------------------------------------
    # MEMORY RESET
    # ---------------------------------------------------------

    @app_commands.command(name="forget", description="Clear your stored AI conversation history")
    async def forget_slash(self, interaction: discord.Interaction):
        had_history = self.memory.pop(interaction.user.id, None) is not None
        if had_history:
            embed = success_embed(
                "Memory Reset",
                "Your conversation history with Gemini has been successfully cleared.",
            )
        else:
            embed = info_embed(
                "No Memory Found",
                "You currently have no active conversation history stored.",
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @commands.command(
        name="forget",
        aliases=["reset", "clearhistory"],
        help="Clear your stored AI conversation history.",
    )
    async def forget_prefix(self, ctx: commands.Context):
        had_history = self.memory.pop(ctx.author.id, None) is not None
        if had_history:
            embed = success_embed(
                "Memory Reset",
                "Your conversation history with Gemini has been cleared.",
            )
        else:
            embed = info_embed("No Memory Found", "You have no active conversation history stored.")
        await ctx.reply(embed=embed, delete_after=10, mention_author=False)

    # ---------------------------------------------------------
    # AI MODEL FLEET STATUS
    # ---------------------------------------------------------

    def _build_models_embed(self, user: Optional[discord.User] = None) -> discord.Embed:
        status_data = self.gemini.get_model_status()
        total = status_data["total_models"]
        healthy = status_data["healthy_models"]

        embed = base_embed(
            title="🤖 SkillX Gemini AI Model Fleet",
            description=(
                f"**Architecture:** Multi-tier fallback chain with auto-healing\n"
                f"**Fleet Health:** `{healthy}/{total} Models Healthy` • "
                f"**Auto-Demotion:** `Active (Dynamic Cooldowns)`\n\n"
                "If any model experiences demand spikes (503) or quota exhaustion (429), "
                "SkillX automatically retries and fails over instantly to the next tier."
            ),
            color=0x2ECC71 if healthy >= (total // 2) else 0xE67E22,
            user=user,
            footer_text="SkillX High-Availability AI Core",
        )

        for m_info in status_data["models"]:
            m_name = m_info["model"]
            m_status = m_info["status"]
            cd = m_info["cooldown_remaining"]
            succ = m_info["successes"]
            fail = m_info["failures"]
            lat = m_info["last_latency_ms"]

            if m_status == "ONLINE":
                icon = "🟢"
                state_str = "**Online**"
                if lat > 0:
                    state_str += f" (`{lat}ms`)"
            elif m_status == "RATE_LIMITED":
                icon = "🔴"
                state_str = f"**Rate Limited** (Ready in {cd}s)"
            else:
                icon = "🟡"
                state_str = f"**Cooling Down** (Ready in {cd}s)"

            stats_str = f"Performance: `{succ} succ / {fail} fail`"
            embed.add_field(
                name=f"{icon} `{m_name}`",
                value=f"{state_str}\n{stats_str}",
                inline=True,
            )

        return embed

    @app_commands.command(
        name="aimodels",
        description="Inspect live health, fallback chain, and latency of all Gemini AI models",
    )
    async def aimodels_slash(self, interaction: discord.Interaction):
        embed = self._build_models_embed(interaction.user)
        await interaction.response.send_message(embed=embed)

    @commands.command(
        name="aimodels",
        aliases=["models", "aichain", "statusai"],
        help="Inspect live health and fallback chain of all Gemini AI models.",
    )
    async def aimodels_prefix(self, ctx: commands.Context):
        embed = self._build_models_embed(ctx.author)
        await ctx.reply(embed=embed, mention_author=False)

    # ---------------------------------------------------------
    # ON_MESSAGE CONVERSATIONAL LISTENER
    # ---------------------------------------------------------

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """
        Prefix-less conversational AI listener.
        Triggers when a user:
        1. Mentions @SkillX
        2. Replies directly to a message sent by SkillX
        3. DMs the bot directly
        """
        if message.author.bot:
            return

        # Ensure bot user object is available
        if not self.bot.user:
            return

        is_dm = message.guild is None
        is_mention = self.bot.user in message.mentions
        is_reply = False

        if message.reference and message.reference.resolved:
            ref_msg = message.reference.resolved
            if isinstance(ref_msg, discord.Message) and ref_msg.author.id == self.bot.user.id:
                is_reply = True

        if not (is_mention or is_reply or is_dm):
            return

        # Check if message is a registered command (e.g. '@SkillX ping' or 'ping')
        ctx = await self.bot.get_context(message)
        if ctx.valid:
            # Let the regular command runner handle it
            return

        # Strip bot mention from prompt content
        clean_content = message.content
        clean_content = clean_content.replace(f"<@{self.bot.user.id}>", "")
        clean_content = clean_content.replace(f"<@!{self.bot.user.id}>", "").strip()

        # If it was an empty mention, show a helpful greeting
        if not clean_content:
            embed = base_embed(
                title=f"👋 Hello, {message.author.display_name}!",
                description=(
                    "I am **SkillX**, an advanced Discord AI and management bot.\n\n"
                    "• **Conversational AI:** Mention me `@SkillX <prompt>` or reply to my messages to chat!\n"
                    "• **AI Personas:** Switch styles with `/persona` (Developer, Tutor, Creative, Concise).\n"
                    "• **Code & Summaries:** Try `/code` for code reviews and `/summarize` for chat recaps.\n"
                    "• **Slash Commands:** Type `/` to browse all commands (`/help`, `/ping`, moderation, community)."
                ),
                user=message.author,
            )
            await message.reply(embed=embed, mention_author=False)
            return

        # Rate Limit Check
        allowed, reason, retry_after = ai_limiter.check(
            message.author.id, message.guild.id if message.guild else None
        )
        if not allowed:
            msg = RATE_LIMIT_MESSAGES.get(reason, "Please slow down.")
            embed = error_embed(
                "Rate Limit Exceeded",
                f"{msg}\n⏳ Please try again in **{retry_after}s**.",
            )
            await message.reply(embed=embed, delete_after=15, mention_author=False)
            return

        # Input Sanitization
        sanitized_prompt = sanitize_input(clean_content)
        if not sanitized_prompt:
            embed = error_embed("Invalid Prompt", "Please provide a valid question or message.")
            await message.reply(embed=embed, delete_after=10, mention_author=False)
            return

        # AI Generation with Fast Cache & timing
        t0 = time.perf_counter()
        history = self.memory.get(message.author.id, [])
        persona = self.user_personas.get(message.author.id, "default")

        cache_key = (sanitized_prompt.lower(), persona)
        if not history and cache_key in self.response_cache:
            c_text, c_model, c_time = self.response_cache[cache_key]
            if time.time() - c_time < 300:
                response_text, model_used = c_text, f"{c_model} (cached)"
            else:
                self.response_cache.pop(cache_key, None)
                response_text, model_used = None, ""
        else:
            response_text, model_used = None, ""

        if not response_text:
            async with message.channel.typing():
                response_text, model_used = await self.gemini.generate_with_fallback(
                    sanitized_prompt, history, persona=persona
                )
                if response_text and not history:
                    self.response_cache[cache_key] = (response_text, model_used, time.time())

        elapsed_ms = round((time.perf_counter() - t0) * 1000)

        if not response_text:
            desc = "All Gemini models are momentarily busy. Please try again shortly."
            await message.reply(
                embed=error_embed("AI Unavailable", desc),
                delete_after=15,
                mention_author=False,
            )
            return

        # Response Dispatching & Pagination
        pages = split_response_into_pages(response_text)
        if len(pages) > 1:
            view = PaginatedResponseView(pages, message.author.id, sanitized_prompt, model_used, elapsed_ms=elapsed_ms)
            msg = await message.reply(embed=view.build_embed(), view=view, mention_author=False)
            view.message = msg
        else:
            embed = ai_response_embed(sanitized_prompt, response_text, message.author, model_used, elapsed_ms=elapsed_ms)
            await message.reply(embed=embed, mention_author=False)

        # Threaded history
        history.append({"role": "user", "parts": [{"text": sanitized_prompt}]})
        history.append({"role": "model", "parts": [{"text": response_text}]})
        self.memory[message.author.id] = history[-12:]


async def setup(bot: commands.Bot):
    await bot.add_cog(AIChat(bot))
