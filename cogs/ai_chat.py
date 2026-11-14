"""AI Chat Cog: Harnesses Google Gemini with rate limiting, memory, and multi-page UI."""

import logging
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
    """Gemini-powered natural language conversation with memory and pagination."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.gemini = GeminiClient(GEMINI_API_KEY)
        # In-memory user conversation history: user_id -> list of role/parts messages
        self.memory: dict[int, list[dict]] = {}

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

        # 3. Model Generation
        history = self.memory.get(interaction.user.id, [])
        response_text, model_used = await self.gemini.generate_with_fallback(clean_prompt, history)

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
            view = PaginatedResponseView(pages, interaction.user.id, clean_prompt, model_used)
            msg = await interaction.followup.send(embed=view.build_embed(), view=view)
            view.message = msg
        else:
            embed = ai_response_embed(clean_prompt, response_text, interaction.user, model_used)
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

        # 3. Model Generation with native Discord typing indicator
        async with ctx.typing():
            history = self.memory.get(ctx.author.id, [])
            response_text, model_used = await self.gemini.generate_with_fallback(clean_prompt, history)

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
            view = PaginatedResponseView(pages, ctx.author.id, clean_prompt, model_used)
            msg = await ctx.reply(embed=view.build_embed(), view=view, mention_author=False)
            view.message = msg
        else:
            embed = ai_response_embed(clean_prompt, response_text, ctx.author, model_used)
            await ctx.reply(embed=embed, mention_author=False)

        # 5. Save History
        history.append({"role": "user", "parts": [{"text": clean_prompt}]})
        history.append({"role": "model", "parts": [{"text": response_text}]})
        self.memory[ctx.author.id] = history[-12:]

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
                    "I am **SkillX**, a modern prefix-less Discord AI bot.\n\n"
                    "• **Conversational AI:** Mention me `@SkillX <prompt>` or reply to my messages to chat!\n"
                    "• **Slash Commands:** Type `/` to access `/chat`, `/ping`, `/help`, and moderation tools.\n"
                    "• **Reset Context:** Use `/forget` anytime to wipe our conversational memory."
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

        # AI Generation with typing indicator
        async with message.channel.typing():
            history = self.memory.get(message.author.id, [])
            response_text, model_used = await self.gemini.generate_with_fallback(
                sanitized_prompt, history
            )

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
            view = PaginatedResponseView(pages, message.author.id, sanitized_prompt, model_used)
            msg = await message.reply(embed=view.build_embed(), view=view, mention_author=False)
            view.message = msg
        else:
            embed = ai_response_embed(sanitized_prompt, response_text, message.author, model_used)
            await message.reply(embed=embed, mention_author=False)

        # Threaded history
        history.append({"role": "user", "parts": [{"text": sanitized_prompt}]})
        history.append({"role": "model", "parts": [{"text": response_text}]})
        self.memory[message.author.id] = history[-12:]


async def setup(bot: commands.Bot):
    await bot.add_cog(AIChat(bot))
