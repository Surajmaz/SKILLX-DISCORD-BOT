"""Discord Embed builders with consistent styling and bounds checking."""

import discord
from datetime import datetime, timezone
from typing import Optional, Union

# Vibrant Brand Palette
BRAND_COLOR = 0x5865F2  # Discord Blurple
AI_COLOR    = 0x9B59B6  # Amethyst Purple
SUCCESS     = 0x2ECC71  # Emerald Green
ERROR       = 0xE74C3C  # Coral Red
WARNING     = 0xF1C40F  # Amber Yellow
INFO        = 0x3498DB  # Sky Blue

DISCORD_EMBED_MAX_DESC = 4096
DISCORD_EMBED_MAX_TITLE = 256
DISCORD_EMBED_MAX_FIELD = 1024


def base_embed(
    title: str,
    description: str = "",
    color: int = BRAND_COLOR,
    user: Optional[Union[discord.User, discord.Member]] = None,
    footer_text: Optional[str] = "Powered by Gemini • SkillX Bot",
) -> discord.Embed:
    """Creates a base discord Embed with UTC timestamp and bounds-safe text."""
    embed = discord.Embed(
        title=(title or "")[:DISCORD_EMBED_MAX_TITLE],
        description=(description or "")[:DISCORD_EMBED_MAX_DESC],
        color=color,
        timestamp=datetime.now(timezone.utc),
    )
    if user:
        avatar_url = user.display_avatar.url if user.display_avatar else None
        embed.set_author(name=user.display_name[:256], icon_url=avatar_url)
    if footer_text:
        embed.set_footer(text=footer_text[:2048])
    return embed


def ai_response_embed(
    prompt: str,
    response: str,
    user: Optional[Union[discord.User, discord.Member]] = None,
    model_used: str = "Gemini",
    page_info: Optional[str] = None,
    elapsed_ms: Optional[int] = None,
) -> discord.Embed:
    """Builds an aesthetically pleasing AI response card with latency metrics."""
    parts = [f"Model: {model_used}"]
    if elapsed_ms is not None:
        parts.append(f"{elapsed_ms}ms")
    parts.append("SkillX AI")
    if page_info:
        parts.append(page_info)
    footer = " • ".join(parts)

    embed = base_embed(
        title="🤖 AI Response",
        description=(response or "")[:DISCORD_EMBED_MAX_DESC],
        color=AI_COLOR,
        user=user,
        footer_text=footer,
    )
    if prompt:
        embed.add_field(
            name="📝 Prompt",
            value=(prompt or "")[:DISCORD_EMBED_MAX_FIELD],
            inline=False,
        )
    return embed


def moderation_embed(
    action: str,
    target: Union[discord.User, discord.Member],
    moderator: Union[discord.User, discord.Member],
    reason: Optional[str] = None,
    extra_fields: Optional[dict[str, str]] = None,
) -> discord.Embed:
    """Builds a formal moderation log embed."""
    action_lower = action.lower()
    if any(k in action_lower for k in ("ban", "kick")):
        color = ERROR
        icon = "🔨" if "ban" in action_lower else "👢"
    elif "timeout" in action_lower or "mute" in action_lower:
        color = WARNING
        icon = "⏳"
    else:
        color = SUCCESS
        icon = "🛡️"

    embed = base_embed(
        title=f"{icon} Moderation Action: {action}",
        color=color,
        user=moderator,
        footer_text="SkillX Moderation Audit",
    )
    embed.add_field(name="Target", value=f"{target.mention} (`{target.id}`)", inline=True)
    embed.add_field(name="Moderator", value=f"{moderator.mention}", inline=True)
    embed.add_field(name="Reason", value=(reason or "No reason provided")[:DISCORD_EMBED_MAX_FIELD], inline=False)

    if extra_fields:
        for k, v in extra_fields.items():
            embed.add_field(name=k[:256], value=v[:DISCORD_EMBED_MAX_FIELD], inline=True)

    return embed


def success_embed(title: str, description: str = "") -> discord.Embed:
    """Returns a green success embed."""
    return base_embed(f"✅ {title}", description, color=SUCCESS)


def error_embed(title: str, description: str = "") -> discord.Embed:
    """Returns a red error embed."""
    return base_embed(f"❌ {title}", description, color=ERROR)


def warning_embed(title: str, description: str = "") -> discord.Embed:
    """Returns a yellow warning embed."""
    return base_embed(f"⚠️ {title}", description, color=WARNING)


def info_embed(title: str, description: str = "") -> discord.Embed:
    """Returns a blue info embed."""
    return base_embed(f"ℹ️ {title}", description, color=INFO)
