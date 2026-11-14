"""Configuration management for SkillX Discord Bot.

Loads environment variables from .env and exposes validated settings.
"""

import os
import secrets
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

# Authentication & IDs
DISCORD_TOKEN: str = os.getenv("DISCORD_TOKEN", "").strip()
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "").strip()

# Optional Guild ID for rapid command sync during testing/development
_raw_guild_id = os.getenv("GUILD_ID", "").strip()
GUILD_ID: Optional[int] = int(_raw_guild_id) if _raw_guild_id.isdigit() and int(_raw_guild_id) > 0 else None

# Bot Command Prefixes (default is empty for prefix-less / slash mode)
_raw_prefixes = os.getenv("COMMAND_PREFIX", "").strip()
if _raw_prefixes:
    COMMAND_PREFIXES: tuple[str, ...] = tuple(p.strip() for p in _raw_prefixes.split(",") if p.strip())
else:
    COMMAND_PREFIXES: tuple[str, ...] = ("",)

# Application Details
BOT_NAME: str = os.getenv("BOT_NAME", "SkillX Bot")
VERSION: str = "2.0.0"

# Web Dashboard Configuration
DASHBOARD_ENABLED: bool = os.getenv("DASHBOARD_ENABLED", "true").lower() in ("true", "1", "yes")
DASHBOARD_HOST: str = os.getenv("DASHBOARD_HOST", "0.0.0.0").strip()
_raw_port = os.getenv("DASHBOARD_PORT", "8080").strip()
DASHBOARD_PORT: int = int(_raw_port) if _raw_port.isdigit() else 8080

# Dashboard Security Credentials (auto-generated if not specified in .env)
_env_dashboard_pass = os.getenv("DASHBOARD_PASSWORD", "").strip()
DASHBOARD_PASSWORD: str = _env_dashboard_pass if _env_dashboard_pass else secrets.token_urlsafe(12)
DASHBOARD_PASSWORD_IS_GENERATED: bool = not bool(_env_dashboard_pass)

_env_dashboard_secret = os.getenv("DASHBOARD_SECRET_KEY", "").strip()
DASHBOARD_SECRET_KEY: str = _env_dashboard_secret if _env_dashboard_secret else secrets.token_hex(32)


def validate_config() -> None:
    """Validates required environment variables before starting the bot."""
    missing = []
    if not DISCORD_TOKEN or DISCORD_TOKEN == "your_discord_bot_token_here":
        missing.append("DISCORD_TOKEN")
    if not GEMINI_API_KEY or GEMINI_API_KEY == "your_gemini_api_key_here":
        missing.append("GEMINI_API_KEY")

    if missing:
        raise RuntimeError(
            f"❌ Missing or unconfigured environment variable(s): {', '.join(missing)}\n"
            "   Please configure them in your `.env` file before running the bot."
        )
