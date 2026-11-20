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

            # 5. Fetch cogs directory
            async with session.get(f"{self.base_url}/api/cogs") as resp:
                self.assertEqual(resp.status, 200)
                cogs = await resp.json()
                self.assertIsInstance(cogs, list)
                self.assertGreater(len(cogs), 0)

            # 6. Fetch leaderboard
            async with session.get(f"{self.base_url}/api/leaderboard") as resp:
                self.assertEqual(resp.status, 200)
                lb = await resp.json()
                self.assertIsInstance(lb, list)

            # 7. Fetch AI Models Fleet
            mock_ai = MagicMock()
            mock_ai.gemini.get_model_status.return_value = {
                "total_models": 9,
                "healthy_models": 9,
                "models": [{"model": "gemini-3.5-flash-lite", "status": "ONLINE"}],
            }
            mock_ai.memory = {}
            mock_ai.user_personas = {}
            self.mock_bot.get_cog.side_effect = lambda name: mock_ai if name == "AI Chat" else None

            async with session.get(f"{self.base_url}/api/ai/models") as resp:
                self.assertEqual(resp.status, 200)
                ai_data = await resp.json()
                self.assertEqual(ai_data["total_models"], 9)

            # 8. Fetch AI Memory List
            async with session.get(f"{self.base_url}/api/ai/memory") as resp:
                self.assertEqual(resp.status, 200)
                mem = await resp.json()
                self.assertIsInstance(mem, list)

            # 9. Fetch Welcome Config
            async with session.get(f"{self.base_url}/api/welcome/config") as resp:
                self.assertEqual(resp.status, 200)

            # 10. Fetch Tickets Config
            async with session.get(f"{self.base_url}/api/tickets/config") as resp:
                self.assertEqual(resp.status, 200)
                t_data = await resp.json()
                self.assertIn("active_tickets", t_data)

            # 11. Fetch Logging Config
            async with session.get(f"{self.base_url}/api/logging/config") as resp:
                self.assertEqual(resp.status, 200)

    async def test_stress_test_and_auto_heal_routes(self):
        async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True)) as session:
            # Login
            login_resp = await session.post(f"{self.base_url}/api/login", json={"password": self.password})
            self.assertEqual(login_resp.status, 200)

            cookies = session.cookie_jar.filter_cookies(URL(f"{self.base_url}/"))
            session_token = cookies["skillx_session"].value
            csrf_token = self.dashboard.security.generate_csrf_token(session_token)

            # 1. Unauthenticated /api/stress-test/last-report
            async with aiohttp.ClientSession() as unauth_session:
                async with unauth_session.get(f"{self.base_url}/api/stress-test/last-report") as resp:
                    self.assertEqual(resp.status, 401)

            # 2. Stress test without CSRF
            async with session.post(f"{self.base_url}/api/stress-test/run", json={"mode": "full"}) as resp:
                self.assertEqual(resp.status, 403)

            # 3. Stress test with CSRF (low intensity full test)
            headers = {"X-CSRF-Token": csrf_token}
            async with session.post(
                f"{self.base_url}/api/stress-test/run",
                headers=headers,
                json={"mode": "full", "intensity": "low", "auto_heal": True},
            ) as resp:
                self.assertEqual(resp.status, 200)
                data = await resp.json()
                self.assertTrue(data["success"])
                report = data["report"]
                self.assertIn("resilience_score", report)
                self.assertIn("subsystems", report)
                self.assertIn("event_loop", report["subsystems"])
                self.assertIn("database_io", report["subsystems"])
                self.assertIn("remediation", report)
                self.assertIsNotNone(report["remediation"])

            # 4. Specific subsystem tests
            for mode in ["loop", "io", "web", "ai"]:
                async with session.post(
                    f"{self.base_url}/api/stress-test/run",
                    headers=headers,
                    json={"mode": mode, "intensity": "low"},
                ) as resp:
                    self.assertEqual(resp.status, 200)
                    data = await resp.json()
                    self.assertTrue(data["success"])
                    self.assertEqual(data["report"]["mode"], mode)
                    self.assertIn("result", data["report"])

            # 5. Last report endpoint
            async with session.get(f"{self.base_url}/api/stress-test/last-report") as resp:
                self.assertEqual(resp.status, 200)
                last = await resp.json()
                self.assertIn("resilience_score", last)

            # 6. Auto-heal without CSRF
            async with session.post(f"{self.base_url}/api/auto-heal/run") as resp:
                self.assertEqual(resp.status, 403)

            # 7. Auto-heal with CSRF
            async with session.post(f"{self.base_url}/api/auto-heal/run", headers=headers) as resp:
                self.assertEqual(resp.status, 200)
                data = await resp.json()
                self.assertTrue(data["success"])
                self.assertEqual(data["report"]["status"], "HEALTHY")
                self.assertIn("actions_taken", data["report"])

    async def test_brute_force_rate_limiting(self):
        async with aiohttp.ClientSession() as session:
            for _ in range(5):
                await session.post(f"{self.base_url}/api/login", json={"password": "bad"})
            # 6th attempt should be blocked with 429
            async with session.post(f"{self.base_url}/api/login", json={"password": "bad"}) as resp:
                self.assertEqual(resp.status, 429)
                data = await resp.json()
                self.assertIn("Too many failed attempts", data["error"])


