"""Gemini API Client with asynchronous failover, retry logic, and safety parsing."""

import asyncio
import logging
from typing import Optional
from google import genai
from google.genai import types

logger = logging.getLogger("skillx.gemini")


class GeminiClient:
    """Manages resilient generation requests to Google Gemini across fallback model tiers."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        try:
            self.client = genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(
                    retry_options=types.HttpRetryOptions(
                        attempts=1,
                    )
                ),
            )
        except Exception:
            self.client = genai.Client(api_key=api_key)

        # High-availability model fallback chain using active Gemini 3.x series
        self.model_chain: list[str] = [
            "gemini-3.5-flash-lite",
            "gemini-3.5-flash",
            "gemini-3.1-flash-lite",
            "gemini-3.8-flash",
        ]

        self.system_instruction = (
            "You are SkillX, an intelligent, helpful, and courteous AI assistant in a Discord community. "
            "Use clean Markdown styling (bolding, lists, and code blocks with syntax highlighting). "
            "Keep answers informative yet concise for Discord chat."
        )

        self.safety_settings = [
            types.SafetySetting(
                category="HARM_CATEGORY_HARASSMENT",
                threshold="BLOCK_MEDIUM_AND_ABOVE",
            ),
            types.SafetySetting(
                category="HARM_CATEGORY_HATE_SPEECH",
                threshold="BLOCK_MEDIUM_AND_ABOVE",
            ),
            types.SafetySetting(
                category="HARM_CATEGORY_DANGEROUS_CONTENT",
                threshold="BLOCK_MEDIUM_AND_ABOVE",
            ),
        ]

    def _classify_error(self, exc: Exception) -> str:
        s = str(exc).lower()
        if any(token in s for token in ("auth", "invalid api key", "api_key_invalid", "unauthorized")):
            return "AUTH_FAILURE"
        if any(token in s for token in ("quota", "resource_exhausted", "429", "rate limit")):
            return "QUOTA_EXCEEDED"
        if any(token in s for token in ("503", "unavailable", "demand", "temporarily")):
            return "SERVICE_UNAVAILABLE"
        if any(token in s for token in ("404", "not_found", "no longer available")):
            return "MODEL_DEPRECATED"
        return "GENERIC_ERROR"

    def _extract_text_safely(self, response) -> Optional[str]:
        """Safely extracts text parts from response without triggering internal exceptions."""
        if not response:
            return None

        # Check candidate safety finish reasons
        if getattr(response, "candidates", None):
            for candidate in response.candidates:
                finish_reason = str(getattr(candidate, "finish_reason", "")).upper()
                if any(r in finish_reason for r in ("SAFETY", "RECITATION", "BLOCKLIST")):
                    return "⚠️ The response was flagged or blocked by Gemini safety guidelines."

                content = getattr(candidate, "content", None)
                if content and getattr(content, "parts", None):
                    text_parts = [
                        p.text for p in content.parts
                        if getattr(p, "text", None)
                    ]
                    if text_parts:
                        return "".join(text_parts)

        # Fallback to response.text property
        try:
            return response.text
        except Exception:
            return None

    async def generate_with_fallback(
        self, prompt: str, history: Optional[list[dict]] = None
    ) -> tuple[Optional[str], str]:
        """
        Executes generation attempting each model in the fallback chain until success.

        Returns:
            (generated_text, model_name_or_status)
        """
        contents = list(history or [])
        contents.append({"role": "user", "parts": [{"text": prompt}]})

        config = types.GenerateContentConfig(
            system_instruction=self.system_instruction,
            safety_settings=self.safety_settings,
            temperature=0.7,
            max_output_tokens=2048,
        )

        for model_name in self.model_chain:
            try:
                # Use native async client
                response = await self.client.aio.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=config,
                )
                text = self._extract_text_safely(response)
                if text:
                    return text.strip(), model_name

            except Exception as exc:
                classification = self._classify_error(exc)
                logger.warning(
                    "Model %s failed with %s: %s", model_name, classification, exc
                )

                if classification == "AUTH_FAILURE":
                    logger.error("Invalid API credentials. Aborting model fallback.")
                    return None, "auth_error"

                # Wait slightly before attempting next fallback model
                await asyncio.sleep(0.5)

        logger.error("All Gemini fallback models were exhausted.")
        return None, "exhausted"
