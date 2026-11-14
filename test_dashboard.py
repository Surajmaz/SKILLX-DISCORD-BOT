"""Comprehensive Security and Functional Tests for the SkillX Web Dashboard."""

import asyncio
import unittest
from unittest.mock import MagicMock
from yarl import URL
import aiohttp
from aiohttp import web

from dashboard.app import DashboardApp
from dashboard.security import DashboardSecurityManager


class TestDashboardSecurity(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.mock_bot = MagicMock()
        self.mock_bot.guilds = []
        self.mock_bot.latency = 0.045
        self.mock_bot.cogs = {"AI Chat": MagicMock(), "Utility": MagicMock(), "Moderation": MagicMock()}

        self.password = "SuperSecretPassword123"
        self.secret_key = "test_secret_key_abcdef123456"

        self.dashboard = DashboardApp(self.mock_bot, self.password, self.secret_key)
        self.runner = web.AppRunner(self.dashboard.app)
        await self.runner.setup()
        self.port = 8999
        self.site = web.TCPSite(self.runner, "127.0.0.1", self.port)
        await self.site.start()
        self.base_url = f"http://127.0.0.1:{self.port}"

    async def asyncTearDown(self):
        await self.runner.cleanup()

    async def test_security_headers_present(self):
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.base_url}/login") as resp:
                self.assertEqual(resp.status, 200)
                self.assertEqual(resp.headers.get("X-Frame-Options"), "DENY")
                self.assertEqual(resp.headers.get("X-Content-Type-Options"), "nosniff")
                self.assertIn("default-src", resp.headers.get("Content-Security-Policy", ""))

    async def test_unauthenticated_redirect(self):
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.base_url}/", allow_redirects=False) as resp:
                self.assertEqual(resp.status, 302)
                self.assertEqual(resp.headers.get("Location"), "/login")

    async def test_login_flow_and_authenticated_access(self):
        async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True)) as session:
            # 1. Failed login
            async with session.post(f"{self.base_url}/api/login", json={"password": "wrong"}) as resp:
                self.assertEqual(resp.status, 401)
                data = await resp.json()
                self.assertFalse(data["success"])

            # 2. Successful login
            async with session.post(f"{self.base_url}/api/login", json={"password": self.password}) as resp:
                self.assertEqual(resp.status, 200)
                data = await resp.json()
                self.assertTrue(data["success"])
                cookies = session.cookie_jar.filter_cookies(URL(f"{self.base_url}/"))
                self.assertIn("skillx_session", cookies)

            # 3. Access dashboard index
            async with session.get(f"{self.base_url}/") as resp:
                self.assertEqual(resp.status, 200)
                html = await resp.text()
                self.assertIn("SkillX Bot Control Console", html)

            # 4. Fetch live stats
            async with session.get(f"{self.base_url}/api/stats") as resp:
                self.assertEqual(resp.status, 200)
                stats = await resp.json()
                self.assertEqual(stats["latency_ms"], 45)
                self.assertIn("system", stats)

    async def test_brute_force_rate_limiting(self):
        async with aiohttp.ClientSession() as session:
            for _ in range(5):
                await session.post(f"{self.base_url}/api/login", json={"password": "bad"})
            # 6th attempt should be blocked with 429
            async with session.post(f"{self.base_url}/api/login", json={"password": "bad"}) as resp:
                self.assertEqual(resp.status, 429)
                data = await resp.json()
                self.assertIn("Too many failed attempts", data["error"])


if __name__ == "__main__":
    unittest.main()
