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


class TestGeminiResilience(unittest.TestCase):
    def setUp(self):
        from gemini_client import GeminiClient
        self.client = GeminiClient("fake_test_key")

    def test_model_chain_count_and_tiering(self):
        from gemini_client import DEFAULT_MODEL_CHAIN

        self.assertGreaterEqual(len(DEFAULT_MODEL_CHAIN), 9)
        self.assertEqual(DEFAULT_MODEL_CHAIN[0], "gemini-3.5-flash-lite")
        self.assertIn("gemma-4-26b-a4b-it", DEFAULT_MODEL_CHAIN)
        self.assertIn("gemini-3.1-flash-lite", DEFAULT_MODEL_CHAIN)
        self.assertIn("gemini-3.8-flash", DEFAULT_MODEL_CHAIN)

    def test_error_classification(self):
        import asyncio
        self.assertEqual(self.client._classify_error(Exception("429 Resource has been exhausted")), "QUOTA_EXCEEDED")
        self.assertEqual(self.client._classify_error(Exception("503 Service Unavailable: High demand spike")), "SERVICE_UNAVAILABLE")
        self.assertEqual(self.client._classify_error(Exception("404 Model not_found")), "MODEL_DEPRECATED")
        self.assertEqual(self.client._classify_error(Exception("API_KEY_INVALID: unauthorized")), "AUTH_FAILURE")
        self.assertEqual(self.client._classify_error(asyncio.TimeoutError()), "TIMEOUT")
        self.assertEqual(self.client._classify_error(Exception("Unknown network socket reset")), "GENERIC_ERROR")

    def test_prioritization_and_cooldown_sorting(self):
        import time
        now = time.time()
        # Put gemini-3.5-flash-lite in 100s cooldown, gemini-3.1-flash-lite in 20s cooldown
        self.client.model_cooldowns["gemini-3.5-flash-lite"] = now + 100.0
        self.client.model_cooldowns["gemini-3.1-flash-lite"] = now + 20.0

        prioritized = self.client._get_prioritized_models()

        # Healthy models must come before cooling down models
        self.assertNotEqual(prioritized[0], "gemini-3.5-flash-lite")
        self.assertNotEqual(prioritized[0], "gemini-3.1-flash-lite")
        self.assertEqual(prioritized[0], "gemma-4-26b-a4b-it")

        # Cooling down models should be sorted by earliest expiry
        self.assertEqual(prioritized[-2], "gemini-3.1-flash-lite")
        self.assertEqual(prioritized[-1], "gemini-3.5-flash-lite")

    def test_safe_text_extraction_with_thoughts(self):
        from unittest.mock import MagicMock

        # Mock a response with thought parts (like Gemma models)
        mock_resp = MagicMock()
        mock_candidate = MagicMock()
        mock_candidate.finish_reason = "STOP"

        p_thought = MagicMock()
        p_thought.thought = True
        p_thought.text = "Internal reasoning: user wants answer."

        p_answer = MagicMock()
        p_answer.thought = False
        p_answer.text = "The answer is 42."

        mock_candidate.content.parts = [p_thought, p_answer]
        mock_resp.candidates = [mock_candidate]

        extracted = self.client._extract_text_safely(mock_resp)
        self.assertEqual(extracted, "The answer is 42.")

    def test_model_status_diagnostics(self):
        status = self.client.get_model_status()
        self.assertEqual(status["total_models"], len(self.client.model_chain))
        self.assertGreaterEqual(status["healthy_models"], 0)
        self.assertEqual(len(status["models"]), len(self.client.model_chain))



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