class TestSystemStressTester(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.mock_bot = MagicMock()
        self.mock_ai = MagicMock()
        self.mock_ai.gemini.get_model_status.return_value = {
            "total_models": 9,
            "healthy_models": 9,
            "models": [],
        }
        self.mock_ai.gemini.model_chain = ["gemini-3.5-flash-lite"]
        self.mock_ai.gemini.model_cooldowns = {}
        self.mock_ai.response_cache = {"key1": ("prompt", "answer", 0.0)}
        self.mock_ai.memory = {123: []}
        self.mock_bot.get_cog.side_effect = lambda n: self.mock_ai if n == "AI Chat" else None
        self.mock_dashboard = MagicMock()
        self.mock_dashboard.activity_logs = ["log1"] * 70

    async def test_auto_healing_engine(self):
        from stress_test import AutoHealingEngine
        rep = await AutoHealingEngine.run_remediation(self.mock_bot, self.mock_dashboard)
        self.assertEqual(rep["status"], "HEALTHY")
        self.assertGreater(len(rep["actions_taken"]), 0)
        self.assertEqual(rep["pruned_cache_items"], 1)
        self.assertEqual(rep["pruned_memory_contexts"], 1)
        self.assertLessEqual(len(self.mock_dashboard.activity_logs), 60)

    async def test_system_stress_tester_subsystems(self):
        from stress_test import SystemStressTester
        tester = SystemStressTester(self.mock_bot, self.mock_dashboard)

        # Loop stress
        loop_res = await tester.run_event_loop_stress(cycles=20)
        self.assertIn("avg_jitter_ms", loop_res)
        self.assertIn(loop_res["status"], ["EXCELLENT", "GOOD", "DEGRADED"])

        # IO stress
        io_res = await tester.run_io_stress(operations=20)
        self.assertIn("iops", io_res)
        self.assertEqual(io_res["operations"], 20)

        # Web API stress
        web_res = await tester.run_web_api_stress(requests_count=10, concurrency=2)
        self.assertIn("rps", web_res)
        self.assertEqual(web_res["total_requests"], 10)

        # AI Fleet stress
        ai_res = await tester.run_ai_fleet_stress()
        self.assertEqual(ai_res["healthy_models"], 9)
        self.assertEqual(ai_res["total_models"], 9)

        # Full stress test with auto-healing
        full_report = await tester.run_full_stress_test(intensity="low", auto_heal=True)
        self.assertIn("resilience_score", full_report)
        self.assertIn("remediation", full_report)
        self.assertIsNotNone(full_report["remediation"])
        self.assertIsNotNone(tester.last_report)


if __name__ == "__main__":
    unittest.main()
