"""SkillX Web Dashboard Application.

Hosts asynchronous management endpoints and an interactive web GUI
directly within the Discord bot's event loop via aiohttp.web.
"""

import asyncio
from datetime import datetime, timezone
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
        if len(self.activity_logs) > 60:
            self.activity_logs.pop(0)

    def _setup_routes(self) -> None:
        self.app.router.add_get("/", self.handle_index)
        self.app.router.add_get("/login", self.handle_login_page)
        self.app.router.add_post("/api/login", self.handle_api_login)
        self.app.router.add_post("/api/logout", self.handle_api_logout)

        # Authenticated APIs
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
        self.app.router.add_post("/api/cogs/reload", self.handle_api_reload_cog)

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
            roles = [{"id": str(r.id), "name": r.name, "color": f"#{r.color.value:06x}"} for r in reversed(g.roles) if not r.is_default()][:15]

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

        return web.json_response(list(reversed(infractions_data))[:50])

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
                # Interpret as hex if 6 or fewer hex chars or contains hex letters
                color_int = max(0, min(0xFFFFFF, int(c_str, 16)))
            except ValueError:
                try:
                    color_int = max(0, min(0xFFFFFF, int(c_str, 10)))
                except ValueError:
                    color_int = 0x5865F2

        try:
            if use_embed or title:
                embed = discord.Embed(
                    title=f"📢 {title[:256]}" if title else None,
                    description=message[:4096],
                    color=color_int,
                    timestamp=datetime.now(timezone.utc),
                )
                embed.set_footer(text="Broadcasted via SkillX Web Console")
                await channel.send(embed=embed)
            else:
                await channel.send(message[:2000])

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
        except Exception:
            return web.json_response({"error": "Malformed payload."}, status=400)

        status_map = {
            "online": discord.Status.online,
            "idle": discord.Status.idle,
            "dnd": discord.Status.dnd,
        }
        activity_type_map = {
            "listening": discord.ActivityType.listening,
            "playing": discord.ActivityType.playing,
            "watching": discord.ActivityType.watching,
            "competing": discord.ActivityType.competing,
        }

        discord_status = status_map.get(status_str, discord.Status.online)
        activity_type = activity_type_map.get(activity_type_str, discord.ActivityType.listening)

        activity = discord.Activity(type=activity_type, name=text or "/help | @SkillX")
        await self.bot.change_presence(activity=activity, status=discord_status)

        self.log_activity("presence", f"Presence adjusted to '{text}' ({status_str})")
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
        if not member and action != "ban":
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
            })

        entries.sort(key=lambda x: x["xp"], reverse=True)
        return web.json_response(entries[:50])

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


async def start_dashboard(bot, host: str = "0.0.0.0", port: int = 8080, password: str = "", secret_key: str = ""):
    """Launches the aiohttp web dashboard application runner."""
    dashboard = DashboardApp(bot, password, secret_key)
    runner = web.AppRunner(dashboard.app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    logger.info("🌐 Web Dashboard is live at http://%s:%d", "localhost" if host == "0.0.0.0" else host, port)
    return runner
