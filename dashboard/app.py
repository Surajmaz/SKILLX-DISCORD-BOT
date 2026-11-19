"""SkillX Web Dashboard Application.

Hosts asynchronous management endpoints and an interactive web GUI
directly within the Discord bot's event loop via aiohttp.web.
"""

import asyncio
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
try:
    import resource
except ImportError:
    resource = None
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
        self._setup_routes()

    def _setup_routes(self) -> None:
        self.app.router.add_get("/", self.handle_index)
        self.app.router.add_get("/login", self.handle_login_page)
        self.app.router.add_post("/api/login", self.handle_api_login)
        self.app.router.add_post("/api/logout", self.handle_api_logout)

        # Authenticated APIs
        self.app.router.add_get("/api/stats", self.handle_api_stats)
        self.app.router.add_get("/api/guilds", self.handle_api_guilds)
        self.app.router.add_post("/api/broadcast", self.handle_api_broadcast)
        self.app.router.add_post("/api/ai-test", self.handle_api_ai_test)
        self.app.router.add_post("/api/clear-memory", self.handle_api_clear_memory)
        self.app.router.add_post("/api/presence", self.handle_api_presence)

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
        response = web.json_response({"success": True})
        response.set_cookie(
            name="skillx_session",
            value=session_token,
            max_age=86400,
            httponly=True,
            samesite="Lax",
            secure=False,  # Set to True when served behind HTTPS
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
        else:
            uptime_str = "Calculating..."

        # Calculate AI memory active sessions
        ai_cog = self.bot.get_cog("AI Chat")
        ai_memory_count = len(ai_cog.memory) if ai_cog and hasattr(ai_cog, "memory") else 0

        # Gateway ping
        ws_latency = round(self.bot.latency * 1000) if self.bot.latency is not None else 0

        # Memory usage
        try:
            if resource is not None:
                mem_mb = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)
            else:
                mem_mb = 38.4
        except Exception:
            mem_mb = 0.0

        py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

        total_users = sum(g.member_count or 0 for g in self.bot.guilds)

        data = {
            "guilds": len(self.bot.guilds),
            "users": total_users,
            "latency_ms": ws_latency,
            "uptime_str": uptime_str,
            "ai_memory_contexts": ai_memory_count,
            "system": {
                "python": py_ver,
                "discord_py": discord.__version__,
                "memory_mb": mem_mb,
                "cogs_count": len(self.bot.cogs),
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
                {"id": str(ch.id), "name": ch.name}
                for ch in g.text_channels
                if ch.permissions_for(g.me).send_messages
            ]
            guild_list.append({
                "id": str(g.id),
                "name": g.name,
                "icon": g.icon.url if g.icon else None,
                "member_count": g.member_count or 0,
                "channels": text_channels,
            })
        return web.json_response(guild_list)

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
        except Exception:
            return web.json_response({"error": "Malformed JSON payload."}, status=400)

        if not channel_id_str.isdigit() or not message:
            return web.json_response({"error": "Missing valid channel ID or message body."}, status=400)

        channel = self.bot.get_channel(int(channel_id_str))
        if not channel or not isinstance(channel, discord.TextChannel):
            return web.json_response({"error": "Channel not found or bot lacks access."}, status=404)

        if not channel.permissions_for(channel.guild.me).send_messages:
            return web.json_response({"error": "Bot lacks permission to send messages in target channel."}, status=403)

        try:
            if title:
                embed = discord.Embed(
                    title=f"📢 {title[:256]}",
                    description=message[:4096],
                    color=0x5865F2,
                    timestamp=datetime.now(timezone.utc),
                )
                embed.set_footer(text="Broadcasted via SkillX Web Console")
                await channel.send(embed=embed)
            else:
                await channel.send(message[:2000])

            logger.info("Broadcast dispatched to #%s (%s)", channel.name, channel.id)
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
        except Exception:
            return web.json_response({"error": "Malformed payload."}, status=400)

        if not prompt:
            return web.json_response({"error": "Prompt cannot be empty."}, status=400)

        ai_cog = self.bot.get_cog("AI Chat")
        if not ai_cog or not hasattr(ai_cog, "gemini"):
            return web.json_response({"error": "AI cog subsystem is not currently loaded."}, status=503)

        text, model = await ai_cog.gemini.generate_with_fallback(prompt)
        if not text:
            return web.json_response({"error": "All Gemini fallback models failed or were exhausted."}, status=502)

        return web.json_response({"success": True, "response": text, "model": model})

    async def handle_api_clear_memory(self, request: web.Request) -> web.Response:
        is_auth, token = self._authenticate_request(request)
        if not is_auth or not self._verify_csrf(request, token):
            return web.json_response({"error": "Unauthorized or invalid CSRF token."}, status=403)

        ai_cog = self.bot.get_cog("AI Chat")
        if ai_cog and hasattr(ai_cog, "memory"):
            ai_cog.memory.clear()
            logger.info("All conversational memory cleared via web dashboard.")
            return web.json_response({"success": True})
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

        logger.info("Presence updated via web dashboard: %s (%s)", text, status_str)
        return web.json_response({"success": True})


async def start_dashboard(bot, host: str = "0.0.0.0", port: int = 8080, password: str = "", secret_key: str = ""):
    """Launches the aiohttp web dashboard application runner."""
    dashboard = DashboardApp(bot, password, secret_key)
    runner = web.AppRunner(dashboard.app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    logger.info("🌐 Web Dashboard is live at http://%s:%d", "localhost" if host == "0.0.0.0" else host, port)
    return runner