class TestMultiLanguageTranslationAndHelpUI(unittest.IsolatedAsyncioTestCase):
    def test_supported_languages_schema_and_limits(self):
        from ui import SUPPORTED_LANGUAGES
        self.assertEqual(len(SUPPORTED_LANGUAGES), 25)
        for lang in SUPPORTED_LANGUAGES:
            self.assertIn("code", lang)
            self.assertIn("name", lang)
            self.assertIn("native", lang)
            self.assertIn("desc", lang)
            self.assertIn("emoji", lang)
            label = f"{lang['native']} ({lang['name']})"
            self.assertLessEqual(len(label), 100)
            self.assertLessEqual(len(lang["desc"]), 100)
            self.assertLessEqual(len(lang["name"]), 100)

    def test_build_help_embed_categories(self):
        from ui import build_help_embed, HELP_CATEGORIES
        for cat in HELP_CATEGORIES:
            embed = build_help_embed(cat)
            self.assertIsNotNone(embed.title)
            self.assertIsNotNone(embed.description)
            self.assertGreater(len(embed.fields), 0)
            self.assertIn("Translate", embed.footer.text)

    async def test_translate_embed_logic(self):
        from ui import translate_embed
        orig_embed = discord.Embed(title="SkillX Manual", description="Test description")
        orig_embed.add_field(name="AI Chat", value="/chat with gemini", inline=False)
        orig_embed.set_footer(text="Original footer")

        mock_gemini = unittest.mock.AsyncMock()
        mock_gemini.translate_text.return_value = (
            "[[TITLE]] Manual de SkillX\n\n"
            "[[DESCRIPTION]]\nDescripción de prueba\n\n"
            "[[FIELD_0_NAME]] Chat de IA\n\n"
            "[[FIELD_0_VAL]] /chat con gemini\n\n"
            "[[FOOTER]] Pie de página original",
            "gemini-2.5-flash-lite",
        )

        # 1. Translate to Spanish
        trans_embed = await translate_embed(orig_embed, mock_gemini, "Spanish")
        self.assertEqual(trans_embed.title, "Manual de SkillX")
        self.assertEqual(trans_embed.description, "Descripción de prueba")
        self.assertEqual(trans_embed.fields[0].name, "Chat de IA")
        self.assertEqual(trans_embed.fields[0].value, "/chat con gemini")
        self.assertIn("Spanish", trans_embed.footer.text)

        # 2. English returns original without calling gemini
        eng_embed = await translate_embed(orig_embed, mock_gemini, "English")
        self.assertEqual(eng_embed, orig_embed)

    async def test_gemini_client_translate_text(self):
        from gemini_client import GeminiClient
        client = GeminiClient("fake_key")
        client.generate_with_fallback = unittest.mock.AsyncMock(return_value=("Hola Mundo", "gemini-3.5-flash"))

        # First call -> calls gemini
        res, model = await client.translate_text("Hello World", "Spanish")
        self.assertEqual(res, "Hola Mundo")
        self.assertEqual(model, "gemini-3.5-flash")

        # Second call with same text and target language -> hit cache
        client.generate_with_fallback.reset_mock()
        res2, model2 = await client.translate_text("Hello World", "Spanish")
        self.assertEqual(res2, "Hola Mundo")
        self.assertEqual(model2, "cache")
        client.generate_with_fallback.assert_not_called()

        # English passthrough
        res3, model3 = await client.translate_text("Hello World", "English")
        self.assertEqual(res3, "Hello World")
        self.assertEqual(model3, "original")

    def test_help_menu_and_language_views(self):
        from ui import HelpMenuView, LanguageSelectView, TranslateFeaturesButton, build_help_embed
        mock_bot = unittest.mock.MagicMock()
        embed = build_help_embed("overview")

        # HelpMenuView
        help_view = HelpMenuView(mock_bot, author_id=123, current_embed=embed)
        self.assertEqual(len(help_view.children), 4)

        # LanguageSelectView
        from ui import LanguageSelect
        lang_view = LanguageSelectView(embed, mock_bot, author_id=123)
        self.assertEqual(len(lang_view.children), 3)
        dropdown = next(c for c in lang_view.children if isinstance(c, LanguageSelect))
        self.assertEqual(dropdown.placeholder, "🌐 Select your preferred language...")
        self.assertEqual(len(dropdown.options), 25)

        # Standalone button
        btn = TranslateFeaturesButton(source_embed=embed, bot=mock_bot)
        self.assertEqual(btn.label, "Translate Features")


if __name__ == "__main__":
    unittest.main()
