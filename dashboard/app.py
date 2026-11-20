"""SkillX Web Dashboard Application.

Hosts asynchronous management endpoints and an interactive web GUI
directly within the Discord bot's event loop via aiohttp.web.
"""

import asyncio
from datetime import datetime, timezone, timedelta
import json
import logging
from pathlib import Path
import resource
import sys
from typing import Optional
from aiohttp import web
import discord

from dashboard.security import DashboardSecurityManager, security_headers_middleware

logger = logging.getLogger("skillx.dashboard")
TEMPLATE_DIR = Path(__file__).parent / "templates"


class DashboardApp:
    """Aiohttp-based secure administration dashboard controller."""

    def __init__(self, bot, password: str, secret_key: str):
        self.bot = bot
        self.security = DashboardSecurityManager(password, secret_key)
        self.app = web.Application(middlewares=[security_headers_middleware])
        self.runner: Optional[web.AppRunner] = None
        self.activity_logs: list[dict] = []
        self._setup_routes()

    def log_activity(self, event_type: str, message: str, meta: Optional[dict] = None) -> None:
        """Stores a recent activity event for the live telemetry feed."""
        self.activity_logs.append({
            "type": event_type,
            "message": message,
            "timestamp": datetime.now(timezone.utc).strftime("%H:%M:%S"),
            "meta": meta or {},
        })
        if len(self.activity_logs) > 100:
            self.activity_logs.pop(0)

    def _setup_routes(self) -> None:
        self.app.router.add_get("/", self.handle_index)
        self.app.router.add_get("/login", self.handle_login_page)
        self.app.router.add_post("/api/login", self.handle_api_login)
        self.app.router.add_post("/api/logout", self.handle_api_logout)

        # Core Authenticated APIs
        self.app.router.add_get("/api/stats", self.handle_api_stats)
        self.app.router.add_get("/api/guilds", self.handle_api_guilds)
        self.app.router.add_get("/api/logs", self.handle_api_logs)
        self.app.router.add_get("/api/infractions", self.handle_api_infractions)
        self.app.router.add_get("/api/leaderboard", self.handle_api_leaderboard)
        self.app.router.add_get("/api/cogs", self.handle_api_cogs)
        self.app.router.add_post("/api/broadcast", self.handle_api_broadcast)
        self.app.router.add_post("/api/ai-test", self.handle_api_ai_test)
        self.app.router.add_post("/api/clear-memory", self.handle_api_clear_memory)
        self.app.router.add_post("/api/presence", self.handle_api_presence)
        self.app.router.add_post("/api/moderation/action", self.handle_api_moderation)
        self.app.router.add_post("/api/moderation/lockdown", self.handle_api_moderation_lockdown)
        self.app.router.add_post("/api/cogs/reload", self.handle_api_reload_cog)
        self.app.router.add_post("/api/cogs/reload-all", self.handle_api_reload_all_cogs)

        # Advanced Feature APIs
        self.app.router.add_get("/api/ai/models", self.handle_api_ai_models)
        self.app.router.add_post("/api/ai/code-review", self.handle_api_ai_code_review)
        self.app.router.add_post("/api/ai/summarize", self.handle_api_ai_summarize)
        self.app.router.add_get("/api/ai/memory", self.handle_api_ai_memory)
        self.app.router.add_post("/api/ai/memory/clear-user", self.handle_api_ai_clear_user_memory)
        self.app.router.add_post("/api/automod/clear-warnings", self.handle_api_automod_clear_warnings)
        self.app.router.add_post("/api/leveling/adjust-xp", self.handle_api_leveling_adjust_xp)
        self.app.router.add_get("/api/welcome/config", self.handle_api_welcome_config_get)
        self.app.router.add_post("/api/welcome/config", self.handle_api_welcome_config_post)
        self.app.router.add_get("/api/tickets/config", self.handle_api_tickets_config_get)
        self.app.router.add_post("/api/tickets/close", self.handle_api_tickets_close)
        self.app.router.add_post("/api/tickets/deploy", self.handle_api_tickets_deploy)
        self.app.router.add_get("/api/logging/config", self.handle_api_logging_config_get)
        self.app.router.add_post("/api/logging/config", self.handle_api_logging_config_post)
        self.app.router.add_post("/api/community/poll", self.handle_api_community_poll)
        self.app.router.add_post("/api/community/giveaway", self.handle_api_community_giveaway)

    def _get_client_ip(self, request: web.Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        peername = request.transport.get_extra_info("peername") if request.transport else None
        if peername:
            return peername[0]
        return "127.0.0.1"

    def _authenticate_request(self, request: web.Request) -> tuple[bool, Optional[str]]:
        session_cookie = request.cookies.get("skillx_session")
        if not self.security.verify_session_token(session_cookie):
            return False, None
        return True, session_cookie

    def _verify_csrf(self, request: web.Request, session_token: str) -> bool:
        csrf_header = request.headers.get("X-CSRF-Token")
        return self.security.verify_csrf_token(session_token, csrf_header)

    # ---------------------------------------------------------
    # PAGE HANDLERS
    # ---------------------------------------------------------

    async def handle_login_page(self, request: web.Request) -> web.Response:
        is_auth, _ = self._authenticate_request(request)
        if is_auth:
            raise web.HTTPFound("/")

        login_html_path = TEMPLATE_DIR / "login.html"
        content = login_html_path.read_text(encoding="utf-8")
        return web.Response(text=content, content_type="text/html")

    async def handle_index(self, request: web.Request) -> web.Response:
        is_auth, session_token = self._authenticate_request(request)
        if not is_auth:
            raise web.HTTPFound("/login")

        csrf_token = self.security.generate_csrf_token(session_token)
        index_html_path = TEMPLATE_DIR / "index.html"
        content = index_html_path.read_text(encoding="utf-8")
        # Inject CSRF token into template safely
        content = content.replace("{{ csrf_token }}", csrf_token)
        return web.Response(text=content, content_type="text/html")

    # ---------------------------------------------------------
    # AUTH APIS
    # ---------------------------------------------------------

    async def handle_api_login(self, request: web.Request) -> web.Response:
        ip = self._get_client_ip(request)
        is_limited, retry_after = self.security.is_ip_rate_limited(ip)
        if is_limited:
            return web.json_response(
                {"success": False, "error": f"Too many failed attempts. Try again in {retry_after}s."},
                status=429,
            )

        try:
            body = await request.json()
            password = str(body.get("password", "")).strip()
        except Exception:
            return web.json_response({"success": False, "error": "Invalid request body."}, status=400)

        if not self.security.verify_password(password):
            self.security.record_failed_login(ip)
            return web.json_response({"success": False, "error": "Incorrect password."}, status=401)

        self.security.reset_failed_logins(ip)
        session_token = self.security.create_session_token()
        self.log_activity("auth", f"Administrator logged into web dashboard from {ip}")
        response = web.json_response({"success": True})
        response.set_cookie(
            name="skillx_session",
            value=session_token,
            max_age=86400,
            httponly=True,
            samesite="Lax",
            secure=False,
            path="/",
        )
        return response

    async def handle_api_logout(self, request: web.Request) -> web.Response:
        response = web.json_response({"success": True})
        response.del_cookie("skillx_session", path="/")
        return response

    # ---------------------------------------------------------
    # DATA & METRIC APIS
    # ---------------------------------------------------------

    async def handle_api_stats(self, request: web.Request) -> web.Response:
        is_auth, _ = self._authenticate_request(request)
        if not is_auth:
            return web.json_response({"error": "Unauthorized"}, status=401)

        # Calculate uptime
        utility_cog = self.bot.get_cog("Utility")
        if utility_cog and hasattr(utility_cog, "start_time"):
            delta = datetime.now(timezone.utc) - utility_cog.start_time
            days, rem = divmod(int(delta.total_seconds()), 86400)
            hours, rem = divmod(rem, 3600)
            mins, secs = divmod(rem, 60)
            uptime_str = f"{days}d {hours}h {mins}m {secs}s"
            uptime_sec = int(delta.total_seconds())
        else:
            uptime_str = "Calculating..."
            uptime_sec = 0

        # AI stats
        ai_cog = self.bot.get_cog("AI Chat")
        ai_memory_count = len(ai_cog.memory) if ai_cog and hasattr(ai_cog, "memory") else 0
        ai_persona_count = len(ai_cog.user_personas) if ai_cog and hasattr(ai_cog, "user_personas") else 0

        # AutoMod stats
        automod_cog = self.bot.get_cog("AutoMod")
        total_warns = 0
        if automod_cog and hasattr(automod_cog, "infractions"):
            total_warns = sum(len(w) for w in automod_cog.infractions.values())

        # Leveling stats
        leveling_cog = self.bot.get_cog("Leveling")
        total_ranked_users = len(leveling_cog.data) if leveling_cog and hasattr(leveling_cog, "data") else 0

        # Tickets stats
        tickets_cog = self.bot.get_cog("Tickets")
        total_tickets = 0
        if tickets_cog and hasattr(tickets_cog, "config"):
            for gcfg in tickets_cog.config.values():
                total_tickets += gcfg.get("ticket_counter", 0)

        # Gateway ping
        ws_latency = round(self.bot.latency * 1000) if self.bot.latency is not None else 0

        # Memory usage
        try:
            mem_mb = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)
        except Exception:
            mem_mb = 0.0

        py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        total_users = sum(g.member_count or 0 for g in self.bot.guilds)

        bot_user_data = None
        if self.bot.user:
            avatar_url = None
            try:
                if hasattr(self.bot.user, "display_avatar") and self.bot.user.display_avatar:
                    avatar_url = str(self.bot.user.display_avatar.url)
            except Exception:
                avatar_url = None

            bot_user_data = {
                "name": str(getattr(self.bot.user, "name", "SkillX")),
                "id": str(getattr(self.bot.user, "id", "0")),
                "avatar": avatar_url,
            }

        data = {
            "guilds": len(self.bot.guilds),
            "users": total_users,
            "latency_ms": ws_latency,
            "uptime_str": uptime_str,
            "uptime_seconds": uptime_sec,
            "ai_memory_contexts": ai_memory_count,
            "ai_persona_overrides": ai_persona_count,
            "total_infractions": total_warns,
            "total_ranked_users": total_ranked_users,
            "total_tickets": total_tickets,
            "bot_user": bot_user_data,
            "system": {
                "python": py_ver,
                "discord_py": discord.__version__,
                "memory_mb": mem_mb,
                "cogs_count": len(self.bot.cogs),
                "cogs_list": list(self.bot.cogs.keys()),
            },
        }
        return web.json_response(data)

    async def handle_api_guilds(self, request: web.Request) -> web.Response:
        is_auth, _ = self._authenticate_request(request)
        if not is_auth:
            return web.json_response({"error": "Unauthorized"}, status=401)

        guild_list = []
        for g in self.bot.guilds:
            text_channels = [
                {
                    "id": str(ch.id),
                    "name": ch.name,
                    "can_send": ch.permissions_for(g.me).send_messages,
                }
                for ch in g.text_channels
            ]
            voice_channels = [{"id": str(v.id), "name": v.name} for v in g.voice_channels]
            roles = [{"id": str(r.id), "name": r.name, "color": f"#{r.color.value:06x}"} for r in reversed(g.roles) if not r.is_default()][:20]

            guild_list.append({
                "id": str(g.id),
                "name": g.name,
                "icon": g.icon.url if g.icon else None,
                "owner": str(g.owner) if g.owner else "Unknown",
                "member_count": g.member_count or 0,
                "text_channels": text_channels,
                "voice_channels": voice_channels,
                "roles_sample": roles,
            })
        return web.json_response(guild_list)

    async def handle_api_logs(self, request: web.Request) -> web.Response:
        is_auth, _ = self._authenticate_request(request)
        if not is_auth:
            return web.json_response({"error": "Unauthorized"}, status=401)
        return web.json_response(list(reversed(self.activity_logs)))

    async def handle_api_infractions(self, request: web.Request) -> web.Response:
        is_auth, _ = self._authenticate_request(request)
        if not is_auth:
            return web.json_response({"error": "Unauthorized"}, status=401)

        automod_cog = self.bot.get_cog("AutoMod")
        infractions_data = []
        if automod_cog and hasattr(automod_cog, "infractions"):
            for key, items in automod_cog.infractions.items():
                try:
                    guild_id_str, user_id_str = key.split("_", 1)
                except ValueError:
                    continue
                for item in items:
                    infractions_data.append({
                        "guild_id": guild_id_str,
                        "user_id": user_id_str,
                        "case_id": item.get("id"),
                        "moderator_id": item.get("moderator_id"),
                        "reason": item.get("reason"),
                        "timestamp": item.get("timestamp"),
                    })

        return web.json_response(list(reversed(infractions_data))[:100])

    # ---------------------------------------------------------
    # INTERACTIVE ACTION APIS
    # ---------------------------------------------------------

    async def handle_api_broadcast(self, request: web.Request) -> web.Response:
        is_auth, token = self._authenticate_request(request)
        if not is_auth or not self._verify_csrf(request, token):
            return web.json_response({"error": "Unauthorized or invalid CSRF token."}, status=403)

        try:
            body = await request.json()
            channel_id_str = str(body.get("channel_id", "")).strip()
            title = str(body.get("title", "")).strip()
            message = str(body.get("message", "")).strip()
            color_raw = body.get("color", "#5865F2")
            use_embed = bool(body.get("use_embed", True))

            # Rich Embed Fields
            author_name = str(body.get("author_name", "")).strip()
            author_icon = str(body.get("author_icon", "")).strip()
            author_url = str(body.get("author_url", "")).strip()
            title_url = str(body.get("title_url", "")).strip()
            footer_text = str(body.get("footer_text", "")).strip()
            footer_icon = str(body.get("footer_icon", "")).strip()
            thumbnail_url = str(body.get("thumbnail_url", "")).strip()
            image_url = str(body.get("image_url", "")).strip()
            fields = body.get("fields", [])
            ping = str(body.get("ping", "none")).strip().lower()
        except Exception:
            return web.json_response({"error": "Malformed JSON payload."}, status=400)

        if not channel_id_str.isdigit() or not message:
            return web.json_response({"error": "Missing valid channel ID or message body."}, status=400)

        channel = self.bot.get_channel(int(channel_id_str))
        if not channel or not isinstance(channel, discord.TextChannel):
            return web.json_response({"error": "Channel not found or bot lacks access."}, status=404)

        if not channel.permissions_for(channel.guild.me).send_messages:
            return web.json_response({"error": "Bot lacks permission to send messages in target channel."}, status=403)

        # Parse and clamp embed color (Discord strictly requires 0 <= color <= 16777215 / 0xFFFFFF)
        color_int = 0x5865F2
        if isinstance(color_raw, int):
            color_int = max(0, min(0xFFFFFF, color_raw))
        elif isinstance(color_raw, str):
            c_str = color_raw.strip().lstrip("#")
            try:
                color_int = max(0, min(0xFFFFFF, int(c_str, 16)))
            except ValueError:
                try:
                    color_int = max(0, min(0xFFFFFF, int(c_str, 10)))
                except ValueError:
                    color_int = 0x5865F2

        prefix_content = ""
        if ping == "everyone":
            prefix_content = "@everyone "
        elif ping == "here":
            prefix_content = "@here "
        elif ping.isdigit():
            prefix_content = f"<@&{ping}> "

        try:
            if use_embed or title or fields or author_name or image_url or thumbnail_url:
                embed = discord.Embed(
                    title=f"📢 {title[:256]}" if title else None,
                    description=message[:4096],
                    color=color_int,
                    url=title_url if title_url.startswith("http") else None,
                    timestamp=datetime.now(timezone.utc),
                )
                if author_name:
                    embed.set_author(
                        name=author_name[:256],
                        icon_url=author_icon if author_icon.startswith("http") else None,
                        url=author_url if author_url.startswith("http") else None,
                    )
                if thumbnail_url and thumbnail_url.startswith("http"):
                    embed.set_thumbnail(url=thumbnail_url)
                if image_url and image_url.startswith("http"):
                    embed.set_image(url=image_url)

                footer_t = footer_text or "Broadcasted via SkillX Web Console"
                embed.set_footer(
                    text=footer_t[:2048],
                    icon_url=footer_icon if footer_icon.startswith("http") else None,
                )

                if isinstance(fields, list):
                    for f in fields[:25]:
                        f_name = str(f.get("name", "")).strip()[:256]
                        f_val = str(f.get("value", "")).strip()[:1024]
                        if f_name and f_val:
                            embed.add_field(name=f_name, value=f_val, inline=bool(f.get("inline", False)))

                await channel.send(content=prefix_content.strip() or None, embed=embed)
            else:
                full_text = f"{prefix_content}{message}"[:2000]
                await channel.send(full_text)

            self.log_activity("broadcast", f"Announcement dispatched to #{channel.name} in {channel.guild.name}")
            return web.json_response({"success": True})
        except Exception as exc:
            logger.error("Failed to dispatch broadcast: %s", exc, exc_info=True)
            return web.json_response({"error": f"Failed to send message: {exc}"}, status=500)

    async def handle_api_ai_test(self, request: web.Request) -> web.Response:
        is_auth, token = self._authenticate_request(request)
        if not is_auth or not self._verify_csrf(request, token):
            return web.json_response({"error": "Unauthorized or invalid CSRF token."}, status=403)

        try:
            body = await request.json()
            prompt = str(body.get("prompt", "")).strip()
            persona = str(body.get("persona", "default")).strip()
            temp = float(body.get("temperature", 0.7))
        except Exception:
            return web.json_response({"error": "Malformed payload."}, status=400)

        if not prompt:
            return web.json_response({"error": "Prompt cannot be empty."}, status=400)

        ai_cog = self.bot.get_cog("AI Chat")
        if not ai_cog or not hasattr(ai_cog, "gemini"):
            return web.json_response({"error": "AI cog subsystem is not currently loaded."}, status=503)

        t1 = asyncio.get_event_loop().time()
        text, model = await ai_cog.gemini.generate_with_fallback(prompt, persona=persona, temperature=temp)
        elapsed_ms = round((asyncio.get_event_loop().time() - t1) * 1000)

        if not text:
            return web.json_response({"error": "All Gemini fallback models failed or were exhausted."}, status=502)

        self.log_activity("ai", f"Web AI query processed with {model} ({elapsed_ms}ms)")
        return web.json_response({
            "success": True,
            "response": text,
            "model": model,
            "elapsed_ms": elapsed_ms,
        })

    async def handle_api_clear_memory(self, request: web.Request) -> web.Response:
        is_auth, token = self._authenticate_request(request)
        if not is_auth or not self._verify_csrf(request, token):
            return web.json_response({"error": "Unauthorized or invalid CSRF token."}, status=403)

        ai_cog = self.bot.get_cog("AI Chat")
        if ai_cog and hasattr(ai_cog, "memory"):
            count = len(ai_cog.memory)
            ai_cog.memory.clear()
            self.log_activity("memory", f"Wiped {count} conversational memory session(s)")
            return web.json_response({"success": True, "cleared_count": count})
        return web.json_response({"error": "AI Cog unavailable."}, status=503)

    async def handle_api_presence(self, request: web.Request) -> web.Response:
        is_auth, token = self._authenticate_request(request)
        if not is_auth or not self._verify_csrf(request, token):
            return web.json_response({"error": "Unauthorized or invalid CSRF token."}, status=403)

        try:
            body = await request.json()
            status_str = str(body.get("status", "online")).lower()
            activity_type_str = str(body.get("activity_type", "listening")).lower()
            text = str(body.get("text", "")).strip()[:128]
            stream_url = str(body.get("stream_url", "")).strip()
        except Exception:
            return web.json_response({"error": "Malformed payload."}, status=400)

        status_map = {
            "online": discord.Status.online,
            "idle": discord.Status.idle,
            "dnd": discord.Status.dnd,
            "invisible": discord.Status.invisible,
        }

        discord_status = status_map.get(status_str, discord.Status.online)
        name_str = text or "/help | @SkillX"

        if activity_type_str == "streaming":
            activity = discord.Streaming(
                name=name_str,
                url=stream_url or "https://www.twitch.tv/skillx",
            )
        else:
            activity_type_map = {
                "listening": discord.ActivityType.listening,
                "playing": discord.ActivityType.playing,
                "watching": discord.ActivityType.watching,
                "competing": discord.ActivityType.competing,
            }
            act_type = activity_type_map.get(activity_type_str, discord.ActivityType.listening)
            activity = discord.Activity(type=act_type, name=name_str)

        await self.bot.change_presence(activity=activity, status=discord_status)

        self.log_activity("presence", f"Presence adjusted to '{name_str}' ({status_str})")
        return web.json_response({"success": True})

    async def handle_api_moderation(self, request: web.Request) -> web.Response:
        is_auth, token = self._authenticate_request(request)
        if not is_auth or not self._verify_csrf(request, token):
            return web.json_response({"error": "Unauthorized or invalid CSRF token."}, status=403)

        try:
            body = await request.json()
            action = str(body.get("action", "")).lower()
            guild_id = int(body.get("guild_id", 0))
            user_id = int(body.get("user_id", 0))
            reason = str(body.get("reason", "Action via Web Console")).strip()
        except Exception:
            return web.json_response({"error": "Malformed payload."}, status=400)

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return web.json_response({"error": "Guild not found."}, status=404)

        member = guild.get_member(user_id)
        if not member and action not in ("ban", "warn"):
            return web.json_response({"error": "Member not found in guild."}, status=404)

        try:
            if action == "kick":
                if member.top_role >= guild.me.top_role:
                    return web.json_response({"error": "Bot role is lower than target member."}, status=403)
                await member.kick(reason=reason)
                self.log_activity("mod", f"Kicked member {member.name} ({user_id}) from {guild.name}")

            elif action == "ban":
                await guild.ban(discord.Object(id=user_id), reason=reason)
                self.log_activity("mod", f"Banned user ({user_id}) from {guild.name}")

            elif action == "timeout":
                duration_min = max(1, min(1440, int(body.get("duration", 10))))
                until = discord.utils.utcnow() + timedelta(minutes=duration_min)
                await member.timeout(until, reason=reason)
                self.log_activity("mod", f"Timed out member ({user_id}) for {duration_min}m in {guild.name}")

            elif action == "warn":
                automod_cog = self.bot.get_cog("AutoMod")
                if not automod_cog:
                    return web.json_response({"error": "AutoMod cog is not loaded."}, status=503)
                automod_cog.add_warning(guild.id, user_id, self.bot.user.id, reason)
                self.log_activity("mod", f"Warned member ({user_id}) in {guild.name}: {reason}")

            else:
                return web.json_response({"error": f"Unknown action '{action}'."}, status=400)

            return web.json_response({"success": True})
        except discord.Forbidden:
            return web.json_response({"error": "Bot lacks Discord permissions to perform this action."}, status=403)
        except Exception as exc:
            return web.json_response({"error": str(exc)}, status=500)

    async def handle_api_moderation_lockdown(self, request: web.Request) -> web.Response:
        is_auth, token = self._authenticate_request(request)
        if not is_auth or not self._verify_csrf(request, token):
            return web.json_response({"error": "Unauthorized or invalid CSRF token."}, status=403)

        try:
            body = await request.json()
            channel_id = int(body.get("channel_id", 0))
            action = str(body.get("action", "lock")).lower()
            reason = str(body.get("reason", "Lockdown via Web Console")).strip()
        except Exception:
            return web.json_response({"error": "Malformed payload."}, status=400)

        channel = self.bot.get_channel(channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            return web.json_response({"error": "Channel not found."}, status=404)

        try:
            if action == "lock":
                await channel.set_permissions(channel.guild.default_role, send_messages=False, reason=reason)
                self.log_activity("mod", f"Locked down #{channel.name} in {channel.guild.name} ({reason})")
            else:
                await channel.set_permissions(channel.guild.default_role, send_messages=None, reason=reason)
                self.log_activity("mod", f"Unlocked #{channel.name} in {channel.guild.name}")
            return web.json_response({"success": True, "action": action})
        except Exception as exc:
            return web.json_response({"error": str(exc)}, status=500)

    async def handle_api_leaderboard(self, request: web.Request) -> web.Response:
        is_auth, _ = self._authenticate_request(request)
        if not is_auth:
            return web.json_response({"error": "Unauthorized"}, status=401)

        leveling_cog = self.bot.get_cog("Leveling")
        if not leveling_cog or not hasattr(leveling_cog, "data"):
            return web.json_response([])

        entries = []
        for key, info in leveling_cog.data.items():
            try:
                guild_id_str, user_id_str = key.split("_", 1)
            except ValueError:
                continue
            entries.append({
                "guild_id": guild_id_str,
                "user_id": user_id_str,
                "xp": info.get("xp", 0),
                "level": info.get("level", 0),
                "messages": info.get("messages", 0),
            })

        entries.sort(key=lambda x: x["xp"], reverse=True)
        return web.json_response(entries[:100])

    async def handle_api_cogs(self, request: web.Request) -> web.Response:
        is_auth, _ = self._authenticate_request(request)
        if not is_auth:
            return web.json_response({"error": "Unauthorized"}, status=401)

        cog_info = []
        all_known = [
            ("AI Chat", "cogs.ai_chat", "Conversational Gemini 3.x, personas, code review & chat recaps"),
            ("Moderation", "cogs.moderation", "Server safety, kick, ban, timeout, and message purging"),
            ("Utility", "cogs.utility", "Ping diagnostics, serverinfo, userinfo, and system status"),
            ("AutoMod", "cogs.automod", "Anti-spam, invite filters, mass-mentions, warnings, and locks"),
            ("Community", "cogs.community", "Interactive button polls, giveaways, reminders, and avatar inspection"),
            ("Fun", "cogs.fun", "8ball, coinflip, dice, trivia, jokes, roasts, and interactive games"),
            ("Leveling", "cogs.leveling", "XP rewards, leveling formula, rank cards, and global leaderboards"),
            ("Server Logs", "cogs.logging_cog", "Audit channel event logging for messages, members, and voice"),
            ("Tickets", "cogs.tickets", "Channel-based private support ticket creation and transcripts"),
            ("Welcome", "cogs.welcome", "Automated member welcome cards, farewells, and join autoroles"),
        ]

        for name, ext, desc in all_known:
            cog = self.bot.get_cog(name)
            cmd_count = len(cog.get_commands()) if cog else 0
            cog_info.append({
                "name": name,
                "extension": ext,
                "description": desc,
                "loaded": cog is not None,
                "commands_count": cmd_count,
            })

        return web.json_response(cog_info)

    async def handle_api_reload_cog(self, request: web.Request) -> web.Response:
        is_auth, token = self._authenticate_request(request)
        if not is_auth or not self._verify_csrf(request, token):
            return web.json_response({"error": "Unauthorized or invalid CSRF token."}, status=403)

        try:
            body = await request.json()
            cog_ext = str(body.get("extension", "")).strip()
        except Exception:
            return web.json_response({"error": "Malformed payload."}, status=400)

        allowed_extensions = {
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
        }
        if cog_ext not in allowed_extensions:
            return web.json_response({"error": f"Extension '{cog_ext}' not permitted."}, status=400)

        try:
            await self.bot.reload_extension(cog_ext)
            self.log_activity("system", f"Reloaded extension {cog_ext}")
            return web.json_response({"success": True, "extension": cog_ext})
        except Exception as exc:
            logger.error("Failed to reload %s: %s", cog_ext, exc)
            return web.json_response({"error": str(exc)}, status=500)

    async def handle_api_reload_all_cogs(self, request: web.Request) -> web.Response:
        is_auth, token = self._authenticate_request(request)
        if not is_auth or not self._verify_csrf(request, token):
            return web.json_response({"error": "Unauthorized or invalid CSRF token."}, status=403)

        allowed_extensions = [
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

        results = []
        for ext in allowed_extensions:
            try:
                await self.bot.reload_extension(ext)
                results.append({"extension": ext, "status": "reloaded"})
            except Exception as exc:
                results.append({"extension": ext, "status": f"error: {exc}"})

        self.log_activity("system", "Reloaded all 10 bot extensions via Web Console")
        return web.json_response({"success": True, "results": results})

    # ---------------------------------------------------------
    # ADVANCED FEATURE APIS
    # ---------------------------------------------------------

    async def handle_api_ai_models(self, request: web.Request) -> web.Response:
        is_auth, _ = self._authenticate_request(request)
        if not is_auth:
            return web.json_response({"error": "Unauthorized"}, status=401)

        ai_cog = self.bot.get_cog("AI Chat")
        if not ai_cog or not hasattr(ai_cog, "gemini"):
            return web.json_response({"error": "AI cog not available"}, status=503)

        status_data = ai_cog.gemini.get_model_status()
        status_data["cache_size"] = len(getattr(ai_cog, "response_cache", {}))
        status_data["active_contexts"] = len(getattr(ai_cog, "memory", {}))
        return web.json_response(status_data)

    async def handle_api_ai_code_review(self, request: web.Request) -> web.Response:
        is_auth, token = self._authenticate_request(request)
        if not is_auth or not self._verify_csrf(request, token):
            return web.json_response({"error": "Unauthorized or invalid CSRF token."}, status=403)

        try:
            body = await request.json()
            code = str(body.get("code", "")).strip()
            language = str(body.get("language", "python")).strip()
        except Exception:
            return web.json_response({"error": "Malformed payload."}, status=400)

        if not code:
            return web.json_response({"error": "Code snippet cannot be empty."}, status=400)

        ai_cog = self.bot.get_cog("AI Chat")
        if not ai_cog or not hasattr(ai_cog, "gemini"):
            return web.json_response({"error": "AI cog subsystem is not loaded."}, status=503)

        t1 = asyncio.get_event_loop().time()
        text, model = await ai_cog.gemini.review_code(code, language)
        elapsed_ms = round((asyncio.get_event_loop().time() - t1) * 1000)

        if not text:
            return web.json_response({"error": "AI review models were exhausted or busy."}, status=502)

        self.log_activity("ai", f"Code review completed in {language} with {model} ({elapsed_ms}ms)")
        return web.json_response({
            "success": True,
            "review": text,
            "model": model,
            "elapsed_ms": elapsed_ms,
        })

    async def handle_api_ai_summarize(self, request: web.Request) -> web.Response:
        is_auth, token = self._authenticate_request(request)
        if not is_auth or not self._verify_csrf(request, token):
            return web.json_response({"error": "Unauthorized or invalid CSRF token."}, status=403)

        try:
            body = await request.json()
            text_to_sum = str(body.get("text", "")).strip()
        except Exception:
            return web.json_response({"error": "Malformed payload."}, status=400)

        if not text_to_sum:
            return web.json_response({"error": "Text cannot be empty."}, status=400)

        ai_cog = self.bot.get_cog("AI Chat")
        if not ai_cog or not hasattr(ai_cog, "gemini"):
            return web.json_response({"error": "AI cog subsystem is not loaded."}, status=503)

        t1 = asyncio.get_event_loop().time()
        summary_text, model = await ai_cog.gemini.summarize_text(text_to_sum)
        elapsed_ms = round((asyncio.get_event_loop().time() - t1) * 1000)

        if not summary_text:
            return web.json_response({"error": "AI summarization models were busy."}, status=502)

        self.log_activity("ai", f"Text summary generated with {model} ({elapsed_ms}ms)")
        return web.json_response({
            "success": True,
            "summary": summary_text,
            "model": model,
            "elapsed_ms": elapsed_ms,
        })

    async def handle_api_ai_memory(self, request: web.Request) -> web.Response:
        is_auth, _ = self._authenticate_request(request)
        if not is_auth:
            return web.json_response({"error": "Unauthorized"}, status=401)

        ai_cog = self.bot.get_cog("AI Chat")
        if not ai_cog or not hasattr(ai_cog, "memory"):
            return web.json_response([])

        memory_list = []
        for uid, turns in ai_cog.memory.items():
            persona = ai_cog.user_personas.get(uid, "default")
            last_prompt = ""
            for item in reversed(turns):
                if item.get("role") == "user" and item.get("parts"):
                    last_prompt = item["parts"][0].get("text", "")[:80]
                    break
            memory_list.append({
                "user_id": str(uid),
                "turns_count": len(turns),
                "persona": persona,
                "preview": last_prompt or "Active conversation",
            })
        return web.json_response(memory_list)

    async def handle_api_ai_clear_user_memory(self, request: web.Request) -> web.Response:
        is_auth, token = self._authenticate_request(request)
        if not is_auth or not self._verify_csrf(request, token):
            return web.json_response({"error": "Unauthorized or invalid CSRF token."}, status=403)

        try:
            body = await request.json()
            user_id = int(body.get("user_id", 0))
        except Exception:
            return web.json_response({"error": "Malformed payload."}, status=400)

        ai_cog = self.bot.get_cog("AI Chat")
        if ai_cog and hasattr(ai_cog, "memory"):
            had = ai_cog.memory.pop(user_id, None) is not None
            self.log_activity("memory", f"Cleared conversation memory for user {user_id}")
            return web.json_response({"success": True, "cleared": had})
        return web.json_response({"error": "AI cog not available."}, status=503)

    async def handle_api_automod_clear_warnings(self, request: web.Request) -> web.Response:
        is_auth, token = self._authenticate_request(request)
        if not is_auth or not self._verify_csrf(request, token):
            return web.json_response({"error": "Unauthorized or invalid CSRF token."}, status=403)

        try:
            body = await request.json()
            guild_id = int(body.get("guild_id", 0))
            user_id = int(body.get("user_id", 0))
        except Exception:
            return web.json_response({"error": "Malformed payload."}, status=400)

        automod_cog = self.bot.get_cog("AutoMod")
        if not automod_cog:
            return web.json_response({"error": "AutoMod cog is not loaded."}, status=503)

        count = automod_cog.clear_warnings(guild_id, user_id)
        self.log_activity("mod", f"Cleared {count} warnings for user {user_id} in guild {guild_id}")
        return web.json_response({"success": True, "cleared_count": count})

    async def handle_api_leveling_adjust_xp(self, request: web.Request) -> web.Response:
        is_auth, token = self._authenticate_request(request)
        if not is_auth or not self._verify_csrf(request, token):
            return web.json_response({"error": "Unauthorized or invalid CSRF token."}, status=403)

        try:
            body = await request.json()
            guild_id = int(body.get("guild_id", 0))
            user_id = int(body.get("user_id", 0))
            amount = int(body.get("xp", 0))
            action = str(body.get("action", "add")).lower()
        except Exception:
            return web.json_response({"error": "Malformed payload."}, status=400)

        leveling_cog = self.bot.get_cog("Leveling")
        if not leveling_cog:
            return web.json_response({"error": "Leveling cog not loaded."}, status=503)

        from cogs.leveling import level_from_xp
        key = f"{guild_id}_{user_id}"
        if key not in leveling_cog.data:
            leveling_cog.data[key] = {"xp": 0, "level": 0, "messages": 0}

        curr_xp = leveling_cog.data[key].get("xp", 0)
        if action == "set":
            new_xp = max(0, amount)
        elif action == "deduct":
            new_xp = max(0, curr_xp - amount)
        else:
            new_xp = max(0, curr_xp + amount)

        leveling_cog.data[key]["xp"] = new_xp
        leveling_cog.data[key]["level"] = level_from_xp(new_xp)
        leveling_cog._save()

        self.log_activity("system", f"Adjusted XP for user {user_id} in guild {guild_id}: now {new_xp} XP (Lvl {leveling_cog.data[key]['level']})")
        return web.json_response({"success": True, "new_xp": new_xp, "new_level": leveling_cog.data[key]["level"]})

    async def handle_api_welcome_config_get(self, request: web.Request) -> web.Response:
        is_auth, _ = self._authenticate_request(request)
        if not is_auth:
            return web.json_response({"error": "Unauthorized"}, status=401)

        welcome_cog = self.bot.get_cog("Welcome")
        if not welcome_cog or not hasattr(welcome_cog, "config"):
            return web.json_response({})
        return web.json_response(welcome_cog.config)

    async def handle_api_welcome_config_post(self, request: web.Request) -> web.Response:
        is_auth, token = self._authenticate_request(request)
        if not is_auth or not self._verify_csrf(request, token):
            return web.json_response({"error": "Unauthorized or invalid CSRF token."}, status=403)

        try:
            body = await request.json()
            guild_id_str = str(body.get("guild_id", "")).strip()
            welcome_ch = body.get("welcome_channel")
            welcome_msg = str(body.get("welcome_message", "")).strip()
            goodbye_ch = body.get("goodbye_channel")
            goodbye_msg = str(body.get("goodbye_message", "")).strip()
            autorole_id = body.get("autorole_id")
        except Exception:
            return web.json_response({"error": "Malformed payload."}, status=400)

        welcome_cog = self.bot.get_cog("Welcome")
        if not welcome_cog:
            return web.json_response({"error": "Welcome cog is not loaded."}, status=503)

        if guild_id_str not in welcome_cog.config:
            welcome_cog.config[guild_id_str] = {}

        welcome_cog.config[guild_id_str]["welcome_channel"] = int(welcome_ch) if welcome_ch and str(welcome_ch).isdigit() else None
        welcome_cog.config[guild_id_str]["welcome_message"] = welcome_msg or "Welcome to **{server}**, {user.mention}!"
        welcome_cog.config[guild_id_str]["goodbye_channel"] = int(goodbye_ch) if goodbye_ch and str(goodbye_ch).isdigit() else None
        welcome_cog.config[guild_id_str]["goodbye_message"] = goodbye_msg or "**{user}** has left **{server}**."
        welcome_cog.config[guild_id_str]["autorole_id"] = int(autorole_id) if autorole_id and str(autorole_id).isdigit() else None
        welcome_cog._save_config()

        self.log_activity("system", f"Updated Welcome & Autorole configuration for guild {guild_id_str}")
        return web.json_response({"success": True})

    async def handle_api_tickets_config_get(self, request: web.Request) -> web.Response:
        is_auth, _ = self._authenticate_request(request)
        if not is_auth:
            return web.json_response({"error": "Unauthorized"}, status=401)

        tickets_cog = self.bot.get_cog("Tickets")
        t_config = getattr(tickets_cog, "config", {}) if tickets_cog else {}

        active_tickets = []
        for guild in self.bot.guilds:
            for ch in guild.text_channels:
                if ch.name.startswith("ticket-"):
                    active_tickets.append({
                        "channel_id": str(ch.id),
                        "channel_name": ch.name,
                        "guild_id": str(guild.id),
                        "guild_name": guild.name,
                        "topic": ch.topic or "Support Ticket",
                        "created_at": ch.created_at.strftime("%Y-%m-%d %H:%M:%S") if ch.created_at else "",
                    })

        return web.json_response({
            "config": t_config,
            "active_tickets": active_tickets,
        })

    async def handle_api_tickets_close(self, request: web.Request) -> web.Response:
        is_auth, token = self._authenticate_request(request)
        if not is_auth or not self._verify_csrf(request, token):
            return web.json_response({"error": "Unauthorized or invalid CSRF token."}, status=403)

        try:
            body = await request.json()
            channel_id = int(body.get("channel_id", 0))
            reason = str(body.get("reason", "Closed via Web Console")).strip()
        except Exception:
            return web.json_response({"error": "Malformed payload."}, status=400)

        channel = self.bot.get_channel(channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            return web.json_response({"error": "Ticket channel not found."}, status=404)

        try:
            name = channel.name
            guild_name = channel.guild.name
            await channel.delete(reason=reason)
            self.log_activity("mod", f"Closed support ticket channel #{name} in {guild_name}")
            return web.json_response({"success": True})
        except Exception as exc:
            return web.json_response({"error": str(exc)}, status=500)

    async def handle_api_tickets_deploy(self, request: web.Request) -> web.Response:
        is_auth, token = self._authenticate_request(request)
        if not is_auth or not self._verify_csrf(request, token):
            return web.json_response({"error": "Unauthorized or invalid CSRF token."}, status=403)

        try:
            body = await request.json()
            channel_id = int(body.get("channel_id", 0))
            title = str(body.get("title", "🎫 Support Tickets")).strip()
            desc = str(body.get("description", "Click the button below to create a private support ticket.")).strip()
        except Exception:
            return web.json_response({"error": "Malformed payload."}, status=400)

        channel = self.bot.get_channel(channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            return web.json_response({"error": "Target channel not found."}, status=404)

        from cogs.tickets import TicketPanelView
        embed = discord.Embed(
            title=title,
            description=desc,
            color=0x5865F2,
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_footer(text="SkillX Support Desk")
        try:
            await channel.send(embed=embed, view=TicketPanelView())
            self.log_activity("system", f"Deployed ticket panel to #{channel.name} in {channel.guild.name}")
            return web.json_response({"success": True})
        except Exception as exc:
            return web.json_response({"error": str(exc)}, status=500)

    async def handle_api_logging_config_get(self, request: web.Request) -> web.Response:
        is_auth, _ = self._authenticate_request(request)
        if not is_auth:
            return web.json_response({"error": "Unauthorized"}, status=401)

        logs_cog = self.bot.get_cog("Server Logs")
        mapping = getattr(logs_cog, "log_channels", {}) if logs_cog else {}
        return web.json_response(mapping)

    async def handle_api_logging_config_post(self, request: web.Request) -> web.Response:
        is_auth, token = self._authenticate_request(request)
        if not is_auth or not self._verify_csrf(request, token):
            return web.json_response({"error": "Unauthorized or invalid CSRF token."}, status=403)

        try:
            body = await request.json()
            guild_id_str = str(body.get("guild_id", "")).strip()
            channel_id = body.get("channel_id")
        except Exception:
            return web.json_response({"error": "Malformed payload."}, status=400)

        logs_cog = self.bot.get_cog("Server Logs")
        if not logs_cog:
            return web.json_response({"error": "Server Logs cog not loaded."}, status=503)

        if channel_id and str(channel_id).isdigit():
            logs_cog.log_channels[guild_id_str] = int(channel_id)
        else:
            logs_cog.log_channels.pop(guild_id_str, None)

        logs_cog._save()
        self.log_activity("system", f"Updated audit log channel for guild {guild_id_str}")
        return web.json_response({"success": True})

    async def handle_api_community_poll(self, request: web.Request) -> web.Response:
        is_auth, token = self._authenticate_request(request)
        if not is_auth or not self._verify_csrf(request, token):
            return web.json_response({"error": "Unauthorized or invalid CSRF token."}, status=403)

        try:
            body = await request.json()
            channel_id = int(body.get("channel_id", 0))
            question = str(body.get("question", "")).strip()
            options = [str(opt).strip() for opt in body.get("options", []) if str(opt).strip()]
        except Exception:
            return web.json_response({"error": "Malformed payload."}, status=400)

        if not question or len(options) < 2:
            return web.json_response({"error": "Question and at least 2 options required."}, status=400)

        channel = self.bot.get_channel(channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            return web.json_response({"error": "Target channel not found."}, status=404)

        from cogs.community import PollView
        view = PollView(question, options[:5], author_id=self.bot.user.id if self.bot.user else 0)
        try:
            embed = view.build_embed()
            msg = await channel.send(embed=embed, view=view)
            view.message = msg
            self.log_activity("broadcast", f"Dispatched poll '{question[:40]}' to #{channel.name}")
            return web.json_response({"success": True})
        except Exception as exc:
            return web.json_response({"error": str(exc)}, status=500)

    async def handle_api_community_giveaway(self, request: web.Request) -> web.Response:
        is_auth, token = self._authenticate_request(request)
        if not is_auth or not self._verify_csrf(request, token):
            return web.json_response({"error": "Unauthorized or invalid CSRF token."}, status=403)

        try:
            body = await request.json()
            channel_id = int(body.get("channel_id", 0))
            prize = str(body.get("prize", "")).strip()
            duration_sec = int(body.get("duration_seconds", 60))
            winners_count = max(1, min(10, int(body.get("winners", 1))))
        except Exception:
            return web.json_response({"error": "Malformed payload."}, status=400)

        if not prize:
            return web.json_response({"error": "Prize cannot be empty."}, status=400)

        channel = self.bot.get_channel(channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            return web.json_response({"error": "Channel not found."}, status=404)

        community_cog = self.bot.get_cog("Community")
        if not community_cog:
            return web.json_response({"error": "Community cog not loaded."}, status=503)

        from cogs.community import GiveawayView
        end_time = datetime.now(timezone.utc) + timedelta(seconds=duration_sec)
        embed = discord.Embed(
            title=f"🎉 GIVEAWAY: {prize}",
            description=(
                f"React by clicking the button below to enter!\n\n"
                f"• **Winners:** {winners_count}\n"
                f"• **Ends:** <t:{int(end_time.timestamp())}:R>\n"
                f"• **Hosted by:** Web Console"
            ),
            color=0x5865F2,
            timestamp=end_time,
        )
        embed.set_footer(text="Ends at")
        view = GiveawayView(prize, self.bot.user.id if self.bot.user else 0, winners_count)
        try:
            msg = await channel.send(embed=embed, view=view)
            view.message = msg
            self.bot.loop.create_task(community_cog._run_giveaway_timer(duration_sec, view, msg, prize, winners_count, channel))
            self.log_activity("broadcast", f"Launched giveaway for '{prize}' in #{channel.name}")
            return web.json_response({"success": True})
        except Exception as exc:
            return web.json_response({"error": str(exc)}, status=500)


async def start_dashboard(bot, host: str = "0.0.0.0", port: int = 8080, password: str = "", secret_key: str = ""):
    """Launches the aiohttp web dashboard application runner."""
    dashboard = DashboardApp(bot, password, secret_key)
    runner = web.AppRunner(dashboard.app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    logger.info("🌐 Web Dashboard is live at http://%s:%d", "localhost" if host == "0.0.0.0" else host, port)
    return runner
