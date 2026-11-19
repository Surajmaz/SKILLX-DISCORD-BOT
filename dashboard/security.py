"""Security engine for the SkillX Web Dashboard.

Provides HMAC session tokens, constant-time authentication, CSRF validation,
brute-force rate limiting, and security header injection.
"""

import hashlib
import hmac
import time
from typing import Optional
from aiohttp import web

LOGIN_WINDOW_SECONDS = 600   # 10 minutes
MAX_FAILED_ATTEMPTS = 5      # Max failed attempts per window
SESSION_MAX_AGE = 86400      # 24 hours


class DashboardSecurityManager:
    """Manages dashboard authentication, session cookies, and brute-force defenses."""

    def __init__(self, password: str, secret_key: str):
        self.password = password
        self.secret_bytes = secret_key.encode("utf-8")
        self.failed_logins: dict[str, list[float]] = {}
        self._last_cleanup = time.monotonic()

    def _cleanup_old_attempts(self, now: float) -> None:
        """Periodically cleans up expired login attempts to prevent memory growth."""
        if now - self._last_cleanup > 300:
            for ip in list(self.failed_logins.keys()):
                self.failed_logins[ip] = [
                    t for t in self.failed_logins[ip] if now - t < LOGIN_WINDOW_SECONDS
                ]
                if not self.failed_logins[ip]:
                    self.failed_logins.pop(ip, None)
            self._last_cleanup = now

    def is_ip_rate_limited(self, ip: str) -> tuple[bool, int]:
        """Checks if an IP address is temporarily blocked due to brute-force attempts."""
        now = time.monotonic()
        self._cleanup_old_attempts(now)

        attempts = [t for t in self.failed_logins.get(ip, []) if now - t < LOGIN_WINDOW_SECONDS]
        self.failed_logins[ip] = attempts

        if len(attempts) >= MAX_FAILED_ATTEMPTS:
            retry_after = int(LOGIN_WINDOW_SECONDS - (now - attempts[0]))
            return True, max(1, retry_after)
        return False, 0

    def record_failed_login(self, ip: str) -> None:
        """Records a failed login attempt for the given IP address."""
        now = time.monotonic()
        if ip not in self.failed_logins:
            self.failed_logins[ip] = []
        self.failed_logins[ip].append(now)

    def reset_failed_logins(self, ip: str) -> None:
        """Resets failed attempts after a successful login."""
        self.failed_logins.pop(ip, None)

    def verify_password(self, provided: str) -> bool:
        """Performs a constant-time comparison to prevent timing attacks."""
        if not provided or not self.password:
            return False
        return hmac.compare_digest(provided.strip(), self.password.strip())

    def create_session_token(self) -> str:
        """Creates a signed, timestamped session token."""
        ts = str(int(time.time()))
        signature = hmac.new(self.secret_bytes, ts.encode("utf-8"), hashlib.sha256).hexdigest()
        return f"{ts}.{signature}"

    def verify_session_token(self, token: Optional[str]) -> bool:
        """Validates the HMAC signature and expiration of a session token."""
        if not token or "." not in token:
            return False

        try:
            ts_str, signature = token.split(".", 1)
            ts = int(ts_str)
        except ValueError:
            return False

        # Expiration check
        now = int(time.time())
        if now - ts > SESSION_MAX_AGE or ts > now + 60:
            return False

        # Verify HMAC signature
        expected_sig = hmac.new(self.secret_bytes, ts_str.encode("utf-8"), hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature, expected_sig)

    def generate_csrf_token(self, session_token: str) -> str:
        """Generates a CSRF token bound to the current session token."""
        seed = f"{session_token}:skillx-csrf".encode("utf-8")
        return hmac.new(self.secret_bytes, seed, hashlib.sha256).hexdigest()[:32]

    def verify_csrf_token(self, session_token: Optional[str], csrf_token: Optional[str]) -> bool:
        """Verifies that the CSRF token matches the session."""
        if not session_token or not csrf_token:
            return False
        expected = self.generate_csrf_token(session_token)
        return hmac.compare_digest(csrf_token, expected)


def _inject_headers(headers) -> None:
    headers["X-Frame-Options"] = "DENY"
    headers["X-Content-Type-Options"] = "nosniff"
    headers["X-XSS-Protection"] = "1; mode=block"
    headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
        "img-src 'self' data: https://cdn.discordapp.com https://images.unsplash.com; "
        "connect-src 'self'; "
        "font-src 'self' https://cdn.jsdelivr.net https://fonts.gstatic.com; "
        "frame-ancestors 'none';"
    )


@web.middleware
async def security_headers_middleware(request: web.Request, handler):
    """Injects strict HTTP security headers into all responses."""
    try:
        response = await handler(request)
    except web.HTTPException as ex:
        _inject_headers(ex.headers)
        raise ex

    _inject_headers(response.headers)
    return response
