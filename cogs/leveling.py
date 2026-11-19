"""Leveling Cog: XP and leveling system with persistent JSON storage, rank cards, and leaderboards."""

import json
import random
import time
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
LEVELS_FILE = DATA_DIR / "levels.json"

# XP constants
XP_MIN = 15
XP_MAX = 25
XP_COOLDOWN = 60  # seconds


def xp_for_level(level: int) -> int:
    """Total cumulative XP required to reach a given level."""
    return 5 * level * level + 50 * level + 100


def level_from_xp(total_xp: int) -> int:
    """Calculate the current level from total XP."""
    level = 0
    while total_xp >= xp_for_level(level + 1):
        level += 1
    return level


def _progress_bar(current: int, maximum: int, length: int = 20) -> str:
    """Generate a Unicode progress bar."""
    if maximum <= 0:
        ratio = 1.0
    else:
        ratio = min(current / maximum, 1.0)
    filled = round(length * ratio)
    return "▓" * filled + "░" * (length - filled)


class Leveling(commands.Cog, name="Leveling"):
    """XP and leveling system with rank cards, leaderboards, and admin tools."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data: dict[str, dict] = {}
        # user_id -> last XP award timestamp (memory-only cooldown)
        self._cooldowns: dict[int, float] = {}
        self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if LEVELS_FILE.exists():
            try:
                with open(LEVELS_FILE, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
            except (json.JSONDecodeError, OSError):
                self.data = {}
        else:
            self.data = {}

    def _save(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(LEVELS_FILE, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _key(self, guild_id: int, user_id: int) -> str:
        return f"{guild_id}_{user_id}"

    def _get_user_data(self, guild_id: int, user_id: int) -> dict:
        key = self._key(guild_id, user_id)
        if key not in self.data:
            self.data[key] = {"xp": 0, "level": 0, "messages": 0}
        return self.data[key]

    def _get_guild_leaderboard(self, guild_id: int) -> list[tuple[int, dict]]:
        """Return sorted list of (user_id, data) for a guild, highest XP first."""
        prefix = f"{guild_id}_"
        entries = []
        for key, data in self.data.items():
            if key.startswith(prefix):
                uid = int(key[len(prefix):])
                entries.append((uid, data))
        entries.sort(key=lambda e: e[1].get("xp", 0), reverse=True)
        return entries

    def _rank_position(self, guild_id: int, user_id: int) -> int:
        """1-based rank position for a user in their guild."""
        lb = self._get_guild_leaderboard(guild_id)
        for idx, (uid, _) in enumerate(lb):
            if uid == user_id:
                return idx + 1
        return len(lb) + 1

    def _build_rank_embed(self, member: discord.Member) -> discord.Embed:
        """Build a beautiful rank card embed."""
        data = self._get_user_data(member.guild.id, member.id)
        level = data["level"]
        xp = data["xp"]
        current_level_xp = xp_for_level(level) if level > 0 else 0
        next_level_xp = xp_for_level(level + 1)
        xp_in_level = xp - (xp_for_level(level) if level > 0 else 0)
        xp_needed = next_level_xp - (xp_for_level(level) if level > 0 else 0)
        rank = self._rank_position(member.guild.id, member.id)
        bar = _progress_bar(xp_in_level, xp_needed, 20)

        embed = base_embed(
            title=f"🏅 Rank Card — {member.display_name}",
            color=BRAND_COLOR,
            user=member,
            footer_text=f"Server Rank #{rank} • SkillX Leveling",
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Level", value=f"**{level}**", inline=True)
        embed.add_field(name="Total XP", value=f"**{xp:,}**", inline=True)
        embed.add_field(name="Rank", value=f"**#{rank}**", inline=True)
        embed.add_field(
            name="Progress to Next Level",
            value=f"`{bar}` **{xp_in_level:,}** / **{xp_needed:,}** XP",
            inline=False,
        )
        embed.add_field(
            name="Messages Tracked",
            value=f"**{data.get('messages', 0):,}**",
            inline=True,
        )
        return embed

    # ------------------------------------------------------------------
    # XP on message
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or not message.guild:
            return

        uid = message.author.id
        now = time.time()

        # Cooldown check
        if uid in self._cooldowns and (now - self._cooldowns[uid]) < XP_COOLDOWN:
            return

        self._cooldowns[uid] = now
        guild_id = message.guild.id
        data = self._get_user_data(guild_id, uid)
        old_level = data["level"]

        xp_gain = random.randint(XP_MIN, XP_MAX)
        data["xp"] += xp_gain
        data["messages"] = data.get("messages", 0) + 1
        new_level = level_from_xp(data["xp"])
        data["level"] = new_level
        self._save()

        # Level-up announcement
        if new_level > old_level:
            next_xp = xp_for_level(new_level + 1)
            current_xp = data["xp"]
            prev_threshold = xp_for_level(new_level) if new_level > 0 else 0
            xp_in_level = current_xp - prev_threshold
            xp_needed = next_xp - prev_threshold
            bar = _progress_bar(xp_in_level, xp_needed, 20)

            embed = base_embed(
                title="🎉 Level Up!",
                description=(
                    f"Congratulations {message.author.mention}! "
                    f"You just advanced to **Level {new_level}**! 🚀\n\n"
                    f"**Progress to Level {new_level + 1}:**\n"
                    f"`{bar}` **{xp_in_level:,}** / **{xp_needed:,}** XP"
                ),
                color=SUCCESS,
                user=message.author,
                footer_text="Keep chatting to level up! • SkillX Leveling",
            )
            embed.set_thumbnail(url=message.author.display_avatar.url)
            try:
                await message.channel.send(embed=embed)
            except discord.HTTPException:
                pass

    # ------------------------------------------------------------------
    # /rank
    # ------------------------------------------------------------------

    @app_commands.command(name="rank", description="View your or another member's rank card")
    @app_commands.describe(user="The member to view (defaults to yourself)")
    @app_commands.guild_only()
    async def rank_slash(self, interaction: discord.Interaction, user: Optional[discord.Member] = None):
        target = user or interaction.user
        if not isinstance(target, discord.Member):
            await interaction.response.send_message(embed=error_embed("Error", "Could not resolve member."), ephemeral=True)
            return
        embed = self._build_rank_embed(target)
        await interaction.response.send_message(embed=embed)

    @commands.command(name="rank", help="View your rank card. Example: !rank @user")
    @commands.guild_only()
    async def rank_prefix(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        target = member or ctx.author
        embed = self._build_rank_embed(target)
        await ctx.reply(embed=embed, mention_author=False)

    # ------------------------------------------------------------------
    # /leaderboard
    # ------------------------------------------------------------------

    @app_commands.command(name="leaderboard", description="View the server XP leaderboard")
    @app_commands.guild_only()
    async def leaderboard_slash(self, interaction: discord.Interaction):
        embed = await self._build_leaderboard_embed(interaction.guild)
        await interaction.response.send_message(embed=embed)

    @commands.command(name="leaderboard", aliases=["lb", "top"], help="View the server XP leaderboard")
    @commands.guild_only()
    async def leaderboard_prefix(self, ctx: commands.Context):
        embed = await self._build_leaderboard_embed(ctx.guild)
        await ctx.reply(embed=embed, mention_author=False)

    async def _build_leaderboard_embed(self, guild: discord.Guild) -> discord.Embed:
        lb = self._get_guild_leaderboard(guild.id)[:10]
        medals = ["🥇", "🥈", "🥉"]

        if not lb:
            return info_embed("Leaderboard", "No one has earned XP yet! Start chatting to earn XP.")

        description_lines = []
        for idx, (uid, data) in enumerate(lb):
            medal = medals[idx] if idx < 3 else f"`#{idx + 1}`"
            member = guild.get_member(uid)
            name = member.display_name if member else f"User {uid}"
            level = data.get("level", 0)
            xp = data.get("xp", 0)
            description_lines.append(
                f"{medal} **{name}** — Level **{level}** • **{xp:,}** XP"
            )

        embed = base_embed(
            title=f"🏆 {guild.name} — XP Leaderboard",
            description="\n".join(description_lines),
            color=BRAND_COLOR,
            footer_text=f"Top {len(lb)} members • SkillX Leveling",
        )
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        return embed

    # ------------------------------------------------------------------
    # /setxp (admin)
    # ------------------------------------------------------------------

    @app_commands.command(name="setxp", description="Set a user's XP (admin only)")
    @app_commands.describe(user="Target member", amount="XP amount to set")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def setxp_slash(self, interaction: discord.Interaction, user: discord.Member, amount: int):
        if amount < 0:
            await interaction.response.send_message(
                embed=error_embed("Invalid Amount", "XP amount cannot be negative."), ephemeral=True
            )
            return
        data = self._get_user_data(interaction.guild.id, user.id)
        data["xp"] = amount
        data["level"] = level_from_xp(amount)
        self._save()
        await interaction.response.send_message(
            embed=success_embed(
                "XP Updated",
                f"Set **{user.display_name}**'s XP to **{amount:,}** (Level **{data['level']}**).",
            )
        )

    @commands.command(name="setxp", help="Set a user's XP. Example: !setxp @user 500")
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def setxp_prefix(self, ctx: commands.Context, member: discord.Member, amount: int):
        if amount < 0:
            await ctx.reply(embed=error_embed("Invalid Amount", "XP cannot be negative."), mention_author=False)
            return
        data = self._get_user_data(ctx.guild.id, member.id)
        data["xp"] = amount
        data["level"] = level_from_xp(amount)
        self._save()
        await ctx.reply(
            embed=success_embed(
                "XP Updated",
                f"Set **{member.display_name}**'s XP to **{amount:,}** (Level **{data['level']}**).",
            ),
            mention_author=False,
        )

    # ------------------------------------------------------------------
    # /resetxp (admin)
    # ------------------------------------------------------------------

    @app_commands.command(name="resetxp", description="Reset a user's XP and level (admin only)")
    @app_commands.describe(user="Target member to reset")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def resetxp_slash(self, interaction: discord.Interaction, user: discord.Member):
        key = self._key(interaction.guild.id, user.id)
        self.data[key] = {"xp": 0, "level": 0, "messages": 0}
        self._save()
        await interaction.response.send_message(
            embed=success_embed(
                "XP Reset",
                f"**{user.display_name}**'s XP and level have been reset to **0**.",
            )
        )

    @commands.command(name="resetxp", help="Reset a user's XP. Example: !resetxp @user")
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def resetxp_prefix(self, ctx: commands.Context, member: discord.Member):
        key = self._key(ctx.guild.id, member.id)
        self.data[key] = {"xp": 0, "level": 0, "messages": 0}
        self._save()
        await ctx.reply(
            embed=success_embed(
                "XP Reset",
                f"**{member.display_name}**'s XP and level have been reset to **0**.",
            ),
            mention_author=False,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Leveling(bot))
