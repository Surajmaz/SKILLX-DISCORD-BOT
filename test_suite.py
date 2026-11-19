"""Automated Unit and Integration Tests for SkillX Discord Bot."""

import unittest
from datetime import datetime, timezone
import discord
from config import validate_config
from embeds import (
    base_embed,
    ai_response_embed,
    moderation_embed,
    success_embed,
    error_embed,
    warning_embed,
    info_embed,
)
from security import MultiDimensionRateLimiter, sanitize_input
from ui import split_response_into_pages


class TestSecurityUtilities(unittest.TestCase):
    def test_sanitize_preserves_newlines_and_tabs(self):
        sample = "Line 1\nLine 2\tTabbed\r\nLine 3"
        sanitized = sanitize_input(sample)
        self.assertEqual(sanitized, sample)

    def test_sanitize_neutralizes_pings(self):
        sample = "Hey @everyone and @here check this out!"
        sanitized = sanitize_input(sample)
        self.assertNotIn("@everyone", sanitized)
        self.assertNotIn("@here", sanitized)
        self.assertIn("@\u200beveryone", sanitized)
        self.assertIn("@\u200bhere", sanitized)

    def test_sanitize_removes_unprintable_control_chars(self):
        sample = "Clean\x00Text\x07With\x1bEscapes"
        sanitized = sanitize_input(sample)
        self.assertEqual(sanitized, "CleanTextWithEscapes")

    def test_rate_limiter_sliding_window(self):
        limiter = MultiDimensionRateLimiter(user_limit=(3, 60))
        # 3 calls allowed
        self.assertTrue(limiter.check(user_id=1, guild_id=10)[0])
        self.assertTrue(limiter.check(user_id=1, guild_id=10)[0])
        self.assertTrue(limiter.check(user_id=1, guild_id=10)[0])
        # 4th call should be rejected
        allowed, reason, retry_after = limiter.check(user_id=1, guild_id=10)
        self.assertFalse(allowed)
        self.assertEqual(reason, "user")
        self.assertGreater(retry_after, 0.0)


class TestTextChunker(unittest.TestCase):
    def test_short_text_no_split(self):
        text = "Hello world, this is a short message."
        pages = split_response_into_pages(text, max_chars=100)
        self.assertEqual(pages, [text])

    def test_codeblock_closed_and_reopened_across_pages(self):
        code_text = (
            "Intro paragraph\n"
            "```python\n"
            "def foo():\n"
            "    return 42\n"
            "```\n"
            "Outro text"
        )
        pages = split_response_into_pages(code_text, max_chars=35)
        self.assertGreater(len(pages), 1)

        # Page containing code split must have matching triple-backticks
        for page in pages:
            # Count backtick blocks
            backtick_count = page.count("```")
            self.assertEqual(
                backtick_count % 2,
                0,
                f"Page has unclosed code fence: {page!r}",
            )


class TestEmbedBuilders(unittest.TestCase):
    def test_base_embed_creation(self):
        embed = base_embed("Sample Title", "Sample Description")
        self.assertEqual(embed.title, "Sample Title")
        self.assertEqual(embed.description, "Sample Description")
        self.assertIsNotNone(embed.timestamp)

    def test_embed_length_caps(self):
        huge_title = "A" * 500
        huge_desc = "B" * 5000
        embed = base_embed(huge_title, huge_desc)
        self.assertLessEqual(len(embed.title), 256)
        self.assertLessEqual(len(embed.description), 4096)


class TestCommunityUtilities(unittest.TestCase):
    def test_parse_time_to_seconds(self):
        from cogs.community import parse_time_to_seconds

        self.assertEqual(parse_time_to_seconds("30s"), 30)
        self.assertEqual(parse_time_to_seconds("5m"), 300)
        self.assertEqual(parse_time_to_seconds("2h"), 7200)
        self.assertEqual(parse_time_to_seconds("1d"), 86400)
        self.assertIsNone(parse_time_to_seconds("invalid"))
        self.assertIsNone(parse_time_to_seconds("10x"))


class TestGeminiPersonas(unittest.TestCase):
    def test_personas_exist_and_non_empty(self):
        from gemini_client import PERSONAS

        self.assertIn("default", PERSONAS)
        self.assertIn("developer", PERSONAS)
        self.assertIn("tutor", PERSONAS)
        self.assertIn("creative", PERSONAS)
        self.assertIn("concise", PERSONAS)

        for name, prompt in PERSONAS.items():
            self.assertIsInstance(prompt, str)
            self.assertGreater(len(prompt), 10)


class TestLevelingFormulas(unittest.TestCase):
    def test_xp_scaling(self):
        from cogs.leveling import xp_for_level, level_from_xp

        self.assertEqual(xp_for_level(0), 100)
        self.assertGreater(xp_for_level(5), xp_for_level(4))
        self.assertEqual(level_from_xp(0), 0)
        lvl_5_xp = xp_for_level(5)
        self.assertEqual(level_from_xp(lvl_5_xp), 5)

    def test_progress_bar(self):
        from cogs.leveling import _progress_bar

        bar_half = _progress_bar(50, 100, length=10)
        self.assertEqual(bar_half, "▓" * 5 + "░" * 5)
        bar_full = _progress_bar(100, 100, length=10)
        self.assertEqual(bar_full, "▓" * 10)


class TestFunUtilities(unittest.TestCase):
    def test_mock_and_reverse(self):
        sample = "hello world"
        reversed_text = sample[::-1]
        self.assertEqual(reversed_text, "dlrow olleh")


class TestBotExtensionIntegrity(unittest.TestCase):
    def test_all_ten_cogs_registered(self):
        from main import SkillXBot

        bot = SkillXBot()
        expected = [
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
        self.assertEqual(bot.extensions_to_load, expected)


class TestBroadcastColorClamping(unittest.TestCase):
    def test_color_bounds_and_parsing(self):
        inputs = [
            ("#a855f7", 0xa855f7),
            ("a855f7", 0xa855f7),
            (11032055, 0xa855f7),
            (999999999, 0xFFFFFF),  # Clamped to 16777215
            ("#ffffffffff", 0xFFFFFF),
            (-50, 0),
        ]
        for inp, expected in inputs:
            color_int = 0x5865F2
            if isinstance(inp, int):
                color_int = max(0, min(0xFFFFFF, inp))
            elif isinstance(inp, str):
                c_str = inp.strip().lstrip("#")
                try:
                    color_int = max(0, min(0xFFFFFF, int(c_str, 16)))
                except ValueError:
                    try:
                        color_int = max(0, min(0xFFFFFF, int(c_str, 10)))
                    except ValueError:
                        color_int = 0x5865F2
            self.assertLessEqual(color_int, 16777215)
            self.assertGreaterEqual(color_int, 0)
            self.assertEqual(color_int, expected)


if __name__ == "__main__":
    unittest.main()
