"""Gemini API Client with high-availability model fallback chain, auto-healing health tracking, and safety parsing."""

import asyncio
import logging
import time
from typing import Optional
from google import genai
from google.genai import types

logger = logging.getLogger("skillx.gemini")


PERSONAS = {
    "default": (
        "You are SkillX, an intelligent, helpful, and courteous AI assistant in a Discord community. "
        "Use clean Markdown styling (bolding, lists, and code blocks with syntax highlighting). "
        "Keep answers informative yet concise for Discord chat."
    ),
    "developer": (
        "You are SkillX Senior Dev, an elite software engineer and systems architect. "
        "Provide idiomatic, secure, high-performance code solutions with clear explanations, "
        "proper complexity analysis, and edge case coverage. Always format code with syntax fences."
    ),
    "tutor": (
        "You are SkillX Tutor, a patient, encouraging, and clear educator. "
        "Break down complex topics into intuitive step-by-step concepts, using analogies, examples, "
        "and clear takeaways suited for learners."
    ),
    "creative": (
        "You are SkillX Creative, a witty, imaginative, and engaging writer and conversationalist. "
        "Craft rich, entertaining, and vibrant descriptions, ideas, and stories with dynamic personality."
    ),
    "concise": (
        "You are SkillX Brief. Answer in as few words as possible without losing factual accuracy. "
        "Zero filler, no conversational preambles, direct bullet points where applicable."
    ),
}

# Exhaustive model fallback chain spanning all verified GenAI text models
DEFAULT_MODEL_CHAIN: list[str] = [
    "gemini-3.5-flash-lite",  # Primary: highest availability, ultra-fast latency (~2-4s)
    "gemini-3.1-flash-lite",  # High-reliability secondary flash-lite tier
    "gemma-4-26b-a4b-it",     # High-throughput 26B instruction-tuned open model on GenAI
    "gemma-4-31b-it",         # 31B instruction-tuned open model on GenAI
    "gemini-3.8-flash",       # High intelligence 3.8 Flash model
    "gemini-3.7-flash",       # High intelligence 3.7 Flash model
    "gemini-3.6-flash",       # Gemini 3.6 Flash
    "gemini-3.5-flash",       # Gemini 3.5 Flash
    "gemini-4-hydrogen",      # Next-gen preview tier
]


