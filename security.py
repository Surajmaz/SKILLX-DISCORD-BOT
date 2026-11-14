"""Security utilities: Rate limiting, input sanitization, and permission checks."""

import re
import time
from collections import defaultdict
from functools import wraps
from typing import Optional, Union
import discord
from discord import app_commands


class MultiDimensionRateLimiter:
    """Sliding-window rate limiter tracking user, guild, and global usage dimensions."""

    def __init__(
        self,
        user_limit: tuple[int, int] = (5, 60),
        guild_limit: tuple[int, int] = (30, 60),
        global_limit: tuple[int, int] = (100, 60),
    ):
        self.user_calls: dict[int, list[float]] = defaultdict(list)
        self.guild_calls: dict[int, list[float]] = defaultdict(list)
        self.global_calls: list[float] = []

        self.user_limit = user_limit      # (max_requests, seconds)
        self.guild_limit = guild_limit
        self.global_limit = global_limit
        self._last_cleanup = time.monotonic()

    def _prune(self, store: list[float], window: int, now: float) -> None:
        store[:] = [t for t in store if now - t < window]

    def _periodic_cleanup(self, now: float) -> None:
        """Removes dormant keys from dictionary stores every 5 minutes to prevent memory leaks."""
        if now - self._last_cleanup > 300:
            for uid in [k for k, v in self.user_calls.items() if not v]:
                self.user_calls.pop(uid, None)
            for gid in [k for k, v in self.guild_calls.items() if not v]:
                self.guild_calls.pop(gid, None)
            self._last_cleanup = now

    def check(self, user_id: int, guild_id: Optional[int]) -> tuple[bool, str, float]:
        """
        Validates whether a request is within allowed limits.

        Returns:
            (allowed, rate_limit_tier, retry_after_seconds)
        """
        now = time.monotonic()
        self._periodic_cleanup(now)

        # Check User Tier
        user_max, user_win = self.user_limit
        self._prune(self.user_calls[user_id], user_win, now)
        if len(self.user_calls[user_id]) >= user_max:
            retry_after = round(user_win - (now - self.user_calls[user_id][0]), 1)
            return False, "user", max(0.1, retry_after)

        # Check Guild Tier
        if guild_id is not None:
            guild_max, guild_win = self.guild_limit
            self._prune(self.guild_calls[guild_id], guild_win, now)
            if len(self.guild_calls[guild_id]) >= guild_max:
                retry_after = round(guild_win - (now - self.guild_calls[guild_id][0]), 1)
                return False, "guild", max(0.1, retry_after)

        # Check Global Tier
        global_max, global_win = self.global_limit
        self._prune(self.global_calls, global_win, now)
        if len(self.global_calls) >= global_max:
            retry_after = round(global_win - (now - self.global_calls[0]), 1)
            return False, "global", max(0.1, retry_after)

        # Record this invocation across tiers
        self.user_calls[user_id].append(now)
        self.global_calls.append(now)
        if guild_id is not None:
            self.guild_calls[guild_id].append(now)

        return True, "", 0.0


# Shared singleton limiter for AI endpoints
ai_limiter = MultiDimensionRateLimiter()

MAX_MESSAGE_LENGTH = 4000


def sanitize_input(text: str) -> str:
    """
    Cleans user input:
    - Neutralizes mass pings (@everyone, @here) using zero-width spaces
    - Strips non-printable ASCII control characters while preserving newlines and tabs
    - Truncates to max allowed length
    """
    if not text:
        return ""
    text = text.strip()
    # Replace @everyone and @here with zero-width safe versions so pings do not trigger
    text = re.sub(r"@(everyone|here)", "@\u200b\\1", text)
    # Strip dangerous control characters (0x00 to 0x1f except tab \t=9, newline \n=10, cr \r=13)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    return text[:MAX_MESSAGE_LENGTH]


def require_permissions(**perms: bool):
    """
    Decorator for slash command callback methods (Cog-compatible)
    verifying caller server permissions before execution.
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Cog methods pass (self, interaction, ...); standalone pass (interaction, ...)
            interaction: Optional[discord.Interaction] = next(
                (arg for arg in args if isinstance(arg, discord.Interaction)),
                kwargs.get("interaction"),
            )

            if not interaction:
                return await func(*args, **kwargs)

            if not interaction.guild or not isinstance(interaction.user, discord.Member):
                embed = discord.Embed(
                    title="❌ Server Only",
                    description="This command can only be used inside a Discord server.",
                    color=0xE74C3C,
                )
                if not interaction.response.is_done():
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                else:
                    await interaction.followup.send(embed=embed, ephemeral=True)
                return

            missing = [
                perm_name.replace("_", " ").title()
                for perm_name, required in perms.items()
                if required and not getattr(interaction.user.guild_permissions, perm_name, False)
            ]

            if missing:
                embed = discord.Embed(
                    title="🔒 Missing Permissions",
                    description=f"You need the following permission(s) to run this command:\n`{', '.join(missing)}`",
                    color=0xE74C3C,
                )
                if not interaction.response.is_done():
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                else:
                    await interaction.followup.send(embed=embed, ephemeral=True)
                return

            return await func(*args, **kwargs)
        return wrapper
    return decorator