class GeminiClient:
    """Manages resilient generation requests to Google Gemini across an exhaustive fallback model chain."""

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

        self.model_chain: list[str] = list(DEFAULT_MODEL_CHAIN)
        self.system_instruction = PERSONAS["default"]

        # Health tracking & auto-demotion
        # model_cooldowns: model_name -> unix timestamp until which model is deferred
        self.model_cooldowns: dict[str, float] = {}
        # model_stats: model_name -> {successes, failures, last_latency_ms, last_error, last_attempt}
        self.model_stats: dict[str, dict] = {
            m: {
                "successes": 0,
                "failures": 0,
                "last_latency_ms": 0,
                "last_error": "",
                "last_attempt": 0.0,
            }
            for m in self.model_chain
        }

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
        """Categorizes exception into standardized failure categories."""
        if isinstance(exc, asyncio.TimeoutError):
            return "TIMEOUT"
        s = str(exc).lower()
        if any(token in s for token in ("auth", "invalid api key", "api_key_invalid", "unauthorized")):
            return "AUTH_FAILURE"
        if any(token in s for token in ("quota", "resource_exhausted", "429", "rate limit")):
            return "QUOTA_EXCEEDED"
        if any(token in s for token in ("503", "unavailable", "demand", "temporarily", "overloaded")):
            return "SERVICE_UNAVAILABLE"
        if any(token in s for token in ("404", "not_found", "no longer available")):
            return "MODEL_DEPRECATED"
        return "GENERIC_ERROR"

    def _get_prioritized_models(self) -> list[str]:
        """
        Dynamically prioritizes models: healthy models come first in their primary order.
        Models currently in cooldown are deferred to the end, ordered by earliest cooldown expiry.
        This guarantees zero downtime while ensuring we never stall on unhealthy models.
        """
        now = time.time()
        healthy: list[str] = []
        cooling_down: list[tuple[float, str]] = []

        for m in self.model_chain:
            expiry = self.model_cooldowns.get(m, 0.0)
            if expiry <= now:
                healthy.append(m)
            else:
                cooling_down.append((expiry, m))

        # Sort cooling down by earliest expiry first
        cooling_down.sort(key=lambda x: x[0])
        return healthy + [m for _, m in cooling_down]

    def _extract_text_safely(self, response) -> Optional[str]:
        """Safely extracts text parts from response, filtering thoughts and handling safety finish reasons."""
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
                    # Filter out internal reasoning / thought parts if present (e.g. in Gemma models)
                    non_thought_parts = [
                        p.text for p in content.parts
                        if getattr(p, "text", None) and not getattr(p, "thought", False)
                    ]
                    if non_thought_parts:
                        return "".join(non_thought_parts)

                    # If only thought parts are present, return the combined text
                    all_text = [
                        p.text for p in content.parts
                        if getattr(p, "text", None)
                    ]
                    if all_text:
                        return "".join(all_text)

        # Fallback to response.text property
        try:
            return response.text
        except Exception:
            return None

    def get_model_status(self) -> dict:
        """Returns real-time health, cooldown, and performance diagnostics across all models."""
        now = time.time()
        diagnostics = []
        for m in self.model_chain:
            stats = self.model_stats.get(m, {})
            expiry = self.model_cooldowns.get(m, 0.0)
            is_cooling = expiry > now
            cd_remaining = round(expiry - now) if is_cooling else 0

            status = "ONLINE"
            if is_cooling:
                last_err = stats.get("last_error", "")
                status = "RATE_LIMITED" if "429" in last_err or "QUOTA" in last_err else "COOLING_DOWN"

            diagnostics.append({
                "model": m,
                "status": status,
                "cooldown_remaining": cd_remaining,
                "successes": stats.get("successes", 0),
                "failures": stats.get("failures", 0),
                "last_latency_ms": stats.get("last_latency_ms", 0),
                "last_error": stats.get("last_error", ""),
            })

        healthy_count = sum(1 for d in diagnostics if d["status"] == "ONLINE")
        return {
            "total_models": len(self.model_chain),
            "healthy_models": healthy_count,
            "models": diagnostics,
        }

    async def generate_with_fallback(
        self,
        prompt: str,
        history: Optional[list[dict]] = None,
        persona: str = "default",
        custom_system_instruction: Optional[str] = None,
        temperature: float = 0.7,
        max_output_tokens: int = 1024,
        timeout_per_model: float = 12.0,
    ) -> tuple[Optional[str], str]:
        """
        Executes generation attempting models across the prioritized fallback chain.
        Applies smart 1-shot retries for transient 503 spikes and automatic health-cooldown demotion.

        Returns:
            (generated_text, model_name_or_status)
        """
        contents = list(history or [])
        contents.append({"role": "user", "parts": [{"text": prompt}]})

        # Determine active system instruction
        active_instruction = custom_system_instruction or PERSONAS.get(persona.lower(), self.system_instruction)

        config = types.GenerateContentConfig(
            system_instruction=active_instruction,
            safety_settings=self.safety_settings,
            temperature=max(0.0, min(1.0, temperature)),
            max_output_tokens=max_output_tokens,
        )

        prioritized_models = self._get_prioritized_models()

        for model_name in prioritized_models:
            stats = self.model_stats.setdefault(model_name, {
                "successes": 0,
                "failures": 0,
                "last_latency_ms": 0,
                "last_error": "",
                "last_attempt": 0.0,
            })

            # For each model, attempt up to 2 times (initial + 1 fast retry for transient 503 / timeout)
            for attempt in range(2):
                stats["last_attempt"] = time.time()
                t0 = time.perf_counter()

                try:
                    coro = self.client.aio.models.generate_content(
                        model=model_name,
                        contents=contents,
                        config=config,
                    )
                    response = await asyncio.wait_for(coro, timeout=timeout_per_model)
                    text = self._extract_text_safely(response)

                    if text:
                        elapsed_ms = round((time.perf_counter() - t0) * 1000)
                        # Success: clear any active cooldown and log performance
                        self.model_cooldowns.pop(model_name, None)
                        stats["successes"] += 1
                        stats["last_latency_ms"] = elapsed_ms
                        stats["last_error"] = ""
                        return text.strip(), model_name

                except Exception as exc:
                    classification = self._classify_error(exc)
                    stats["failures"] += 1
                    stats["last_error"] = f"{classification}: {exc}"

                    if classification == "AUTH_FAILURE":
                        logger.error("Invalid API credentials. Aborting model fallback.")
                        return None, "auth_error"

                    if classification == "QUOTA_EXCEEDED":
                        # Rate limit / daily quota hit: apply 5-minute cooldown and immediately switch model
                        self.model_cooldowns[model_name] = time.time() + 300.0
                        logger.warning(
                            "Model %s exceeded quota (429). Placed in 5m cooldown. Switching model.",
                            model_name,
                        )
                        break

                    if classification == "MODEL_DEPRECATED":
                        # Deprecated / 404 model: apply 24h cooldown
                        self.model_cooldowns[model_name] = time.time() + 86400.0
                        logger.warning("Model %s returned 404 Not Found. Demoting for 24h.", model_name)
                        break

                    if classification == "SERVICE_UNAVAILABLE":
                        if attempt == 0:
                            # Transient 503 demand spike: fast 350ms backoff and retry once before demoting
                            logger.info(
                                "Model %s returned 503. Retrying once after 350ms backoff...",
                                model_name,
                            )
                            await asyncio.sleep(0.35)
                            continue
                        else:
                            # 2nd attempt failed: place in 45s cooldown
                            self.model_cooldowns[model_name] = time.time() + 45.0
                            logger.warning(
                                "Model %s 503 persisted after retry. Placed in 45s cooldown.",
                                model_name,
                            )
                            break

                    if classification == "TIMEOUT":
                        if attempt == 0:
                            logger.info(
                                "Model %s timed out after %.1fs. Retrying once...",
                                model_name,
                                timeout_per_model,
                            )
                            await asyncio.sleep(0.25)
                            continue
                        else:
                            self.model_cooldowns[model_name] = time.time() + 45.0
                            logger.warning(
                                "Model %s timed out twice. Placed in 45s cooldown.",
                                model_name,
                            )
                            break

                    # Generic error: place in 30s cooldown and try next model
                    self.model_cooldowns[model_name] = time.time() + 30.0
                    logger.warning("Model %s encountered %s: %s", model_name, classification, exc)
                    break

        logger.error("All Gemini fallback models were exhausted across all tiers.")
        return None, "exhausted"

    async def ping_ai(self) -> tuple[bool, int, str]:
        """Measures roundtrip AI generation latency in milliseconds across the active fallback chain."""
        loop = asyncio.get_event_loop()
        t0 = loop.time()
        text, model = await self.generate_with_fallback(
            prompt="Hi",
            max_output_tokens=5,
            timeout_per_model=10.0,
        )
        elapsed_ms = round((loop.time() - t0) * 1000)
        return bool(text), elapsed_ms, model

    async def review_code(self, code: str, language: str = "") -> tuple[Optional[str], str]:
        """Performs specialized code review, security check, and architectural feedback."""
        prompt = (
            f"Please conduct an in-depth code review on the following {language} snippet:\n\n"
            f"```{language}\n{code}\n```\n\n"
            "Format your response cleanly with the following markdown headers:\n"
            "1. **🔍 Analysis & Complexity**\n"
            "2. **⚠️ Potential Bugs & Security Risks**\n"
            "3. **⚡ Recommended Refactor (Optimized Code)**"
        )
        return await self.generate_with_fallback(
            prompt=prompt,
            persona="developer",
            temperature=0.3,
            timeout_per_model=14.0,
        )

    async def summarize_text(self, text: str) -> tuple[Optional[str], str]:
        """Generates a structured, concise executive summary of chat dialogue or article text."""
        prompt = (
            "Summarize the key points of the following Discord chat conversation log.\n"
            "Organize your summary into:\n"
            "• **Main Topics Discussed**\n"
            "• **Key Decisions / Takeaways**\n"
            "• **Action Items (if any)**\n\n"
            f"Chat Log:\n{text}"
        )
        return await self.generate_with_fallback(
            prompt=prompt,
            persona="concise",
            temperature=0.4,
            timeout_per_model=14.0,
        )
